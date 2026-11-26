"""
Page: Forecast

Forecast of the weekly reservoir filling rate with River's SNARIMAX (dynamic forecasting).
  - Area: global selection (sidebar or map).
  - Training timeframe: the training data ends at the end of the period chosen in the sidebar
    (the same period as the map), and the history length chooses how far back it starts.
    If the end of the period lies in the past, the following weeks are known, so the forecast
    can be compared with what really happened.
  - All model parameters and the exogenous variables are selectable; the defaults are the best
    setting found in the tests in project_4.ipynb.
  - The result is shown as a Plotly animation (the forecast appears week by week), optionally
    with a confidence band from quantile regression (bonus exercise).
"""
import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis import (BEST_SETTINGS, CURRENCY_COLUMNS, WEATHER_COLUMNS, download_exchange_rates,
                      download_weather, forecast_filling, load_locations, load_reservoirs,
                      region_id_for, reservoir_series, to_weekly)

st.title("Forecast of the Reservoir Filling")

N_LOCATIONS = 5   # random locations per area for the weather inputs
EXOGENOUS = {
    "temperature_2m": "Temperature (weekly mean)",
    "precipitation": "Precipitation (weekly total)",
    "snowfall": "Snowfall (weekly total)",
    "eur_nok": "EUR/NOK exchange rate",
    "usd_nok": "USD/NOK exchange rate",
}

# ---------------------------------------------------------------------------
# Global selections (sidebar / map)
# ---------------------------------------------------------------------------
area_type, area_number = st.session_state.get("area", ("EL", 3))
region_id = region_id_for(area_type, area_number)
period_start, period_end = st.session_state.get("period", (dt.date(2024, 1, 1), dt.date(2024, 12, 31)))


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
                              variables=WEATHER_COLUMNS)
    return pd.concat([to_weekly(hourly["temperature_2m"]),
                      to_weekly(hourly[["precipitation", "snowfall"]], how="sum")], axis=1)


@st.cache_data(ttl=24 * 3600, show_spinner="Downloading exchange rates from Norges Bank...")
def get_weekly_rates(start, end):
    rates = download_exchange_rates(start.isoformat(), end.isoformat())
    return to_weekly(rates).rename(columns={"EUR": "eur_nok", "USD": "usd_nok"})


# The forecast is cached: the same settings give the result immediately the second time
@st.cache_data(show_spinner=False)
def run_forecast(data, settings, horizon, end, quantile=None):
    return forecast_filling(data, horizon=horizon, end=end, quantile=quantile, **settings)


# Target variable; error handling for areas without reservoir statistics (e.g. VASS4)
try:
    fill = reservoir_series(get_reservoirs(), area_type, area_number) * 100   # percent
except ValueError as e:
    st.warning(f"{e} Please choose another area in the sidebar or on the map.")
    st.stop()
except Exception as e:
    st.error(f"The reservoir statistics could not be downloaded from NVE: {e}")
    st.stop()

# Last training week: the last week with data up to the end of the sidebar period
train_weeks = fill.index[fill.index <= pd.Timestamp(period_end)]
if len(train_weeks) == 0:
    st.warning("No reservoir data before the end of the selected period.")
    st.stop()
end_week = train_weeks[-1]

st.write(f"Weekly filling rate of **{area_type} {area_number}**. The training data ends on "
         f"**{end_week:%d %b %Y}**, the end of the period selected in the sidebar (same timeframe "
         "as the map); the history length below sets how far back it starts.")

