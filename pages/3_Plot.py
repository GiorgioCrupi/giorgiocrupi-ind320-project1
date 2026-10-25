"""
Page: Reservoirs - Trends

Interactive chart of the NVE reservoir data:
  - st.radio        -> area type (EL, NO, VASS); one line per area number of that type
  - st.select_slider -> range of months to load (default: the first month)
  - st.selectbox    -> one variable, or all variables in separate panels
Data source: NVE Magasinstatistikk public API (replaces the former reservoirs.csv file).
"""
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests

# Browser-tab title and full-width layout for this page
st.set_page_config(page_title="Interactive Plot", layout="wide")
st.title("Reservoirs: Trends")

# Public NVE endpoint that returns the full weekly reservoir history as JSON (no API key needed)
NVE_URL = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligData"

# Human-readable descriptions of the NVE area types, shown next to the radio buttons
AREA_TYPE_DESCRIPTIONS = {
    "EL": "Electricity price areas",
    "NO": "Norway as a whole",
    "VASS": "Watercourse areas",
}
numeric_columns = ['Fill_Rate', 'Capacity_TWh', 'Filled_TWh', 'Fill_Rate_Last_Week', 'Fill_Rate_Change']


# The NVE API has no date filter (its endpoints take no parameters), so the full series
# is downloaded once. st.cache_data with ttl=24h means the API is called at most once a day:
# Streamlit re-runs the script on every widget interaction, and later runs reuse the result.
@st.cache_data(ttl=24 * 3600)
def fetch_all_data():
    # 1. Retrieve the reservoir statistics from the API
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

    # 3. ISO year + ISO week -> real date (Monday of the week, '%G-%V-%u'),
    #    plus a "YYYY-MM" string used by the month slider
    df['Date'] = pd.to_datetime(df['Year'].astype(str) + '-' + df['Week'].astype(str) + '-1', format='%G-%V-%u')
    df['Month_Str'] = df['Date'].dt.strftime('%Y-%m')

    # 4. The API returns the records unsorted, so sort them chronologically
    return df.sort_values(['Date', 'Area_Number']).reset_index(drop=True)


# Second cache level: the data for each (month range, area type) chosen by the user is
# loaded once and stored separately, so moving the slider back to a range already viewed
# is instant. This is how the slider "controls the download range" of the page.
@st.cache_data
def load_range(start_month, end_month, area_type):
    df = fetch_all_data()
    mask = (
        (df['Month_Str'] >= start_month)
        & (df['Month_Str'] <= end_month)
        & (df['Area_Type'] == area_type)
    )
    return df[mask]


all_df = fetch_all_data()

# --- WIDGET 1: radio buttons for the area type ---
# format_func only changes the displayed label; the returned value is still "EL", "NO" or "VASS"
area_type = st.radio(
    "Select area type:",
    sorted(all_df['Area_Type'].unique()),
    horizontal=True,
    format_func=lambda t: f"{t} – {AREA_TYPE_DESCRIPTIONS.get(t, '')}",
)

# --- WIDGET 2: select slider controlling which months are loaded ---
# Passing a tuple as value turns the slider into a range slider with two handles.
# (first, first) makes the first available month the default selection.
unique_months = sorted(all_df.loc[all_df['Area_Type'] == area_type, 'Month_Str'].unique())
selected_months = st.select_slider(
    "Select the range of months to load:",
    options=unique_months,
    value=(unique_months[0], unique_months[0]),
)

# Load only the selected range for the selected area type
df_filtered = load_range(selected_months[0], selected_months[1], area_type)
area_numbers = sorted(df_filtered['Area_Number'].unique())
st.caption(f"Loaded {len(df_filtered):,} weekly records for {len(area_numbers)} {area_type} areas.")

# --- WIDGET 3: selectbox for the column (one variable or all of them) ---
selected_col = st.selectbox("Choose a column to plot:", ['All Columns'] + numeric_columns)

st.write("---")   # horizontal separator line

period = f"{selected_months[0]} to {selected_months[1]}"
# With only a few weeks selected, show the individual points so it is clear the data is weekly
show_markers = df_filtered['Date'].nunique() <= 60


def plot_column(ax, col):
    """Draw one line per area number for the variable `col` on the Matplotlib axis `ax`."""
    for area in area_numbers:
        d = df_filtered[df_filtered['Area_Number'] == area].sort_values('Date')
        ax.plot(d['Date'], d[col], linewidth=1.5,
                marker='o' if show_markers else None, markersize=3,
                label=f"{area_type} {area}")
    ax.grid(True, alpha=0.3)


if selected_col == 'All Columns':
    # The variables have different units (rates vs. TWh), so instead of one crowded chart
    # each variable gets its own panel (3 x 2 grid), keeping its real scale.
    fig, axes = plt.subplots(3, 2, figsize=(14, 11), sharex=True)
    axes = axes.flatten()   # 2-D grid of axes -> simple list
    for ax, col in zip(axes, numeric_columns):
        plot_column(ax, col)
        ax.set_title(col, fontsize=12, fontweight='bold')
        ax.set_ylabel(col)
    axes[-1].axis('off')   # 5 variables in a 3x2 grid: hide the empty sixth panel
    # One shared legend for the whole figure, taken from the first panel
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower right', ncol=2, title="Area")
    fig.suptitle(f"All Columns by {area_type} area ({period})", fontsize=16, fontweight='bold')
    for ax in axes[3:5]:   # bottom panels carry the date labels
        ax.tick_params(axis='x', rotation=45)
else:
    # Single variable: one chart, one line per area
    fig, ax = plt.subplots(figsize=(12, 6))
    plot_column(ax, selected_col)
    ax.set_title(f"{selected_col} by {area_type} area ({period})", fontsize=16, fontweight='bold')
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel(selected_col, fontsize=12)
    ax.legend(loc='best', title="Area")
    plt.xticks(rotation=45)

plt.tight_layout()
st.pyplot(fig)   # render the Matplotlib figure in the Streamlit page

# Collapsible box documenting the data source and the loading strategy
with st.expander("About the data"):
    st.markdown(
        """
- **Source:** NVE (Norwegian Water Resources and Energy Directorate), *Magasinstatistikk* public API.
- **Area types:** **EL** = electricity price areas, **NO** = Norway as a whole, **VASS** = watercourse areas.
- **Loading:** the NVE API has no date filter, so the full weekly series is downloaded once and
  cached for 24 hours; the month slider then determines which range of data is loaded into the chart.
- **Chart:** one line per area number; "All Columns" shows one panel per variable in its own unit.
"""
    )