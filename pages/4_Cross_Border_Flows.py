"""
Page: Cross-border flows

Hourly physical electricity flows on three Norwegian interconnections, read from MongoDB Atlas.
The page is split into two columns (st.columns):
  - left : st.radio (connection) + st.selectbox (year) -> pie chart of yearly export vs. import
  - right: st.pills (any set of months)                 -> line chart of hourly flows
An st.expander below the columns documents the data source.

Data pipeline (see notebooks/project_2.ipynb):
ENTSO-E API -> Spark -> Cassandra -> Spark (hourly aggregation) -> MongoDB -> this page.
"""
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pymongo import MongoClient

# Browser-tab title and full-width layout for this page
st.set_page_config(page_title="Cross-Border Flows", layout="wide")
st.title("Cross-Border Electricity Flows")

# Interconnections stored in MongoDB.
# key   = label shown on the radio buttons
# value = (Norwegian price area, foreign price area), as used in the "from_area"/"to_area" fields
CONNECTIONS = {
    "NO1 ↔ SE3 (Oslo – Stockholm)": ("NO_1", "SE_3"),
    "NO2 ↔ DK1 (Skagerrak)": ("NO_2", "DK_1"),
    "NO2 ↔ DE_LU (NordLink)": ("NO_2", "DE_LU"),
}


# st.cache_resource keeps ONE MongoDB connection open and shares it across all reruns
# and users (cache_resource is meant for objects such as database connections).
@st.cache_resource
def get_collection():
    # The connection string (with password) is read from Streamlit secrets:
    # locally from .streamlit/secrets.toml (excluded from Git), and on streamlit.io from the
    # app's "Secrets" settings, so credentials never appear in the code or on GitHub.
    client = MongoClient(st.secrets["mongo"]["uri"])
    return client["ind320_energy_data"]["crossborder_flows_hourly"]


# st.cache_data stores the downloaded DataFrame for 24 hours, so the ~105,000 documents are
# fetched from MongoDB only once instead of on every widget interaction.
@st.cache_data(ttl=24 * 3600)
def load_flows():
    # {"_id": 0} excludes MongoDB's internal id field, which is not needed here
    docs = list(get_collection().find({}, {"_id": 0}))
    df = pd.DataFrame(docs)
    # Timestamps are stored in UTC in MongoDB; convert them to Norwegian local time for display
    # and drop the time-zone information so Matplotlib shows local clock times
    df["timestamp"] = (
        pd.to_datetime(df["timestamp"], utc=True)
        .dt.tz_convert("Europe/Oslo")
        .dt.tz_localize(None)
    )
    # Helper columns used by the year selector and the month pills
    df["year"] = df["timestamp"].dt.year
    df["month"] = df["timestamp"].dt.strftime("%Y-%m")
    return df


df = load_flows()

# Split the page into two equally wide columns
left, right = st.columns(2)

# ---------- LEFT COLUMN: pie chart ----------
with left:
    st.subheader("Yearly energy exchange")

    # --- WIDGET: radio buttons for the connection ---
    connection_label = st.radio("Select a connection:", list(CONNECTIONS))
    no_area, foreign_area = CONNECTIONS[connection_label]

    # --- WIDGET: selectbox for the year (a different control than the radio buttons) ---
    # 2025 is preselected because it is the only complete calendar year in the data
    years = sorted(df["year"].unique())
    year = st.selectbox("Select a year:", years, index=years.index(2025) if 2025 in years else 0)

    # Keep only the two directions of the selected connection
    conn_df = df[
        ((df["from_area"] == no_area) & (df["to_area"] == foreign_area)) |
        ((df["from_area"] == foreign_area) & (df["to_area"] == no_area))
    ].copy()
    # Label each direction: flows that start in a Norwegian area ("NO_...") are exports
    conn_df["flow_type"] = np.where(
        conn_df["from_area"].str.startswith("NO"), "Export from Norway", "Import to Norway"
    )

    # Total energy per direction in the selected year.
    # Each row is the energy of one hour in MWh, so the sum is the yearly energy;
    # dividing by 1,000,000 converts MWh to TWh.
    totals_twh = (
        conn_df[conn_df["year"] == year]
        .groupby(["flow_type", "direction"])["energy_mwh"].sum() / 1e6
    )
    total = totals_twh.sum()

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pie(
        totals_twh.values,
        labels=[f"{ft}\n({d})" for ft, d in totals_twh.index],
        # autopct receives the percentage of each slice; we also show the value in TWh
        autopct=lambda p: f"{p:.1f}%\n({p * total / 100:.2f} TWh)",
        startangle=90,
    )
    ax.set_title(f"{no_area} ↔ {foreign_area} in {year}")
    st.pyplot(fig)

    # The data covers Oct 2024 - Sep 2026, so 2024 and 2026 are partial years
    if year != 2025:
        st.caption("Note: only 2025 is a complete calendar year in the data (Oct 2024 – Sep 2026).")

# ---------- RIGHT COLUMN: line chart ----------
with right:
    st.subheader("Hourly flows")

    # January of the selected year is the default (as in the Jupyter Notebook);
    # if it is not available, the first month in the data is used instead
    month_options = sorted(conn_df["month"].unique())
    default_month = f"{year}-01" if f"{year}-01" in month_options else month_options[0]

    # --- WIDGET: pills with multi-selection, so any set of months can be chosen ---
    selected_months = st.pills(
        "Select months to include:",
        month_options,
        selection_mode="multi",
        default=[default_month],
    )

    if not selected_months:
        # Avoid an empty chart when every pill is deselected
        st.info("Select at least one month to display the line chart.")
    else:
        line_df = conn_df[conn_df["month"].isin(selected_months)]
        colors = {"Export": "tab:blue", "Import": "tab:orange"}

        fig, ax = plt.subplots(figsize=(7, 5))
        # One line per direction of the connection selected in the left column
        for from_area, to_area, flow_type in [
            (no_area, foreign_area, "Export"),
            (foreign_area, no_area, "Import"),
        ]:
            direction = f"{from_area} → {to_area}"
            series = line_df[line_df["direction"] == direction].sort_values("timestamp")
            # Plot each month separately so that non-consecutive months (e.g. Jan and Jun)
            # are not joined by a misleading straight line. Only the first piece gets a
            # legend label, so each direction appears once in the legend.
            for i, (_, part) in enumerate(series.groupby("month")):
                ax.plot(
                    part["timestamp"], part["energy_mwh"],
                    color=colors[flow_type], linewidth=0.8,
                    label=f"{flow_type}: {direction}" if i == 0 else None,
                )

        ax.set_title(f"Hourly flows {no_area} ↔ {foreign_area}")
        ax.set_xlabel("Date")
        ax.set_ylabel("MWh per hour")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %Y"))   # e.g. "05 Jan 2025"
        ax.grid(alpha=0.3)
        ax.legend(loc="upper right")
        fig.autofmt_xdate()   # rotate the date labels so they do not overlap
        st.pyplot(fig)

# ---------- DATA SOURCE (collapsible box below the columns) ----------
with st.expander("About the data"):
    st.markdown(
        """
- **Source:** ENTSO-E Transparency Platform, *physical cross-border flows*, retrieved with the `entsoe-py` client.
- **Period:** October 2024 – September 2026.
- **Processing:** the data was written to **Cassandra** with Spark, extracted again with Spark,
  aggregated to **hourly values** (MWh per hour), and stored in **MongoDB Atlas**,
  which this page reads from.
- **Export** = flow from the Norwegian area to the foreign area; **Import** = the opposite direction.
"""
    )