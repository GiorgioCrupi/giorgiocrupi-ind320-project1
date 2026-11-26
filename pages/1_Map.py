"""
Page: Map

Interactive map of Norway with the GeoJSON outlines of one of the three types of areas used in
Magasinstatistikk (EL price areas, VASS watercourse areas, NO = Norway as a whole).
  - The areas are coloured (transparently) by the reservoir filling rate or by a weather property
    (weekly mean temperature, weekly total precipitation or snowfall) in the week chosen with a
    slider inside the period selected in the sidebar.
  - A click on an area selects it: its outline becomes thick and red, and the selection is stored
    in st.session_state, so all other pages (and the sidebar) use the clicked area.
  - Below the map, a Plotly line chart shows the chosen variable for the selected area in the period.
The GeoJSON files were created from the NVE Atlas shapefiles in notebooks/project_4.ipynb.
"""
import datetime as dt
import json
from pathlib import Path

import branca.colormap as cm
import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from analysis import download_weather, load_locations, load_reservoirs, region_id_for, to_weekly

st.title("Map of the areas")

SHAPE_DIR = Path(__file__).resolve().parent.parent / "shapefiles"
N_LOCATIONS = 5   # random locations per area for the map's weather values (fast, within API limits)

AREA_TYPES = {"EL": "Price areas (EL)", "VASS": "Watercourse areas (VASS)",
              "NO": "Norway as a whole (NO)"}
# Variables that can colour the map: (label, unit, colours from low to high)
COLOUR_BY = {
    "fill_rate": ("Reservoir filling rate", "%", ["#fee2e2", "#93c5fd", "#1d4ed8"]),
    "temperature_2m": ("Temperature (weekly mean)", "°C", ["#2563eb", "#f3f4f6", "#dc2626"]),
    "precipitation": ("Precipitation (weekly total)", "mm", ["#f0f9ff", "#38bdf8", "#1e3a8a"]),
    "snowfall": ("Snowfall (weekly total)", "cm", ["#f8fafc", "#a5b4fc", "#4338ca"]),
}

# ---------------------------------------------------------------------------
# Global selections from the sidebar (area and period)
# ---------------------------------------------------------------------------
selected_type, selected_number = st.session_state.get("area", ("EL", 3))
period_start, period_end = st.session_state.get("period", (dt.date(2024, 1, 1), dt.date(2024, 12, 31)))
# Weather data is hourly and ERA5 is published with a delay: use at most the last 12 months
end = min(period_end, dt.date.today() - dt.timedelta(days=7))
start = max(period_start, end - dt.timedelta(days=365))


# ---------------------------------------------------------------------------
# Cached data loading
# ---------------------------------------------------------------------------
@st.cache_data(ttl=24 * 3600, show_spinner="Loading reservoir statistics from NVE...")
def get_reservoirs():
    return load_reservoirs()


@st.cache_data
def get_geojson(area_type):
    """GeoJSON outlines of one area type (created in the notebook from the shapefiles)."""
    with open(SHAPE_DIR / f"areas_{area_type}.geojson", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=24 * 3600, show_spinner="Downloading weather data for the map...")
def get_weekly_weather(region_id, start, end):
    """Weekly weather of one area: mean temperature, total precipitation and snowfall."""
    hourly = download_weather(region_id, start.isoformat(), end.isoformat(),
                              locations=load_locations(), n_locations=N_LOCATIONS,
                              variables=["temperature_2m", "precipitation", "snowfall"])
    return pd.concat([to_weekly(hourly["temperature_2m"]),
                      to_weekly(hourly[["precipitation", "snowfall"]], how="sum")], axis=1)


try:
    reservoirs = get_reservoirs()
