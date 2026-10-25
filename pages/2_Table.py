"""
Page: Reservoirs - Overview Table

Shows one row per variable of the NVE reservoir data. For the selected area type,
the table contains one small trend line (LineChartColumn) per area number, showing
the weekly values of the first available month.
Data source: NVE Magasinstatistikk public API (replaces the former reservoirs.csv file).
"""
import streamlit as st
import pandas as pd
import requests

# Browser-tab title and full-width layout for this page
st.set_page_config(page_title="Data Table", layout="wide")
st.title("Reservoirs: Overview Table")

# Public NVE endpoint that returns the full weekly reservoir history as JSON (no API key needed)
NVE_URL = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligData"


# st.cache_data stores the return value of the function. Streamlit re-runs the whole script
# every time the user interacts with a widget, so without caching the API would be called on
# every click. With ttl=24h the API is called at most once a day; later runs reuse the result.
@st.cache_data(ttl=24 * 3600)
def load_data():
    # 1. Retrieve the reservoir statistics directly from the NVE Magasinstatistikk API
    response = requests.get(NVE_URL, timeout=60)
    response.raise_for_status()   # stop with a clear error if the API does not answer correctly
    df = pd.DataFrame(response.json())   # list of JSON records -> DataFrame

    # 2. Translate the Norwegian column names to English
    column_translation = {
        'dato_Id': 'Date_Id', 'omrType': 'Area_Type', 'omrnr': 'Area_Number',
        'iso_aar': 'Year', 'iso_uke': 'Week', 'fyllingsgrad': 'Fill_Rate',
        'kapasitet_TWh': 'Capacity_TWh', 'fylling_TWh': 'Filled_TWh',
        'neste_Publiseringsdato': 'Next_Publishing_Date',
        'fyllingsgrad_forrige_uke': 'Fill_Rate_Last_Week',
        'endring_fyllingsgrad': 'Fill_Rate_Change'
    }
    df.rename(columns=column_translation, inplace=True)

    # 3. Convert ISO year + ISO week to a real date (the Monday of that week, '%G-%V-%u'),
    #    and add a "YYYY-MM" string used to select months
    df['Date'] = pd.to_datetime(df['Year'].astype(str) + '-' + df['Week'].astype(str) + '-1', format='%G-%V-%u')
    df['Month_Str'] = df['Date'].dt.strftime('%Y-%m')

    # 4. The API returns the records unsorted, so sort them chronologically
    #    (otherwise the trend lines would zig-zag)
    return df.sort_values(['Date', 'Area_Number']).reset_index(drop=True)


df = load_data()

# Numeric variables shown as rows of the table
numeric_columns = ['Fill_Rate', 'Capacity_TWh', 'Filled_TWh', 'Fill_Rate_Last_Week', 'Fill_Rate_Change']

# Human-readable descriptions of the NVE area types, shown next to the radio buttons
AREA_TYPE_DESCRIPTIONS = {
    "EL": "Electricity price areas",
    "NO": "Norway as a whole",
    "VASS": "Watercourse areas",
}

# --- WIDGET: radio buttons for the area type ---
# st.radio returns the selected value. format_func only changes the label that is displayed
# (e.g. "EL - Electricity price areas"); the returned value is still "EL".
area_types = sorted(df['Area_Type'].unique())
area_type = st.radio(
    "Select area type:",
    area_types,
    horizontal=True,
    format_func=lambda t: f"{t} – {AREA_TYPE_DESCRIPTIONS.get(t, '')}",
)

df_type = df[df['Area_Type'] == area_type]

# Isolate the first available month for the selected area type
first_month = df_type['Month_Str'].min()
df_first_month = df_type[df_type['Month_Str'] == first_month]
area_numbers = sorted(df_first_month['Area_Number'].unique())

st.write(f"### Trend Analysis for the First Month: {first_month} ({area_type}, {len(area_numbers)} areas)")

# Build the table: one row per variable, one column per area number.
# Each cell contains a list of weekly values, which LineChartColumn draws as a small line.
summary_data = []
for col in numeric_columns:
    row = {"Variable Name": col}
    for area in area_numbers:
        values = (
            df_first_month[df_first_month['Area_Number'] == area]
            .sort_values('Date')[col]
            .dropna()          # missing values would break the small chart
            .astype(float)     # plain floats are required by LineChartColumn
            .tolist()
        )
        row[f"Area {area}"] = values
    summary_data.append(row)

summary_df = pd.DataFrame(summary_data)

# column_config tells st.dataframe how to display each column:
# TextColumn for the variable name, LineChartColumn (a small line chart) for each area.
column_config = {"Variable Name": st.column_config.TextColumn("Column Name", width="medium")}
for area in area_numbers:
    column_config[f"Area {area}"] = st.column_config.LineChartColumn(
        f"{area_type} {area}",   # column header shown in the table
        help=f"Weekly values in {first_month} for {area_type} area {area}",   # tooltip
    )

st.dataframe(summary_df, column_config=column_config, hide_index=True, use_container_width=True)

# st.expander creates a collapsible box, used here to document the data source
with st.expander("About the data"):
    st.markdown(
        """
- **Source:** NVE (Norwegian Water Resources and Energy Directorate), *Magasinstatistikk* public API.
- **Content:** weekly reservoir statistics (filling rate, capacity, stored energy) for each area.
- **Area types:** **EL** = electricity price areas (NO1–NO5), **NO** = Norway as a whole,
  **VASS** = watercourse areas.
- **Table:** one row per variable; each trend line shows the weekly values of the first
  available month for one area.
- The API response is cached for 24 hours to keep the app fast.
"""
    )