# ---------------------------------------------------------------------------
# Interface: all parameters in a form (the model only runs when the button is pressed)
# ---------------------------------------------------------------------------
col_params, col_plot = st.columns([1, 3])
with col_params:
    with st.form("forecast_settings"):
        st.markdown("**Timeframe**")
        horizon = st.slider("Forecast horizon [weeks]", 4, 52, 13)
        history_weeks = st.slider("History length [weeks]", 104, 416,
                                  BEST_SETTINGS["history_weeks"], step=52,
                                  help="Number of weeks before the end of the period used for training.")

        st.markdown("**SNARIMAX parameters**")
        c1, c2, c3 = st.columns(3)
        p = c1.number_input("p", 0, 4, BEST_SETTINGS["p"], help="Autoregressive order (past weeks)")
        d = c2.number_input("d", 0, 1, BEST_SETTINGS["d"], help="Differencing")
        q = c3.number_input("q", 0, 4, BEST_SETTINGS["q"], help="Moving-average order (past errors)")
        c4, c5, c6 = st.columns(3)
        sp = c4.number_input("P", 0, 2, BEST_SETTINGS["sp"], help="Seasonal AR order")
        sd = c5.number_input("D", 0, 1, BEST_SETTINGS["sd"], help="Seasonal differencing")
        sq = c6.number_input("Q", 0, 2, BEST_SETTINGS["sq"], help="Seasonal MA order")
        m = st.number_input("Season length m [weeks]", 1, 52, BEST_SETTINGS["m"])
        learning_rate = st.select_slider("Learning rate (SGD)", [0.005, 0.01, 0.02, 0.03, 0.05],
                                         value=BEST_SETTINGS["learning_rate"])

        st.markdown("**Exogenous variables**")
        exogenous = st.multiselect("Data sources", list(EXOGENOUS), format_func=EXOGENOUS.get,
                                   default=list(BEST_SETTINGS["exogenous"]))
        show_band = st.checkbox("Confidence band (5–95 %, quantile loss)", value=True)
        st.form_submit_button("Run forecast", type="primary", use_container_width=True)
    st.caption("Defaults = best setting from the tests in the project notebook.")

settings = dict(history_weeks=history_weeks, exogenous=tuple(exogenous), p=p, d=d, q=q, m=m,
                sp=sp, sd=sd, sq=sq, learning_rate=learning_rate)

# ---------------------------------------------------------------------------
# Weekly dataset: target + only the exogenous data sources that were selected
# ---------------------------------------------------------------------------
data_start = (end_week - pd.Timedelta(weeks=history_weeks + 1)).date()
data_end = min((end_week + pd.Timedelta(weeks=horizon + 1)).date(),
               dt.date.today() - dt.timedelta(days=7))
parts = [fill.rename("fill_rate")]
try:
    if any(c in WEATHER_COLUMNS for c in exogenous):
        parts.append(get_weekly_weather(region_id, data_start, data_end))
    if any(c in CURRENCY_COLUMNS for c in exogenous):
        parts.append(get_weekly_rates(data_start, data_end))
except Exception as e:
    st.error(f"An exogenous data source could not be downloaded: {e}")
    st.stop()
data = pd.concat(parts, axis=1)
# Training rows need all selected inputs; weeks after the end keep the actual filling rate
needed = ["fill_rate"] + list(exogenous)
data = pd.concat([data.loc[:end_week].dropna(subset=needed), data.loc[end_week:].iloc[1:]])

# ---------------------------------------------------------------------------
# Forecast (with a spinner while the model trains) and optional confidence band
# ---------------------------------------------------------------------------
try:
    with st.spinner("Training SNARIMAX week by week and forecasting..."):
        fc = run_forecast(data, settings, horizon, end_week)
        if show_band:
            lower = run_forecast(data, settings, horizon, end_week, quantile=0.05)["forecast"]
            upper = run_forecast(data, settings, horizon, end_week, quantile=0.95)["forecast"]
            # keep the band around the forecast (quantile models are trained separately)
            lower = pd.concat([lower, fc["forecast"]], axis=1).min(axis=1)
            upper = pd.concat([upper, fc["forecast"]], axis=1).max(axis=1)
except ValueError as e:   # e.g. too little history for the chosen season length
    st.warning(str(e))
    st.stop()

# ---------------------------------------------------------------------------
# Plotly animation: the forecast appears week by week (Play button)
# ---------------------------------------------------------------------------
observed = fill.loc[end_week - pd.Timedelta(weeks=78):end_week]
actual_after = fc["actual"].dropna()
start_point = pd.Series([observed.iloc[-1]], index=[end_week])   # connect forecast to the data


def frame_traces(k):
    """Traces of animation frame k: the band and the forecast for the first k weeks."""
    f = pd.concat([start_point, fc["forecast"].iloc[:k]])
    traces = []
    if show_band:
        lo = pd.concat([start_point, lower.iloc[:k]])
        hi = pd.concat([start_point, upper.iloc[:k]])
        traces.append(go.Scatter(x=list(hi.index) + list(lo.index[::-1]),
                                 y=list(hi.values) + list(lo.values[::-1]),
                                 fill="toself", fillcolor="rgba(220,38,38,0.15)",
                                 line=dict(width=0), name="5–95 % band", hoverinfo="skip"))
    traces.append(go.Scatter(x=f.index, y=f.values, mode="lines+markers", name="Forecast",
                             line=dict(color="#dc2626", dash="dash", width=2.5),
                             marker=dict(size=5)))
    return traces