except Exception as e:   # error handling: no crash if the NVE API cannot be reached
    st.error(f"The reservoir statistics could not be downloaded from NVE: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Local controls: area type, colour variable and week
# ---------------------------------------------------------------------------
c1, c2 = st.columns(2)
with c1:
    type_options = list(AREA_TYPES)
    area_type = st.radio("Areas", type_options, horizontal=True, format_func=AREA_TYPES.get,
                         index=type_options.index(selected_type) if selected_type in type_options else 0)
with c2:
    # Norway as a whole has no weather region, so only the filling rate is offered there
    colour_options = ["fill_rate"] if area_type == "NO" else list(COLOUR_BY)
    colour_by = st.selectbox("Colour by", colour_options, format_func=lambda v: COLOUR_BY[v][0])

# Weeks (Mondays, as in the NVE data) inside the period
weeks = [pd.Timestamp(d) for d in sorted(
    reservoirs.loc[(reservoirs["Date"] >= pd.Timestamp(start))
                   & (reservoirs["Date"] <= pd.Timestamp(end)), "Date"].unique())]
if not weeks:
    st.warning("No data in the selected period. Please choose another period in the sidebar.")
    st.stop()
week = st.select_slider("Week", options=weeks, value=weeks[-1],
                        format_func=lambda d: f"Week {d:%V}, {d:%d %b %Y}")

# ---------------------------------------------------------------------------
# Values of all areas of the chosen type (weekly time series, one column per area)
# ---------------------------------------------------------------------------
geojson = get_geojson(area_type)
area_ids = [f["properties"]["area_id"] for f in geojson["features"]]   # e.g. "EL 3"

if colour_by == "fill_rate":
    subset = reservoirs[reservoirs["Area_Type"] == area_type].copy()
    subset["area_id"] = subset["Area_Type"] + " " + subset["Area_Number"].astype(str)
    series = (subset.pivot_table(index="Date", columns="area_id", values="Fill_Rate") * 100)
    series = series.loc[pd.Timestamp(start):pd.Timestamp(end)]
else:
    columns = {}
    progress = st.progress(0.0, text="Weather data for the map")
    for i, area_id in enumerate(area_ids):
        number = int(area_id.split()[-1])
        try:
            columns[area_id] = get_weekly_weather(region_id_for(area_type, number), start, end)[colour_by]
        except Exception as e:   # one failing area should not break the whole map
            st.warning(f"Weather data for {area_id} could not be downloaded: {e}")
        progress.progress((i + 1) / len(area_ids), text=f"Weather data for the map ({area_id})")
    progress.empty()
    series = pd.DataFrame(columns)

values = series.reindex([week]).iloc[0] if week in series.index else pd.Series(dtype=float)
label, unit, colours = COLOUR_BY[colour_by]

# Colour scale over the whole period, so the colours can be compared from week to week
valid = series.stack().dropna()
vmin, vmax = (float(valid.min()), float(valid.max())) if len(valid) else (0.0, 1.0)
colormap = cm.LinearColormap(colours, vmin=vmin, vmax=vmax if vmax > vmin else vmin + 1,
                             caption=f"{label} [{unit}]")

selected_id = f"{selected_type} {selected_number}"
for feature in geojson["features"]:   # text shown in the tooltip of each area
    v = values.get(feature["properties"]["area_id"])
    feature["properties"]["value_text"] = "no data" if v is None or pd.isna(v) else f"{v:.1f} {unit}"


def style(feature):
    """Transparent fill by value; thick red outline for the selected area."""
    area_id = feature["properties"]["area_id"]
    v = values.get(area_id)
    is_selected = area_id == selected_id
    return {
        "fillColor": "#d1d5db" if v is None or pd.isna(v) else colormap(v),   # grey = no data
        "fillOpacity": 0.6,
        "color": "#dc2626" if is_selected else "#334155",
        "weight": 5 if is_selected else 1,
    }


# ---------------------------------------------------------------------------
# Map (left) and information about the selected area (right)
# ---------------------------------------------------------------------------
col_map, col_info = st.columns([3, 1])
with col_map:
    m = folium.Map(location=[65.0, 15.0], zoom_start=4, tiles="OpenStreetMap")   # free background map, no API key needed
    folium.GeoJson(
        geojson,
        style_function=style,
        highlight_function=lambda f: {"weight": 3, "fillOpacity": 0.8},   # effect on mouse-over
        tooltip=folium.GeoJsonTooltip(fields=["name", "value_text"], aliases=["Area", label]),
    ).add_to(m)
    colormap.add_to(m)   # colour scale (legend) in the corner of the map
    # st_folium shows the map and returns the last clicked area ("last_active_drawing")
    map_state = st_folium(m, height=560, use_container_width=True,
                          returned_objects=["last_active_drawing"], key=f"map_{area_type}")

# A click on an area: store it as the new global selection (only EL and VASS can be selected,
# because they have weather regions). "last_map_click" makes sure each click is handled once.
clicked = (map_state or {}).get("last_active_drawing")
if clicked:
    props = clicked["properties"]
    click = (props["area_type"], int(props["area_number"]))
    if click != st.session_state.get("last_map_click"):
        st.session_state["last_map_click"] = click
        if click[0] in ("EL", "VASS") and click != (selected_type, selected_number):
            st.session_state["pending_area"] = click   # applied by app.py before the sidebar
            st.rerun()

with col_info:
    st.markdown(f"**Selected area**  \n{selected_id}")
    if area_type == selected_type:
        v = values.get(selected_id)
        st.metric(f"{label}, week {week:%V}", "no data" if v is None or pd.isna(v) else f"{v:.1f} {unit}")
    else:
        st.caption(f"The selected area is not a {area_type} area: click an area on the map "
                   "to select it.")
    st.caption("Click an area to select it for all pages. Grey areas have no data "
               "(e.g. VASS4 has no reservoir statistics).")
    if area_type == "NO":
        st.caption("Norway as a whole can be coloured, but not selected (it has no weather region).")

# ---------------------------------------------------------------------------
# Line chart of the selected area in the period, with the chosen week marked
# ---------------------------------------------------------------------------
if area_type == selected_type and selected_id in series.columns:
    line = series[selected_id].dropna()
    fig = go.Figure(go.Scatter(x=line.index, y=line, mode="lines+markers", name=selected_id,
                               line=dict(color="#1d4ed8"), marker=dict(size=4)))
    fig.add_vline(x=week, line_dash="dash", line_color="#dc2626")   # week shown on the map
    fig.update_layout(title=f"{label} – {selected_id}, {start:%b %Y} – {end:%b %Y}",
                      xaxis_title="Week", yaxis_title=f"{label} [{unit}]", height=350)
    st.plotly_chart(fig, use_container_width=True)

with st.expander("About the map"):
    st.markdown(
        f"""
- **Outlines:** GeoJSON files converted from the NVE Atlas shapefiles in the project notebook
  (EL = price areas, VASS = watercourse areas, NO = union of all price areas).
- **Filling rate:** NVE Magasinstatistikk, weekly values in percent.
- **Weather:** Open-Meteo ERA5, average of {N_LOCATIONS} random locations per area, aggregated to
  weeks (Monday–Sunday): mean temperature, total precipitation and snowfall.
- **Period:** from the sidebar (at most the last 12 months for the hourly weather data); the colour
  scale covers the whole period, so weeks can be compared.
- **Selection:** a click on an EL or VASS area selects it for all pages (thick red outline).
"""
    )