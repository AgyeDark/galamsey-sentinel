import streamlit as st
import pystac_client
import planetary_computer
import rasterio
import numpy as np
import pandas as pd
import plotly.express as px
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import io 

# --- PAGE CONFIG ---
st.set_page_config(page_title="Galamsey Sentinel Pro", page_icon="🛰️", layout="wide")

st.title("🇬🇭 Galamsey Sentinel Tracker Pro")
st.markdown("**Calibrated Remote Sensing Tool** | Monitor river turbidity with Scientific Indices & True Color verification.")

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

# CLOUD SLIDER EXPLANATION
max_cloud = st.sidebar.slider("Max Cloud Cover (%)", 0, 50, 20, 
    help="Filter out bad images. Lower = Clearer images but fewer data points. Higher = More data but risk of cloud noise.")

# --- CALIBRATION & VIEW SETTINGS ---
st.sidebar.divider()
st.sidebar.header("2. Sensor Calibration")

view_mode = st.sidebar.radio("Visualization Mode:", ["Scientific Heatmap (NDTI)", "True Color (RGB)"])

mask_threshold = st.sidebar.slider(
    "Water Mask Threshold (NDWI)", 
    -0.2, 0.2, 0.0, 0.01,
    help="Lower this value (e.g., to -0.1) if the river is missing. Muddy water often looks like land to the satellite."
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

def normalize(band):
    """Normalize band for RGB display"""
    band = band.astype(float)
    return (band - band.min()) / (band.max() - band.min())

def process_image(item):
    # Fetch bands
    href_blue = item.assets["B02"].href
    href_green = item.assets["B03"].href
    href_red = item.assets["B04"].href
    href_nir = item.assets["B08"].href

    # Read bands (downsampled 8x)
    with rasterio.open(href_red) as src:
        red = src.read(1, out_shape=(src.height // 8, src.width // 8))
    with rasterio.open(href_green) as src:
        green = src.read(1, out_shape=(src.height // 8, src.width // 8))
    with rasterio.open(href_blue) as src:
        blue = src.read(1, out_shape=(src.height // 8, src.width // 8))
    with rasterio.open(href_nir) as src:
        nir = src.read(1, out_shape=(src.height // 8, src.width // 8))

    np.seterr(divide='ignore', invalid='ignore')
    r, g, b, n = red.astype(float), green.astype(float), blue.astype(float), nir.astype(float)
    
    # Indices
    ndti = (r - g) / (r + g) 
    ndwi = (g - n) / (g + n) 
    
    # Create RGB Stack
    rgb = np.dstack((normalize(r), normalize(g), normalize(b))) * 3.5
    rgb = np.clip(rgb, 0, 1)
    
    # Get Metadata
    cloud_pct = item.properties.get("eo:cloud_cover", 0)
    
    return ndti, ndwi, rgb, item.datetime, cloud_pct

# --- MAIN APP LOGIC ---

if st.sidebar.button("Run Analysis", type="primary"):
    with st.spinner(f"🛰️ Scanning {selected_river}..."):
        items = fetch_satellite_data(bbox, year, max_cloud)
        
    if not items:
        st.error("No clear images found. Try increasing the 'Max Cloud Cover' slider.")
    else:
        st.success(f"Processing {len(items)} scenes...")
        
        progress_bar = st.progress(0)
        results = []
        
        for i, item in enumerate(items):
            try:
                ndti, ndwi, rgb, date, cloud = process_image(item)
                river_pixels = ndti[ndwi > mask_threshold]
                
                if len(river_pixels) > 50:
                    avg_turbidity = np.nanmean(river_pixels)
                    if -0.5 < avg_turbidity < 0.8:
                        results.append({"Date": date, "Turbidity": avg_turbidity})
            except:
                pass
            progress_bar.progress((i + 1) / len(items))
            
        if results:
            df = pd.DataFrame(results)
            df = df.sort_values("Date")
            
            # METRICS
            avg_annual = df["Turbidity"].mean()
            col1, col2, col3 = st.columns(3)
            col1.metric("Avg Turbidity", f"{avg_annual:.3f}")
            col2.metric("Usable Images", len(df))
            
            if avg_annual > 0.1: status = "CRITICAL (Heavy Sediment)"
            elif avg_annual > 0.0: status = "MODERATE (Visible Turbidity)"
            else: status = "CLEAR"
            col3.metric("River Status", status)

            st.divider()

            # LATEST MAP VIEW
            st.subheader(f"🗺️ Satellite View: {view_mode}")
            
            # Process latest image
            last_item = items[-1]
            ndti, ndwi, rgb, date, cloud_pct = process_image(last_item)
            date_str = date.strftime('%Y-%m-%d')
            
            col_map, col_info = st.columns([3, 1])
            
            with col_map:
                fig_map, ax = plt.subplots(figsize=(10, 8))
                
                if view_mode == "True Color (RGB)":
                    ax.imshow(rgb)
                    ax.set_title(f"True Color: {date_str} (Clouds: {cloud_pct}%)")
                    filename = f"TrueColor_{selected_river}_{date_str}.png"
                else:
                    masked_ndti = np.ma.masked_where(ndwi <= mask_threshold, ndti)
                    cmap = mcolors.LinearSegmentedColormap.from_list("galamsey", ["blue", "cyan", "yellow", "red", "brown"])
                    ax.imshow(masked_ndti, cmap=cmap, vmin=-0.1, vmax=0.3)
                    ax.set_title(f"Turbidity Heatmap: {date_str}")
                    filename = f"Heatmap_{selected_river}_{date_str}.png"
                
                ax.axis('off')
                st.pyplot(fig_map)
                
                # DOWNLOAD IMAGE BUTTON
                buf = io.BytesIO()
                fig_map.savefig(buf, format="png", bbox_inches='tight', dpi=150)
                buf.seek(0)
                
                st.download_button(
                    label=f"📥 Download {view_mode} Image",
                    data=buf,
                    file_name=filename,
                    mime="image/png"
                )
                
            with col_info:
                st.markdown("### 📝 Analysis Note")
                st.info(f"**Scene Metadata:**\n- **Date:** {date_str}\n- **Cloud Cover:** {cloud_pct}%")
                
                if view_mode == "True Color (RGB)":
                    st.markdown("""
                    **What you are seeing:**
                    This is the raw optical image.
                    - **Brown:** Suspended Sediment (Mud).
                    - **White:** Clouds.
                    - **Green:** Forest/Vegetation.
                    
                    *Use this to verify if the Heatmap is telling the truth.*
                    """)
                else:
                    st.markdown(f"""
                    **What you are seeing:**
                    A computed Index (NDTI) identifying pollution.
                    
                    - **Current Threshold:** {mask_threshold}
                    - **Brown/Red:** High pollution detected.
                    - **Missing River?** If the river is gone, it means the water is SO muddy the satellite thinks it is land. **Lower the Threshold slider.**
                    """)

            # TREND CHART
            st.divider()
            st.subheader(f"📉 Annual Trend ({year})")
            fig = px.line(df, x="Date", y="Turbidity", markers=True)
            fig.update_traces(line_color='#8B4513', line_width=3)
            fig.add_hrect(y0=0.1, y1=0.5, line_width=0, fillcolor="red", opacity=0.1, annotation_text="Heavy Galamsey")
            
            st.plotly_chart(fig, use_container_width=True)
            
            # DOWNLOAD DATA BUTTON
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Trend Data (CSV)",
                data=csv,
                file_name=f"turbidity_trend_{selected_river}_{year}.csv",
                mime="text/csv"
            )

        else:
            st.warning("No valid data points found.")

        st.divider()
st.markdown("<p style='text-align: center; color: #888888;'>© 2025 Agyei Darko | Virtual Catchment Laboratory</p>", unsafe_allow_html=True)