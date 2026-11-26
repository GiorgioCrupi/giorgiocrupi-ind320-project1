"""
Page: Reservoir overview

Joins the two former reservoir pages (overview table with LineChartColumn and trend plot)
into one page with two tabs:
  - Trends: interactive Plotly line chart, one line per area (one variable or all variables)
  - Table:  one row per variable, with a small trend line (LineChartColumn) per area
The period comes from the global sidebar selection (st.session_state), and the area selected
in the sidebar (or on the map) is highlighted with a thicker line.
Data source: NVE Magasinstatistikk public API.
"""
import datetime as dt

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.title("Reservoirs: Overview")

# Public NVE endpoint that returns the full weekly reservoir history as JSON (no API key needed)
NVE_URL = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligData"

AREA_TYPE_DESCRIPTIONS = {
    "EL": "Electricity price areas",
    "NO": "Norway as a whole",
    "VASS": "Watercourse areas",
}
# Numeric variables, with readable names for the menus and axis titles
VARIABLES = {
    "Fill_Rate": "Filling rate (0-1)",
    "Capacity_TWh": "Capacity (TWh)",
    "Filled_TWh": "Stored energy (TWh)",
    "Fill_Rate_Last_Week": "Filling rate last week (0-1)",
    "Fill_Rate_Change": "Change in filling rate (0-1)",
}


# st.cache_data: the API is called at most once a day; later reruns reuse the result
@st.cache_data(ttl=24 * 3600, show_spinner="Loading reservoir statistics from NVE...")
def load_data():
    # 1. Retrieve the reservoir statistics from the NVE API
    response = requests.get(NVE_URL, timeout=60)
    response.raise_for_status()   # stop with an error if the API does not answer correctly
    df = pd.DataFrame(response.json())

    # 2. Translate the Norwegian column names to English
    df = df.rename(columns={
        'dato_Id': 'Date_Id', 'omrType': 'Area_Type', 'omrnr': 'Area_Number',
        'iso_aar': 'Year', 'iso_uke': 'Week', 'fyllingsgrad': 'Fill_Rate',
        'kapasitet_TWh': 'Capacity_TWh', 'fylling_TWh': 'Filled_TWh',
        'neste_Publiseringsdato': 'Next_Publishing_Date',
        'fyllingsgrad_forrige_uke': 'Fill_Rate_Last_Week',
        'endring_fyllingsgrad': 'Fill_Rate_Change',
    })

    # 3. ISO year + ISO week -> date (Monday of the week), and a readable area name, e.g. "EL 3"
    df['Date'] = pd.to_datetime(df['Year'].astype(str) + '-' + df['Week'].astype(str) + '-1',
                                format='%G-%V-%u')
    df['Area'] = df['Area_Type'] + ' ' + df['Area_Number'].astype(str)

    # 4. The API returns the records unsorted, so sort them chronologically
    return df.sort_values(['Date', 'Area_Number']).reset_index(drop=True)


# Error handling: a clear message instead of a crash if the NVE API cannot be reached
try:
    df = load_data()
except requests.RequestException as e:
    st.error(f"The reservoir statistics could not be downloaded from NVE: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Selections: global period and area (sidebar), local area type and variable
# ---------------------------------------------------------------------------
start, end = st.session_state.get("period", (dt.date(2024, 1, 1), dt.date(2024, 12, 31)))
selected_type, selected_number = st.session_state.get("area", ("EL", 3))
selected_area = f"{selected_type} {selected_number}"

col1, col2 = st.columns(2)
with col1:
    # Local choice: which group of areas to compare. Default = type of the selected area.
    area_types = sorted(df['Area_Type'].unique())
    area_type = st.radio(
        "Area type",
        area_types,
        index=area_types.index(selected_type) if selected_type in area_types else 0,
        horizontal=True,
        format_func=lambda t: f"{t} – {AREA_TYPE_DESCRIPTIONS.get(t, '')}",
    )
with col2:
    variable = st.selectbox("Variable", ["All variables"] + list(VARIABLES),
                            format_func=lambda v: VARIABLES.get(v, v))

# Data of the chosen area type in the period chosen in the sidebar
df_period = df[(df['Area_Type'] == area_type)
               & (df['Date'] >= pd.Timestamp(start))
               & (df['Date'] <= pd.Timestamp(end))]
if df_period.empty:
    st.warning("No reservoir data in the selected period. Please choose another period in the sidebar.")
    st.stop()

areas = sorted(df_period['Area'].unique(), key=lambda a: int(a.split()[-1]))
st.caption(f"{len(df_period):,} weekly records for {len(areas)} {area_type} areas, "
           f"{start:%b %Y} – {end:%b %Y} (change the period in the sidebar).")


def highlight_selected(fig):
    """Thicker line for the area selected in the sidebar, thinner lines for the others."""
    fig.for_each_trace(lambda t: t.update(line_width=4 if t.name == selected_area else 1.5))
    return fig


tab_trends, tab_table = st.tabs(["Trends", "Table"])

# ---------- TAB 1: interactive trend chart ----------
with tab_trends:
    if variable == "All variables":
        # Long format (one row per date, area and variable) -> one panel per variable,
        # each with its own y-axis because the units differ (rates vs. TWh)
        long = df_period.melt(id_vars=['Date', 'Area'], value_vars=list(VARIABLES),
                              var_name='Variable', value_name='Value')
        long['Variable'] = long['Variable'].map(VARIABLES)
        fig = px.line(long, x='Date', y='Value', color='Area', facet_row='Variable',
                      category_orders={'Area': areas}, height=1100)
        fig.update_yaxes(matches=None, title=None)          # independent y-axes
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))   # panel titles
    else:
        fig = px.line(df_period, x='Date', y=variable, color='Area',
                      category_orders={'Area': areas},
                      markers=df_period['Date'].nunique() <= 60,   # show points for short periods
                      labels={variable: VARIABLES[variable], 'Date': 'Date'})
    fig.update_layout(legend_title_text="Area", hovermode="x unified")
    st.plotly_chart(highlight_selected(fig), use_container_width=True)
    if selected_type == area_type:
        st.caption(f"The thick line is the area selected in the sidebar ({selected_area}).")

# ---------- TAB 2: table with one small trend line per area ----------
with tab_table:
    # One row per variable; each cell holds the list of weekly values in the period,
    # which LineChartColumn draws as a small line
    rows = []
    for col in VARIABLES:
        row = {"Variable": VARIABLES[col]}
        for area in areas:
            row[area] = (df_period[df_period['Area'] == area].sort_values('Date')[col]
                         .dropna().astype(float).tolist())
        rows.append(row)

    column_config = {"Variable": st.column_config.TextColumn("Variable", width="medium")}
    for area in areas:
        column_config[area] = st.column_config.LineChartColumn(
            area, help=f"Weekly values of {area} in the selected period")
    st.dataframe(pd.DataFrame(rows), column_config=column_config, hide_index=True,
                 use_container_width=True)

# ---------- DATA SOURCE ----------
with st.expander("About the data"):
    st.markdown(
        """
- **Source:** NVE (Norwegian Water Resources and Energy Directorate), *Magasinstatistikk* public API.
- **Area types:** **EL** = electricity price areas, **NO** = Norway as a whole, **VASS** = watercourse areas.
- **Period:** chosen in the sidebar and shared with the other analysis pages.
- **Trends:** interactive Plotly chart (hover for values, drag to zoom, click the legend to hide areas).
- **Table:** one small trend line per area and variable (this replaces the former overview-table page).
- The API response is cached for 24 hours to keep the app fast.
"""
    )