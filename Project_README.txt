🇬🇭 Galamsey Sentinel Tracker

An operational remote-sensing dashboard for monitoring river turbidity in Ghana.

Overview

Illegal small-scale mining (Galamsey) poses a critical threat to water resources in Ghana (Pra, Ankobra, Birim basins). Traditional field monitoring is dangerous and expensive.
This tool uses Sentinel-2 Satellite Imagery and the Microsoft Planetary Computer API to provide near-real-time monitoring of river health. It calculates the Normalized Difference Turbidity Index (NDTI) to visualize sediment plumes and track water quality trends over time.


Features

Live Satellite Search: Queries the Sentinel-2 archive for specific river basins.
Automated Masking: Uses NDWI to separate water from dense forest/vegetation.
Time-Series Analysis: Plots turbidity trends to identify pollution events.
Interactive Dashboard: Built with Streamlit for easy use by non-coders.🛠️ 


Installation
Clone the repository:
git clone [https://github.com/YOUR_USERNAME/galamsey-sentinel.git](https://github.com/YOUR_USERNAME/galamsey-sentinel.git)
cd galamsey-sentinel

Install dependencies:
pip install -r requirements.txt

Run the Dashboard:
streamlit run dashboard.py


Methodology

The tool utilizes the Normalized Difference Turbidity Index (NDTI):$$ NDTI = \frac{Red - Green}{Red + Green} $$
High Values (>0.05): Indicate high suspended sediment (Mining/Runoff).
Low Values (<0.0): Indicate clear water.

🇬🇭 Focus Areas
Pra River (Twifo Praso)
Ankobra River (Prestea)
Birim River (Kyebi)
Offin River (Dunkwa)📄 

License

MIT License. Open for research and educational use.