"""
IND320 - Norwegian Energy Dashboard (Streamlit entry point)

Run locally (from the project folder) with:
    uv run streamlit run app.py

This file defines the navigation menu and the global area selector.
Every page lives in its own .py file and is executed by Streamlit when the
user selects it in the sidebar.
"""
import streamlit as st

# set_page_config must be the first Streamlit command that is executed.
st.set_page_config(page_title="IND320 Energy Dashboard", layout="wide")

# ---------------------------------------------------------------------------
# Global area selector
# ---------------------------------------------------------------------------
# The analysis pages (reservoir analysis and weather anomalies) work on one area at a
# time, and the weather data depends on the area chosen for the reservoir statistics.
# The selector is therefore global: it lives in the sidebar of the entry point, so it is
# shown on every page and keeps its value when the user moves between pages.
# Only EL and VASS areas are offered, because they have a matching weather region.
AREAS = {
    "NO1 – South-East Norway (price area)": ("EL", 1),
    "NO2 – South-West Norway (price area)": ("EL", 2),
    "NO3 – Central Norway (price area)": ("EL", 3),
    "NO4 – Northern Norway (price area)": ("EL", 4),
    "NO5 – Western Norway (price area)": ("EL", 5),
    "VASS1 – South-East Norway (watercourse area)": ("VASS", 1),
    "VASS2 – Western Norway (watercourse area)": ("VASS", 2),
    "VASS3 – Central Norway (watercourse area)": ("VASS", 3),
    "VASS4 – Northern Norway (watercourse area)": ("VASS", 4),
}

with st.sidebar:
    st.subheader("Area for the analyses")
    # key= stores the choice in st.session_state, so it survives page changes
    area_label = st.selectbox(
        "Reservoir area (also used for the weather data)",
        list(AREAS),
        index=2,                      # default: NO3, as in the notebook
        key="area_label",
    )
    st.caption("Used by the *Reservoir analysis* and *Weather anomalies* pages.")

# Make the selected area available to all pages as (area_type, area_number)
st.session_state["area"] = AREAS[area_label]

# ---------------------------------------------------------------------------
# Navigation menu
# ---------------------------------------------------------------------------
# st.navigation builds the sidebar menu from a dictionary:
#   - key   = section header shown in the sidebar ("" means no header)
#   - value = list of st.Page objects (file path, title shown in the menu, icon)
# Only the pages listed here appear in the menu.
pg = st.navigation(
    {
        "": [
            st.Page("home.py", title="Home", icon=":material/home:", default=True),
        ],
        "Reservoirs (NVE)": [
            st.Page("pages/2_Table.py", title="Overview table", icon=":material/table_chart:"),
            st.Page("pages/3_Plot.py", title="Trends", icon=":material/show_chart:"),
            st.Page("pages/5_Reservoir_Analysis.py", title="Seasonal analysis", icon=":material/insights:"),
        ],
        "Weather (Open-Meteo)": [
            st.Page("pages/6_Weather_Anomalies.py", title="Outliers and anomalies", icon=":material/thermostat:"),
        ],
        "Cross-border flows (ENTSO-E)": [
            st.Page("pages/4_Cross_Border_Flows.py", title="Cross-border flows", icon=":material/swap_horiz:"),
        ],
    }
)

# Run the page currently selected by the user
pg.run()