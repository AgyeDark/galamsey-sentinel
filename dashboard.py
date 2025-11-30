import streamlit as st
import pystac_client
import planetary_computer
import rasterio
import numpy as np
import pandas as pd
import plotly.express as px
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# --- PAGE CONFIG ---
st.set_page_config(page_title="Galamsey Sentinel", page_icon="💧", layout="wide")

st.title("🇬🇭 Galamsey Sentinel Tracker")
st.markdown("""
**Operational Support Tool for Ghanaian Hydrology** This dashboard uses Sentinel-2 satellite imagery to monitor river turbidity (sediment load).  
*High turbidity is a strong proxy for illegal mining (Galamsey) activity.*
""")

# --- SIDEBAR CONTROLS ---
st.sidebar.header("Configuration")

river_options = {
    "Pra River (Twifo Praso)": [-1.58, 5.55, -1.52, 5.65],
    "Ankobra River (Prestea)": [-2.15, 5.40, -2.05, 5.50],
    "Birim River (Kyebi)": [-0.55, 6.10, -0.45, 6.20],
    "Offin River (Dunkwa)": [-1.85, 5.90, -1.75, 6.00]
}

selected_river = st.sidebar.selectbox("Select River Basin", list(river_options.keys()))
bbox = river_options[selected_river]

year = st.sidebar.slider("Select Year to Analyze", 2017, 2024, 2023)
max_cloud = st.sidebar.slider("Max Cloud Cover (%)", 0, 50, 20)

st.sidebar.divider()
st.sidebar.markdown("### ℹ️ Key Indicators")
st.sidebar.info("""
**NDTI (Turbidity Index):**
- **> 0.05 (Red):** Critical. Likely active mining or heavy flood runoff.
- **< 0.00 (Blue):** Clear. Normal river conditions.
""")

# --- FUNCTIONS ---
@st.cache_data
def fetch_satellite_data(bbox, year, cloud_cover):
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace
    )
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=f"{year}-01-01/{year}-12-31",
        query={"eo:cloud_cover": {"lt": cloud_cover}}, 
    )
    items = search.item_collection()
    # Sort by date
    return sorted(items, key=lambda i: i.properties["datetime"])

def process_image(item):
    # Fetch bands
    href_red = item.assets["B04"].href
    href_green = item.assets["B03"].href
    href_nir = item.assets["B08"].href

    # Read bands (downsampled for speed)
    with rasterio.open(href_red) as src:
        red = src.read(1, out_shape=(src.height // 8, src.width // 8))
    with rasterio.open(href_green) as src:
        green = src.read(1, out_shape=(src.height // 8, src.width // 8))
    with rasterio.open(href_nir) as src:
        nir = src.read(1, out_shape=(src.height // 8, src.width // 8))

    # Calculate Indices
    np.seterr(divide='ignore', invalid='ignore')
    r, g, n = red.astype(float), green.astype(float), nir.astype(float)
    
    ndti = (r - g) / (r + g)  # Turbidity
    ndwi = (g - n) / (g + n)  # Water Mask
    
    return ndti, ndwi, item.datetime

# --- MAIN APP LOGIC ---

if st.sidebar.button("Run Analysis", type="primary"):
    with st.spinner(f"🛰️ Searching satellite archives for {selected_river} in {year}..."):
        items = fetch_satellite_data(bbox, year, max_cloud)
        
    if not items:
        st.error("No clear images found! Try increasing cloud cover percentage or choosing a different year.")
    else:
        st.success(f"Found {len(items)} satellite scenes.")
        
        progress_bar = st.progress(0)
        results = []
        
        # Analyze each image
        for i, item in enumerate(items):
            try:
                ndti, ndwi, date = process_image(item)
                
                # Mask: Only Water Pixels (NDWI > 0)
                river_pixels = ndti[ndwi > 0.0]
                
                if len(river_pixels) > 300:
                    avg_turbidity = np.nanmean(river_pixels)
                    # Simple outlier filter to remove clouds/glint
                    if -0.5 < avg_turbidity < 0.5:
                        results.append({"Date": date, "Turbidity": avg_turbidity})
            except:
                pass
            progress_bar.progress((i + 1) / len(items))
            
        # --- DASHBOARD VISUALIZATION ---
        if results:
            df = pd.DataFrame(results)
            df = df.sort_values("Date")
            
            # 1. METRICS ROW
            avg_annual = df["Turbidity"].mean()
            delta_val = avg_annual - (-0.05) # Comparing to a "Clean" baseline of -0.05
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Annual Avg Turbidity", f"{avg_annual:.3f}", 
                          delta=f"{delta_val:.3f} vs Baseline", delta_color="inverse")
            with col2:
                st.metric("Data Points Analyzed", len(df))
            with col3:
                # Determine status
                if avg_annual > 0.05:
                    status = "CRITICAL ⚠️"
                elif avg_annual > 0:
                    status = "MODERATE ⚠️"
                else:
                    status = "GOOD ✅"
                st.metric("Overall Status", status)

            st.divider()

            # 2. TIME SERIES CHART
            st.subheader(f"📉 Turbidity Trend ({year})")
            
            fig = px.line(df, x="Date", y="Turbidity", markers=True)
            fig.update_traces(line_color='#8B4513', line_width=3)
            
            # Add Colored Zones
            fig.add_hrect(y0=0.05, y1=0.4, line_width=0, fillcolor="red", opacity=0.1, annotation_text="Danger Zone (Galamsey)")
            fig.add_hrect(y0=-0.2, y1=0.0, line_width=0, fillcolor="blue", opacity=0.1, annotation_text="Clear Zone")
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Context Expander
            with st.expander("🔎 How to read this graph"):
                st.markdown("""
                This graph shows the **Normalized Difference Turbidity Index (NDTI)** over time.
                - **Spikes Upwards:** Indicate sudden increases in sediment. This usually happens after heavy rains or when mining dredgers are active.
                - **The Red Zone (> 0.05):** Sustained values here mean the river is consistently muddy/brown.
                - **The Blue Zone (< 0.0):** Values here indicate the river is reflecting green/blue light, which means it is relatively clear.
                """)
            
            st.divider()

            # 3. LATEST MAP (Side by Side with Legend)
            st.subheader("🗺️ Latest Satellite View (River Only)")
            
            last_item = items[-1]
            ndti, ndwi, date = process_image(last_item)
            masked_ndti = np.ma.masked_where(ndwi < 0.0, ndti)
            
            col_map, col_legend = st.columns([3, 1])
            
            with col_map:
                fig_map, ax = plt.subplots(figsize=(10, 8))
                colors = ["#00008b", "#00BFFF", "#FFFF00", "#FF4500", "#5c4033"]
                cmap = mcolors.LinearSegmentedColormap.from_list("galamsey", colors)
                # Plot the map
                im = ax.imshow(masked_ndti, cmap=cmap, vmin=-0.15, vmax=0.25)
                ax.set_title(f"River Mask: {date.strftime('%Y-%m-%d')}")
                ax.axis('off')
                st.pyplot(fig_map)
                
            with col_legend:
                st.markdown("### Legend")
                st.markdown("🟤 **Dark Brown:** Heavy Sediment / Mud")
                st.markdown("🔴 **Red/Orange:** High Turbidity")
                st.markdown("🟡 **Yellow:** Moderate Turbidity")
                st.markdown("🔵 **Blue:** Clear Water")
                st.info("White areas are land/forest, which have been digitally removed to focus on the water.")

        else:
            st.warning("Found images, but could not detect enough water pixels. This area might be too cloudy or the river is too narrow for 10m satellite resolution.")