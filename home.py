"""
Page: Home

Landing page of the dashboard. It briefly explains the two data sources and offers
direct links to the other pages (in addition to the sidebar menu defined in app.py).
"""
import streamlit as st

st.title("Norwegian Energy Dashboard")

# st.write renders Markdown, so **text** is shown in bold
st.write(
    "An interactive dashboard for **IND320**, combining Norwegian hydropower reservoir statistics "
    "with cross-border electricity flows between Norway and its neighbours."
)

st.write("---")   # horizontal separator line

# st.columns splits the page into side-by-side columns;
# everything written inside a "with colX:" block is placed in that column.
col1, col2 = st.columns(2)

with col1:
    # Material icons can also be used inside text and headers
    st.subheader(":material/water_drop: Reservoirs")
    st.write(
        "Weekly reservoir statistics from **NVE (Magasinstatistikk API)**, available for "
        "electricity price areas, Norway as a whole and watercourse areas."
    )
    # st.page_link creates a clickable link to another page of the app.
    # The path must match the one used in st.Page (app.py).
    st.page_link("pages/2_Table.py", label="Overview table", icon=":material/table_chart:")
    st.page_link("pages/3_Plot.py", label="Trends", icon=":material/show_chart:")

with col2:
    st.subheader(":material/electric_bolt: Cross-border flows")
    st.write(
        "Hourly physical electricity flows on three major Norwegian interconnections, from "
        "**ENTSO-E**, processed with Spark and Cassandra and stored in MongoDB."
    )
    st.page_link("pages/4_Cross_Border_Flows.py", label="Cross-border flows", icon=":material/swap_horiz:")

st.write("---")

# st.caption shows small, grey helper text
st.caption("Use the sidebar menu or the links above to navigate between pages.")