"""
IND320 - Norwegian Energy Dashboard (Streamlit entry point)

Run locally (from the project folder) with:
    uv run streamlit run app.py

This file only defines the navigation menu. Every page lives in its own .py file
and is executed by Streamlit when the user selects it in the sidebar.
"""
import streamlit as st

# set_page_config must be the first Streamlit command that is executed.
# It sets the title shown in the browser tab and uses the full browser width ("wide").
st.set_page_config(page_title="IND320 Energy Dashboard", layout="wide")

# st.navigation builds the sidebar menu from a dictionary:
#   - key   = section header shown in the sidebar ("" means no header)
#   - value = list of st.Page objects (file path, title shown in the menu, icon)
# When st.navigation is used, Streamlit no longer adds the files in the pages/ folder
# automatically: only the pages listed here appear in the menu.
# The icons are Streamlit's built-in Material Symbols (":material/<name>:"),
# so no extra library is required.
pg = st.navigation(
    {
        "": [
            # default=True makes this the page shown when the app is opened
            st.Page("home.py", title="Home", icon=":material/home:", default=True),
        ],
        "Reservoirs (NVE)": [
            st.Page("pages/2_Table.py", title="Overview table", icon=":material/table_chart:"),
            st.Page("pages/3_Plot.py", title="Trends", icon=":material/show_chart:"),
        ],
        "Cross-border flows (ENTSO-E)": [
            st.Page("pages/4_Cross_Border_Flows.py", title="Cross-border flows", icon=":material/swap_horiz:"),
        ],
    }
)

# Run the page currently selected by the user
pg.run()