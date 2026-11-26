"""
Page: Sliding window correlation

Streamlit version (with Plotly graphics) of the sliding window correlation from the lectures:
the correlation between a weather property and a representative reservoir variable is computed
in a window that slides through time, with a selectable lag and window length.
  - Area and period: global selection in the sidebar (st.session_state)
  - Local choices: weather property, reservoir variable, lag (weeks) and window length (weeks)
  - Tab 1: the two weekly series and their sliding window correlation
  - Tab 2: the correlation over the whole period for every lag (which lag relates most?)
All data is weekly (Monday-Sunday), the resolution of the reservoir statistics.
"""
import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from analysis import (download_weather, load_locations, load_reservoirs, region_id_for,
                      reservoir_series, to_weekly)

st.title("Sliding Window Correlation")

N_LOCATIONS = 5   # random locations per area (keeps multi-year downloads within API limits)
WEATHER = {
    "temperature_2m": ("Temperature (weekly mean)", "°C"),
    "precipitation": ("Precipitation (weekly total)", "mm"),
    "snowfall": ("Snowfall (weekly total)", "cm"),
}
RESERVOIR = {
    "change": ("Weekly change in filling rate", "pp"),
    "level": ("Filling rate", "%"),
}

# ---------------------------------------------------------------------------
# Global selections (sidebar)
# ---------------------------------------------------------------------------
area_type, area_number = st.session_state.get("area", ("EL", 3))
region_id = region_id_for(area_type, area_number)
period_start, period_end = st.session_state.get("period", (dt.date(2024, 1, 1), dt.date(2024, 12, 31)))
end = min(period_end, dt.date.today() - dt.timedelta(days=7))   # ERA5 is published with a delay
start = period_start
st.write(f"Weekly data for **{region_id}**, **{start:%b %Y} – {end:%b %Y}** "
         "(change the area and period in the sidebar; a period of several years gives the "
         "most informative correlations).")


# ---------------------------------------------------------------------------
# Cached data loading
# ---------------------------------------------------------------------------
@st.cache_data(ttl=24 * 3600, show_spinner="Loading reservoir statistics from NVE...")
def get_reservoirs():
    return load_reservoirs()


@st.cache_data(ttl=24 * 3600, show_spinner="Downloading weather data from Open-Meteo...")
def get_weekly_weather(region_id, start, end):
    """Weekly weather of one area: mean temperature, total precipitation and snowfall."""
    hourly = download_weather(region_id, start.isoformat(), end.isoformat(),
                              locations=load_locations(), n_locations=N_LOCATIONS,
                              variables=list(WEATHER))
    return pd.concat([to_weekly(hourly["temperature_2m"]),
                      to_weekly(hourly[["precipitation", "snowfall"]], how="sum")], axis=1)


# Error handling: clear messages instead of crashes (missing data or API problems)
try:
    fill = reservoir_series(get_reservoirs(), area_type, area_number) * 100   # percent
except ValueError as e:          # e.g. VASS4, which has no reservoir statistics
    st.warning(f"{e} Please choose another area in the sidebar.")
    st.stop()
except Exception as e:
    st.error(f"The reservoir statistics could not be downloaded from NVE: {e}")
    st.stop()
try:
    weather = get_weekly_weather(region_id, start, end)