fig = go.Figure(
    data=[go.Scatter(x=observed.index, y=observed.values, name="Observed (training)",
                     line=dict(color="#1f2937", width=2))]
         + ([go.Scatter(x=actual_after.index, y=actual_after.values, name="Actual (after training)",
                        line=dict(color="#16a34a", width=2))] if len(actual_after) else [])
         + frame_traces(len(fc)),
)
n_static = len(fig.data) - len(frame_traces(1))   # traces that do not change between frames
fig.frames = [go.Frame(data=frame_traces(k), name=str(k),
                       traces=list(range(n_static, len(fig.data))))
              for k in range(1, len(fc) + 1)]
fig.update_layout(
    title=f"{area_type} {area_number}: {horizon}-week forecast of the filling rate",
    xaxis_title="Week", yaxis_title="Filling rate (%)", yaxis_range=[0, 100], height=560,
    hovermode="x unified", legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
    updatemenus=[dict(type="buttons", x=0.0, y=1.12, xanchor="left", direction="left",
                      buttons=[dict(label="▶ Play", method="animate",
                                    args=[None, dict(frame=dict(duration=250, redraw=True),
                                                     fromcurrent=False, transition=dict(duration=0))]),
                               dict(label="⏸ Pause", method="animate",
                                    args=[[None], dict(mode="immediate",
                                                       frame=dict(duration=0, redraw=False))])])],
    sliders=[dict(active=len(fc) - 1, x=0.1, len=0.9, y=-0.02,
                  currentvalue=dict(prefix="Forecast week: "),
                  steps=[dict(label=str(k), method="animate",
                              args=[[str(k)], dict(mode="immediate", frame=dict(duration=0, redraw=True))])
                         for k in range(1, len(fc) + 1)])],
)
fig.add_vline(x=end_week, line_dash="dot", line_color="grey")   # end of the training data

with col_plot:
    st.plotly_chart(fig, use_container_width=True)

    # Metrics: error on the known weeks (if any) and the forecast at the end of the horizon
    m1, m2, m3 = st.columns(3)
    m1.metric(f"Forecast in {horizon} weeks ({fc.index[-1]:%d %b %Y})", f"{fc['forecast'].iloc[-1]:.1f} %",
              f"{fc['forecast'].iloc[-1] - observed.iloc[-1]:+.1f} pp from now")
    known = fc.dropna(subset=["actual"])
    if len(known):
        mae = (known["forecast"] - known["actual"]).abs().mean()
        naive = fill.shift(52).reindex(known.index)
        m2.metric(f"MAE on {len(known)} known weeks", f"{mae:.2f} pp")
        m3.metric("MAE seasonal naive (baseline)", f"{(naive - known['actual']).abs().mean():.2f} pp")
    else:
        m2.caption("The forecast weeks lie in the future, so no error can be computed yet. "
                   "Choose an earlier end of the period in the sidebar to test the model.")

    table = fc.rename(columns={"forecast": "Forecast (%)", "actual": "Actual (%)"})
    if show_band:
        table.insert(1, "Lower 5 % (%)", lower)
        table.insert(2, "Upper 95 % (%)", upper)
    with st.expander("Table of forecast values"):
        st.dataframe(table.round(1), use_container_width=True)

with st.expander("About the model"):
    st.markdown(
        """
- **Model:** River `SNARIMAX`, an online version of SARIMAX. It learns one week at a time and
  forecasts recursively (dynamic forecasting): each predicted week is used as input for the next.
- **Defaults:** the best setting from the backtests in the project notebook (312 weeks of history,
  AR(1) + seasonal differencing with m = 52, learning rate 0.03, no exogenous variables).
- **Exogenous variables:** weekly weather (Open-Meteo ERA5) and exchange rates (Norges Bank).
  Their future values are unknown, so the forecast uses the weekly climatology (weather) and the
  last known value (exchange rates).
- **Confidence band (bonus):** two extra models are trained with the quantile loss
  (`optim.losses.Quantile`, alpha = 0.05 and 0.95), so they predict the 5 % and 95 % quantiles.
- **Test:** if the end of the sidebar period lies in the past, the weeks after it are known and
  the forecast is compared with the actual values and with the seasonal naive baseline.
"""
    )