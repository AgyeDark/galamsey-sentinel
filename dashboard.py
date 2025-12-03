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
st.set_page_config(page_title="Galamsey Sentinel (Calibrated)", page_icon="🛰️", layout="wide")

st.title("🇬🇭 Galamsey Sentinel Tracker")
st.markdown("**Calibrated Remote Sensing Tool** | Adjust thresholds to detect high-sediment flows.")

# --- SIDEBAR CONTROLS ---
st.sidebar.header("1. Location & Time")

river_options = {
    "Pra River (Twifo Praso)": [-1.58, 5.55, -1.52, 5.65],
    "Ankobra River (Prestea)": [-2.15, 5.40, -2.05, 5.50],
    "Birim River (Kyebi)": [-0.55, 6.10, -0.45, 6.20],
    "Offin River (Dunkwa)": [-1.85, 5.90, -1.75, 6.00],
    "White Volta (Pwalugu)": [-0.85, 10.58, -0.83, 10.60]
}

selected_river = st.sidebar.selectbox("Select River Basin", list(river_options.keys()))
bbox = river_options[selected_river]

year = st.sidebar.slider("Select Year", 2017, 2024, 2023)
max_cloud = st.sidebar.slider("Max Cloud Cover (%)", 0, 50, 20)

# --- NEW CALIBRATION SECTION ---
st.sidebar.divider()
st.sidebar.header("2. Sensor Calibration")
st.sidebar.info("💡 If the river looks 'False Clear', lower the Water Mask Threshold.")

# Standard NDWI threshold is 0.0. For muddy water, we often need -0.05 or -0.1
mask_threshold = st.sidebar.slider(
    "Water Mask Threshold (NDWI)", 
    -0.2, 0.2, 0.0, 0.01,
    help="Lower this value to detect muddier water. If too low, it will mistakenly include land."
)

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
    return sorted(items, key=lambda i: i.properties["datetime"])

def process_image(item):
    href_red = item.assets["B04"].href
    href_green = item.assets["B03"].href
    href_nir = item.assets["B08"].href

    with rasterio.open(href_red) as src:
        red = src.read(1, out_shape=(src.height // 8, src.width // 8))
    with rasterio.open(href_green) as src:
        green = src.read(1, out_shape=(src.height // 8, src.width // 8))
    with rasterio.open(href_nir) as src:
        nir = src.read(1, out_shape=(src.height // 8, src.width // 8))

    np.seterr(divide='ignore', invalid='ignore')
    r, g, n = red.astype(float), green.astype(float), nir.astype(float)
    
    # Indices
    ndti = (r - g) / (r + g) # Turbidity
    ndwi = (g - n) / (g + n) # Water Detection
    
    return ndti, ndwi, item.datetime

# --- MAIN APP LOGIC ---

if st.sidebar.button("Run Analysis", type="primary"):
    with st.spinner(f"🛰️ Scanning {selected_river}..."):
        items = fetch_satellite_data(bbox, year, max_cloud)
        
    if not items:
        st.error("No clear images found. Try increasing cloud cover.")
    else:
        st.success(f"Processing {len(items)} scenes with Threshold {mask_threshold}...")
        
        progress_bar = st.progress(0)
        results = []
        
        for i, item in enumerate(items):
            try:
                ndti, ndwi, date = process_image(item)
                
                # --- THE FIX: DYNAMIC MASKING ---
                # We use the user-selected threshold instead of hardcoded 0.0
                river_pixels = ndti[ndwi > mask_threshold]
                
                if len(river_pixels) > 50: # Minimum pixels to count as valid
                    avg_turbidity = np.nanmean(river_pixels)
                    # Filter outlier noise
                    if -0.5 < avg_turbidity < 0.8:
                        results.append({"Date": date, "Turbidity": avg_turbidity})
            except:
                pass
            progress_bar.progress((i + 1) / len(items))
            
        if results:
            df = pd.DataFrame(results)
            df = df.sort_values("Date")
            
            # 1. METRICS
            avg_annual = df["Turbidity"].mean()
            col1, col2, col3 = st.columns(3)
            col1.metric("Avg Turbidity (NDTI)", f"{avg_annual:.3f}")
            col2.metric("Data Points", len(df))
            
            # Recalibrate Status Logic
            if avg_annual > 0.1: status = "CRITICAL (Heavy Sediment)"
            elif avg_annual > 0.0: status = "MODERATE (Visible Turbidity)"
            else: status = "CLEAR"
            col3.metric("Status", status)

            st.divider()

            # 2. TREND CHART
            st.subheader(f"📉 Turbidity Trend ({year})")
            fig = px.line(df, x="Date", y="Turbidity", markers=True)
            fig.update_traces(line_color='#8B4513', line_width=3)
            
            # Update Danger Zones for High Sediment
            fig.add_hrect(y0=0.1, y1=0.5, line_width=0, fillcolor="red", opacity=0.1, annotation_text="Heavy Galamsey")
            fig.add_hrect(y0=0.0, y1=0.1, line_width=0, fillcolor="orange", opacity=0.1, annotation_text="Moderate")
            fig.add_hrect(y0=-0.3, y1=0.0, line_width=0, fillcolor="blue", opacity=0.1, annotation_text="Clear")
            
            st.plotly_chart(fig, use_container_width=True)
            
            # 3. DEBUG VIEW (LATEST IMAGE)
            st.divider()
            st.subheader("🛠️ Calibration View (Latest Scene)")
            
            last_item = items[-1]
            ndti, ndwi, date = process_image(last_item)
            
            # Apply the user's mask
            masked_ndti = np.ma.masked_where(ndwi <= mask_threshold, ndti)
            
            col_map, col_mask = st.columns(2)
            
            with col_map:
                st.write("**Detected River (Masked)**")
                fig_map, ax = plt.subplots(figsize=(8, 8))
                cmap = mcolors.LinearSegmentedColormap.from_list("galamsey", ["blue", "cyan", "yellow", "red", "brown"])
                ax.imshow(masked_ndti, cmap=cmap, vmin=-0.1, vmax=0.3)
                ax.axis('off')
                st.pyplot(fig_map)
                
            with col_mask:
                st.write("**Raw Water Mask (Yellow = Selected)**")
                st.write(f"Showing pixels where NDWI > {mask_threshold}")
                fig_mask, ax2 = plt.subplots(figsize=(8, 8))
                # Show what the computer thinks is water
                mask_display = (ndwi > mask_threshold).astype(int)
                ax2.imshow(mask_display, cmap="viridis") 
                ax2.axis('off')
                st.pyplot(fig_mask)
                
            st.caption(f"Scene Date: {date.strftime('%Y-%m-%d')}")

        else:
            st.warning("No data found. Try lowering the threshold or checking different dates.")