"""
Page: Home

Landing page of the dashboard. It briefly explains the three groups of pages
(Explore, Anomalies, Relations and prediction) and links to every page,
in addition to the sidebar menu defined in app.py.
"""
import streamlit as st

st.title("Norwegian Energy Dashboard")

# st.write renders Markdown, so **text** is shown in bold
st.write(
    "An interactive dashboard for **IND320**, combining Norwegian hydropower reservoir statistics "
    "(NVE), the weather that feeds the reservoirs (Open-Meteo), cross-border electricity flows "
    "(ENTSO-E) and exchange rates (Norges Bank)."
)
st.info("Choose the **area** and **period** in the sidebar (or click an area on the map): "
        "the selection is used by all analysis pages.", icon=":material/info:")

st.write("---")   # horizontal separator line

# One column per group of pages; everything inside "with colX:" is placed in that column.
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader(":blue[:material/explore: Explore]")
    st.write("Look at the data: map of the areas, reservoir statistics, "
             "cross-border flows and exchange rates.")
    # st.page_link creates a clickable link; the path must match st.Page in app.py
    st.page_link("pages/1_Map.py", label="Map", icon=":material/map:")
    st.page_link("pages/2_Table.py", label="Reservoir table", icon=":material/table_chart:")
    st.page_link("pages/3_Plot.py", label="Reservoir trends", icon=":material/show_chart:")
    st.page_link("pages/4_Cross_Border_Flows.py", label="Cross-border flows",
                 icon=":material/swap_horiz:")
    st.page_link("pages/7_Exchange_Rates.py", label="Exchange rates",
                 icon=":material/currency_exchange:")

with col2:
    st.subheader(":orange[:material/warning: Anomalies]")
    st.write("Find unusual behaviour: seasonal decomposition of the reservoir filling, "
             "and outliers and anomalies in the weather data.")
    st.page_link("pages/5_Reservoir_Analysis.py", label="Reservoir seasonality",
                 icon=":material/insights:")
    st.page_link("pages/6_Weather_Anomalies.py", label="Weather outliers and anomalies",
                 icon=":material/thermostat:")

with col3:
    st.subheader(":green[:material/trending_up: Relations and prediction]")
    st.write("Relate the weather to the reservoir filling, and forecast the filling "
             "of the coming months.")
    st.page_link("pages/8_Sliding_Correlation.py", label="Sliding window correlation",
                 icon=":material/compare_arrows:")
    st.page_link("pages/9_Forecast.py", label="Forecast", icon=":material/trending_up:")

st.write("---")

# st.caption shows small, grey helper text
st.caption("Use the sidebar menu or the links above to navigate between pages.")