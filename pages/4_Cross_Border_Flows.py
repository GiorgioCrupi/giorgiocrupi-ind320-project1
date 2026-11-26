"""
Page: Cross-border flows

Hourly physical electricity flows on three Norwegian interconnections, read from MongoDB Atlas.
The page is split into two columns (st.columns):
  - left : st.radio (connection) + st.selectbox (year) -> donut chart of yearly export vs. import
  - right: st.pills (any set of months)                 -> line chart of hourly flows
Both charts are interactive Plotly charts (part 4), replacing the former matplotlib figures.
An st.expander below the columns documents the data source.

Data pipeline (see notebooks/project_2.ipynb):
ENTSO-E API -> Spark -> Cassandra -> Spark (hourly aggregation) -> MongoDB -> this page.
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pymongo import MongoClient, errors

st.title("Cross-Border Electricity Flows")

# Interconnections stored in MongoDB.
# key   = label shown on the radio buttons
# value = (Norwegian price area, foreign price area), as used in the "from_area"/"to_area" fields
CONNECTIONS = {
    "NO1 ↔ SE3 (Oslo – Stockholm)": ("NO_1", "SE_3"),
    "NO2 ↔ DK1 (Skagerrak)": ("NO_2", "DK_1"),
    "NO2 ↔ DE_LU (NordLink)": ("NO_2", "DE_LU"),
}
# Same colours for export and import in both charts
COLOURS = {"Export from Norway": "#1d4ed8", "Import to Norway": "#ea580c"}


# st.cache_resource keeps ONE MongoDB connection open and shares it across all reruns
# and users (cache_resource is meant for objects such as database connections).
@st.cache_resource
def get_collection():
    # The connection string (with password) is read from Streamlit secrets:
    # locally from .streamlit/secrets.toml (excluded from Git), and on streamlit.io from the
    # app's "Secrets" settings, so credentials never appear in the code or on GitHub.
    # Generous timeouts make the connection more tolerant of slow networks.
    client = MongoClient(
        st.secrets["mongo"]["uri"],
        serverSelectionTimeoutMS=30_000,
        connectTimeoutMS=30_000,
        socketTimeoutMS=120_000,
    )
    return client["ind320_energy_data"]["crossborder_flows_hourly"]


# Only the data of the selected connection is downloaded (about 35,000 documents instead of
# all 105,000), using a MongoDB query on the "direction" field.
# st.cache_data stores the result for 24 hours separately for each connection.
@st.cache_data(ttl=24 * 3600, show_spinner="Loading data from MongoDB...")
def load_flows(no_area, foreign_area):
    directions = [f"{no_area} → {foreign_area}", f"{foreign_area} → {no_area}"]
    query = {"direction": {"$in": directions}}
    # Projection: only the needed fields ({"_id": 0} excludes MongoDB's internal id)
    projection = {"_id": 0, "from_area": 1, "to_area": 1, "direction": 1, "timestamp": 1,
                  "energy_mwh": 1}

    # A download can be interrupted by an unstable network, so it is retried up to 3 times
    for attempt in range(3):
        try:
            docs = list(get_collection().find(query, projection, batch_size=5_000))
            break
        except errors.PyMongoError:
            if attempt == 2:
                raise

    df = pd.DataFrame(docs)
    # Timestamps are stored in UTC in MongoDB; convert them to Norwegian local time for display
    df["timestamp"] = (pd.to_datetime(df["timestamp"], utc=True)
                       .dt.tz_convert("Europe/Oslo").dt.tz_localize(None))
    # Helper columns used by the year selector and the month pills
    df["year"] = df["timestamp"].dt.year
    df["month"] = df["timestamp"].dt.strftime("%Y-%m")
    # Flows that start in a Norwegian area ("NO_...") are exports
    df["flow_type"] = np.where(df["from_area"].str.startswith("NO"),
                               "Export from Norway", "Import to Norway")
    return df


# ---------------------------------------------------------------------------
# Error handling: clear messages instead of crashes
# ---------------------------------------------------------------------------
try:
    has_mongo_secret = "mongo" in st.secrets
except Exception:            # no secrets file at all
    has_mongo_secret = False
if not has_mongo_secret:
    st.error("The MongoDB connection is not configured (missing `[mongo]` in the Streamlit "
             "secrets), so the cross-border flows cannot be loaded.")
    st.stop()

# Split the page into two equally wide columns
left, right = st.columns(2)

# ---------- LEFT COLUMN: donut chart ----------
with left:
    st.subheader("Yearly energy exchange")

    # --- WIDGET: radio buttons for the connection ---
    connection_label = st.radio("Select a connection:", list(CONNECTIONS))
    no_area, foreign_area = CONNECTIONS[connection_label]

    try:
        conn_df = load_flows(no_area, foreign_area)
    except Exception as e:   # e.g. no network, wrong password or database not reachable
        st.error(f"The data could not be loaded from MongoDB: {e}")
        st.stop()
    if conn_df.empty:
        st.warning("No data found for this connection.")
        st.stop()

    # --- WIDGET: selectbox for the year (a local choice: it only matters on this page) ---
    # 2025 is preselected because it is the only complete calendar year in the data
    years = sorted(conn_df["year"].unique())
    year = st.selectbox("Select a year:", years, index=years.index(2025) if 2025 in years else 0)

    # Total energy per direction in the selected year: each row is the energy of one hour
    # in MWh, so the sum is the yearly energy; dividing by 1,000,000 converts MWh to TWh.
    totals = (conn_df[conn_df["year"] == year]
              .groupby(["flow_type", "direction"], as_index=False)["energy_mwh"].sum())
    totals["TWh"] = totals["energy_mwh"] / 1e6

    # Donut chart (a pie chart with a hole); hovering shows the exact energy
    fig = px.pie(totals, values="TWh", names="flow_type", color="flow_type",
                 color_discrete_map=COLOURS, hole=0.45,
                 hover_data=["direction"], title=f"{no_area} ↔ {foreign_area} in {year}")
    fig.update_traces(textinfo="percent+label", texttemplate="%{label}<br>%{percent:.1%}",
                      hovertemplate="%{label}<br>%{customdata[0]}<br>%{value:.2f} TWh"
                                    "<extra></extra>")
    fig.update_layout(showlegend=False,
                      annotations=[dict(text=f"{totals['TWh'].sum():.1f}<br>TWh",
                                        showarrow=False, font_size=18)])
    st.plotly_chart(fig, use_container_width=True)

    # The data covers Oct 2024 - Sep 2026, so 2024 and 2026 are partial years
    if year != 2025:
        st.caption("Note: only 2025 is a complete calendar year in the data (Oct 2024 – Sep 2026).")

# ---------- RIGHT COLUMN: line chart ----------
with right:
    st.subheader("Hourly flows")

    # January of the selected year is the default; if missing, the first month in the data
    month_options = sorted(conn_df["month"].unique())
    default_month = f"{year}-01" if f"{year}-01" in month_options else month_options[0]

    # --- WIDGET: pills with multi-selection, so any set of months can be chosen ---
    selected_months = st.pills("Select months to include:", month_options,
                               selection_mode="multi", default=[default_month])

    if not selected_months:
        # Avoid an empty chart when every pill is deselected
        st.info("Select at least one month to display the line chart.")
    else:
        line_df = conn_df[conn_df["month"].isin(selected_months)]
        # Wide table: one column per flow type, one row per hour. Reindexing to a continuous
        # hourly time axis inserts empty values between non-consecutive months (e.g. Jan and
        # Jun), so Plotly breaks the line there instead of drawing a misleading straight line.
        wide = line_df.pivot_table(index="timestamp", columns="flow_type", values="energy_mwh")
        wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="h"))

        fig = go.Figure()
        for flow_type in wide.columns:
            direction = line_df.loc[line_df["flow_type"] == flow_type, "direction"].iloc[0]
            fig.add_trace(go.Scatter(x=wide.index, y=wide[flow_type], mode="lines",
                                     name=f"{flow_type}: {direction}",
                                     line=dict(color=COLOURS[flow_type], width=1)))
        fig.update_layout(title=f"Hourly flows {no_area} ↔ {foreign_area}",
                          xaxis_title="Date", yaxis_title="MWh per hour", hovermode="x unified",
                          legend=dict(orientation="h", y=1.02, x=1, xanchor="right",
                                      yanchor="bottom"))
        st.plotly_chart(fig, use_container_width=True)

# ---------- DATA SOURCE (collapsible box below the columns) ----------
with st.expander("About the data"):
    st.markdown(
        """
- **Source:** ENTSO-E Transparency Platform, *physical cross-border flows*, retrieved with the `entsoe-py` client.
- **Period:** October 2024 – September 2026.
- **Processing:** the data was written to **Cassandra** with Spark, extracted again with Spark,
  aggregated to **hourly values** (MWh per hour), and stored in **MongoDB Atlas**,
  which this page reads from (only the selected connection is downloaded).
- **Export** = flow from the Norwegian area to the foreign area; **Import** = the opposite direction.
- **Charts:** interactive Plotly charts (hover for values, drag to zoom, click the legend to hide a line).
"""
    )