except Exception as e:
    st.error(f"The weather data could not be downloaded from Open-Meteo: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Local controls
# ---------------------------------------------------------------------------
c1, c2 = st.columns(2)
with c1:
    weather_var = st.selectbox("Weather property", list(WEATHER),
                               format_func=lambda v: WEATHER[v][0])
with c2:
    reservoir_var = st.selectbox(
        "Reservoir variable", list(RESERVOIR), format_func=lambda v: RESERVOIR[v][0],
        help="The weekly change shows how much the reservoirs fill or empty in a week, which "
             "reacts directly to the weather; the level mainly follows the yearly cycle.")
c3, c4 = st.columns(2)
with c3:
    lag = st.slider("Lag [weeks]", -12, 12, 0,
                    help="Positive lag: the weather is compared with the reservoir variable "
                         "this many weeks LATER (the weather leads).")
with c4:
    window = st.slider("Window length [weeks]", 4, 104, 26, step=2,
                       help="Number of weeks in each correlation window.")

# Weekly series on the same Monday labels, restricted to the period
target = fill.diff() if reservoir_var == "change" else fill
target = target.loc[pd.Timestamp(start):pd.Timestamp(end)].rename("reservoir")
# Shifting the weather forward by `lag` weeks puts the weather of week t next to the
# reservoir variable of week t + lag
driver = weather[weather_var].shift(lag).rename("weather")
data = pd.concat([target, driver], axis=1).dropna()

if len(data) < window + 2:
    st.warning(f"Only {len(data)} weeks with data: choose a longer period in the sidebar "
               f"or a shorter window (now {window} weeks).")
    st.stop()

# Correlation in a window of `window` weeks that slides one week at a time
# (center=True: each value is plotted in the middle of its window)
rolling_corr = data["reservoir"].rolling(window, center=True).corr(data["weather"])
overall = data["reservoir"].corr(data["weather"])

m1, m2, m3 = st.columns(3)
m1.metric("Correlation over the whole period", f"{overall:+.2f}")
m2.metric("Strongest positive window", f"{rolling_corr.max():+.2f}")
m3.metric("Strongest negative window", f"{rolling_corr.min():+.2f}")

w_label, w_unit = WEATHER[weather_var]
r_label, r_unit = RESERVOIR[reservoir_var]
tab_sliding, tab_lags = st.tabs(["Sliding window", "Correlation by lag"])

# ---------- TAB 1: the two series and the sliding window correlation ----------
with tab_sliding:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        row_heights=[0.55, 0.45], specs=[[{"secondary_y": True}], [{}]],
                        subplot_titles=[f"{r_label} and {w_label.lower()}"
                                        + (f" (weather shifted {lag:+d} weeks)" if lag else ""),
                                        f"Correlation in a {window}-week sliding window"])
    fig.add_trace(go.Scatter(x=data.index, y=data["reservoir"], name=r_label,
                             line=dict(color="#1d4ed8", width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.index, y=data["weather"], name=w_label,
                             line=dict(color="#ea580c", width=1.2)),
                  row=1, col=1, secondary_y=True)          # second y-axis: different units
    fig.add_trace(go.Scatter(x=rolling_corr.index, y=rolling_corr, name="Correlation",
                             line=dict(color="#15803d", width=2), fill="tozeroy",
                             fillcolor="rgba(21,128,61,0.15)"), row=2, col=1)
    fig.add_hline(y=0, line_color="black", line_width=1, row=2, col=1)
    fig.update_yaxes(title_text=f"{r_label} [{r_unit}]", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text=f"{w_label} [{w_unit}]", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Correlation", range=[-1, 1], row=2, col=1)
    # Legend centred below the charts, so it does not overlap the panel titles
    fig.update_layout(height=720, hovermode="x unified", margin=dict(t=60, b=80),
                      legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center",
                                  yanchor="top"))
    st.plotly_chart(fig, use_container_width=True)

# ---------- TAB 2: overall correlation for every lag ----------
with tab_lags:
    lags = range(-12, 13)
    by_lag = pd.Series(
        {k: target.corr(weather[weather_var].shift(k)) for k in lags}, name="correlation")
    best_lag = by_lag.abs().idxmax()
    fig = go.Figure(go.Bar(x=list(by_lag.index), y=by_lag.values,
                           marker_color=["#15803d" if k == lag else "#93c5fd" for k in lags]))
    fig.add_hline(y=0, line_color="black", line_width=1)
    fig.update_layout(title=f"Correlation over the whole period for each lag "
                            f"(selected lag in green)",
                      xaxis_title="Lag [weeks] (positive = weather leads)",
                      yaxis_title="Correlation", yaxis_range=[-1, 1], height=420)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"The strongest relation is at a lag of **{best_lag:+d} weeks** "
               f"(correlation {by_lag[best_lag]:+.2f}).")

with st.expander("About the method"):
    st.markdown(
        f"""
- **Data:** weekly filling rate (NVE Magasinstatistikk) and weekly weather (Open-Meteo ERA5,
  average of {N_LOCATIONS} random locations in the area), both on Monday-Sunday weeks.
- **Lag:** the weather series is shifted by the chosen number of weeks before the correlation is
  computed. With a positive lag, the weather of a week is compared with the reservoirs
  *later*, which is what matters for prediction (e.g. snowfall in winter and the filling in spring).
- **Sliding window:** the Pearson correlation is computed in a window of the chosen length that
  moves one week at a time; each value is drawn in the middle of its window. Changes in the
  correlation over time show when the weather and the reservoirs are strongly linked.
- **Correlation by lag:** the correlation over the whole period for every lag from -12 to +12 weeks.
"""
    )