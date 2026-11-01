"""
Page: Weather anomalies

Outlier and anomaly detection on hourly ERA5 weather data (Open-Meteo API) for the area chosen
in the global sidebar selector, organised in tabs:
  - Outliers with Statistical Process Control on DCT high-pass filtered data (SPC)
  - Anomalies with the Local Outlier Factor (LOF)
The weather data is downloaded automatically and cached, so no separate download page is needed.
The analysis functions are shared with the notebook through analysis.py.
"""
import pandas as pd
import streamlit as st

from analysis import (download_weather, load_locations, lof_anomalies,
                      region_id_for, spc_outliers)

N_LOCATIONS = 20   # random locations per area: keeps the download fast and within API limits

st.title("Weather: Outliers and Anomalies")

# Area chosen in the global selector (app.py) -> weather region id, e.g. ('EL', 3) -> 'NO3'
area_type, area_number = st.session_state.get("area", ("EL", 3))
region_id = region_id_for(area_type, area_number)

# The year is a local setting: it only matters for the weather analyses on this page
year = st.selectbox("Year", list(range(2025, 1999, -1)), index=1)   # default 2024
st.write(f"Hourly ERA5 weather data for **{region_id}**, **{year}** "
         f"(average of {N_LOCATIONS} random locations; change the area in the sidebar).")


@st.cache_data
def get_locations():
    return load_locations()


# Cached per (region, year): each combination is downloaded only once
@st.cache_data(ttl=24 * 3600, show_spinner="Downloading weather data from Open-Meteo...")
def get_weather(region_id, year):
    return download_weather(region_id, f"{year}-01-01", f"{year}-12-31",
                            locations=get_locations(), n_locations=N_LOCATIONS)


try:
    weather = get_weather(region_id, year)
except Exception as e:   # e.g. no network or the daily API limit reached
    st.error(f"The weather data could not be downloaded: {e}")
    st.stop()

VARIABLES = {
    "precipitation": "Precipitation",
    "temperature_2m": "Temperature",
    "rain": "Rain",
    "snowfall": "Snowfall",
    "wind_speed_10m": "Wind speed",
}

tab_spc, tab_lof = st.tabs(["Outliers (SPC)", "Anomalies (LOF)"])

# ---------- TAB 1: SPC outliers ----------
with tab_spc:
    st.subheader("Outliers: Statistical Process Control")
    col1, col2, col3 = st.columns(3)
    with col1:
        spc_var = st.selectbox("Variable", list(VARIABLES), format_func=VARIABLES.get,
                               index=0, key="spc_var")   # default: precipitation
    with col2:
        cutoff_days = st.slider("DCT cut-off [days]", 7, 120, 30,
                                help="Variations slower than this period are treated as seasonal.")
    with col3:
        n_std = st.slider("Number of robust standard deviations", 1.5, 6.0, 3.0, step=0.5)

    fig, summary, outliers = spc_outliers(weather, variable=spc_var, cutoff_days=cutoff_days,
                                          n_std=n_std, region_label=f"({region_id}, {year})")
    st.pyplot(fig)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Outliers", summary["n_outliers"])
    m2.metric("Share of hours", f"{summary['outlier_share_%']} %")
    m3.metric("High / low", f"{summary['n_high']} / {summary['n_low']}")
    m4.metric("Robust SD", summary["robust_sd"])

    with st.expander("Largest outliers"):
        st.dataframe(outliers.sort_values(spc_var, ascending=False).head(20).round(3))

# ---------- TAB 2: LOF anomalies ----------
with tab_lof:
    st.subheader("Anomalies: Local Outlier Factor")
    col1, col2, col3 = st.columns(3)
    with col1:
        lof_var = st.selectbox("Variable", list(VARIABLES), format_func=VARIABLES.get,
                               index=1, key="lof_var")   # default: temperature
    with col2:
        contamination = st.slider("Proportion of anomalies [%]", 0.1, 5.0, 1.0, step=0.1) / 100
    with col3:
        n_neighbors = st.slider("Number of neighbours", 10, 200, 50, step=10)

    fig, summary, anomalies = lof_anomalies(weather, variable=lof_var, contamination=contamination,
                                            n_neighbors=n_neighbors,
                                            region_label=f"({region_id}, {year})")
    st.pyplot(fig)

    m1, m2, m3 = st.columns(3)
    m1.metric("Anomalies", summary["n_anomalies"])
    m2.metric("Share of hours", f"{summary['anomaly_share_%']} %")
    m3.metric("Max LOF score", summary["max_lof_score"])

    with st.expander("Most anomalous hours"):
        st.dataframe(anomalies.sort_values("lof_score", ascending=False).head(20))

# ---------- DATA SOURCE ----------
with st.expander("About the data and methods"):
    st.markdown(
        f"""
- **Source:** Open-Meteo Historical Weather API, hourly **ERA5** reanalysis.
- **Locations:** {N_LOCATIONS} random locations inside the selected area (drawn from 1000 random
  locations per area, based on the NVE Atlas shapefiles); the plots show their hourly average.
  A small subset keeps the download fast and within the free API limits.
- **Download:** automatic when an area or year is selected, and cached, so no separate
  download page is needed.
- **SPC:** a DCT high-pass filter removes the seasonal level; limits are the seasonal level
  ± n robust standard deviations (median absolute deviation) of the remaining variations.
- **LOF:** each hour (time and value) is compared with the density of its nearest neighbours;
  the given proportion of hours in the sparsest regions are marked as anomalies.
"""
    )