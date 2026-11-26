"""
analysis.py - shared analysis functions for the IND320 project (parts 3 and 4).

The same functions are developed and tested in notebooks/project_3.ipynb.
They are collected here so that the Streamlit pages can import them
(`from analysis import ...`) instead of copying the code.
Part 4: all figures are interactive Plotly figures (shown with st.plotly_chart),
replacing the static matplotlib figures of part 3.

Contents
--------
- Locations and regions : load_locations, region_id_for
- Weather (Open-Meteo)  : make_openmeteo_client, download_weather
- Outliers / anomalies  : spc_outliers (DCT + SPC), lof_anomalies (Local Outlier Factor)
- Exchange rates (NB)   : download_exchange_rates, to_weekly
- Reservoir statistics  : load_reservoirs, reservoir_series,
                          stl_decomposition, reservoir_spectrogram
"""
import json
import os
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Locations and regions
# ---------------------------------------------------------------------------

# 1000 random locations per region, created in the notebook from the NVE Atlas shapefiles
LOCATIONS_FILE = Path(__file__).resolve().parent / "shapefiles" / "locations.geojson"


def load_locations(path=LOCATIONS_FILE):
    """Read the random locations (region_id, region_type, longitude, latitude).

    The GeoJSON file is read as plain JSON, so the app does not need geopandas.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return pd.DataFrame([feature["properties"] for feature in data["features"]])


def region_id_for(area_type, area_number):
    """Translate a reservoir-statistics area into the region id used for the weather data.

    ('EL', 3) -> 'NO3'   (electricity price area)
    ('VASS', 1) -> 'VASS1' (watercourse area)
    ('NO', 0) -> None    (Norway as a whole: no weather region)
    """
    if area_type == "EL":
        return f"NO{area_number}"
    if area_type == "VASS":
        return f"VASS{area_number}"
    return None


# ---------------------------------------------------------------------------
# Weather data from Open-Meteo (ERA5 reanalysis)
# ---------------------------------------------------------------------------

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_VARIABLES = ["temperature_2m", "precipitation", "rain", "snowfall", "wind_speed_10m"]


def make_openmeteo_client(cache_path=None):
    """Open-Meteo client as generated on open-meteo.com: HTTP cache + automatic retries."""
    import openmeteo_requests
    import requests_cache
    from retry_requests import retry

    if cache_path is None:   # a writable temporary folder works both locally and online
        cache_path = os.path.join(tempfile.gettempdir(), "openmeteo_http_cache")
    cache_session = requests_cache.CachedSession(cache_path, expire_after=-1)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.5)
    return openmeteo_requests.Client(session=retry_session)


def download_weather(region_id, start_date, end_date, locations, client=None,
                     n_locations=50, variables=WEATHER_VARIABLES, batch_size=10,
                     pause_seconds=15, seed=42, cache_dir=None, force_refresh=False,
                     progress=None):
    """Download hourly ERA5 weather data for a region and return the regional average.

    region_id     : 'NO1'...'NO5' or 'VASS1'...'VASS4' (looked up in `locations`)
    start_date    : first day, 'YYYY-MM-DD'
    end_date      : last day, 'YYYY-MM-DD'
    locations     : DataFrame from load_locations()
    n_locations   : number of the region's random locations to use (Open-Meteo limits)
    batch_size    : locations per API request
    pause_seconds : pause between requests, used only for large downloads
    cache_dir     : optional folder for a local copy of the result
    progress      : optional function progress(done, total), e.g. for a progress bar
    """
    var_tag = "-".join(v.split("_")[0] for v in variables)
    cache_file = None
    if cache_dir is not None:
        cache_file = Path(cache_dir) / f"{region_id}_{start_date}_{end_date}_{n_locations}_{var_tag}.pkl"
        if cache_file.exists() and not force_refresh:
            return pd.read_pickle(cache_file)

    client = client or make_openmeteo_client()

    # Look up the region's locations and pick a reproducible random subset
    region_locations = locations[locations.region_id == region_id]
    if region_locations.empty:
        raise ValueError(f"Unknown region: {region_id}")
    chosen = region_locations.sample(n=min(n_locations, len(region_locations)), random_state=seed)

    # Open-Meteo weighs a request as locations × days/14 × variables/10 (600 per minute
    # for free use). Small downloads need no pause between batches.
    n_days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days + 1
    total_weight = len(chosen) * n_days / 14 * len(variables) / 10
    if total_weight < 500:
        pause_seconds = 0

    frames = []
    for start in range(0, len(chosen), batch_size):
        batch = chosen.iloc[start:start + batch_size]
        params = {
            "latitude": batch.latitude.tolist(),     # several locations in one request
            "longitude": batch.longitude.tolist(),
            "start_date": start_date,
            "end_date": end_date,
            "hourly": variables,
            "models": "era5",
            "timezone": "UTC",
        }
        responses = client.weather_api(ARCHIVE_URL, params=params)

        # One response per location: build an hourly DataFrame for each
        for response in responses:
            hourly = response.Hourly()
            times = pd.date_range(
                start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
                end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
                freq=pd.Timedelta(seconds=hourly.Interval()),
                inclusive="left",
            )
            values = {var: hourly.Variables(i).ValuesAsNumpy() for i, var in enumerate(variables)}
            frames.append(pd.DataFrame(values, index=times))

        done = min(start + batch_size, len(chosen))
        if progress is not None:
            progress(done, len(chosen))
        if done < len(chosen) and pause_seconds:
            time.sleep(pause_seconds)   # stay below the per-minute API limit

    # Regional average over all locations, in Norwegian local time
    regional = pd.concat(frames).groupby(level=0).mean()
    regional.index = regional.index.tz_convert("Europe/Oslo")
    regional.index.name = "time"

    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        regional.to_pickle(cache_file)
    return regional


UNITS = {"temperature_2m": "°C", "precipitation": "mm", "rain": "mm", "snowfall": "cm",
         "wind_speed_10m": "km/h"}


# ---------------------------------------------------------------------------
# Outliers: Statistical Process Control on DCT high-pass filtered data
# ---------------------------------------------------------------------------

def spc_outliers(weather, variable="precipitation", cutoff_days=30, n_std=3.0, region_label=""):
    """Detect outliers with Statistical Process Control on DCT high-pass filtered data.

    weather      : DataFrame with an hourly DatetimeIndex (e.g. from download_weather)
    variable     : column to analyse (default 'precipitation')
    cutoff_days  : variations slower than this period are treated as seasonal and removed
    n_std        : number of robust standard deviations for the SPC limits
    Returns (figure, summary dict, DataFrame of outliers).
    """
    from scipy.fft import dct, idct

    series = weather[variable].astype(float)
    x = series.to_numpy()
    n = len(x)
    step_hours = (series.index[1] - series.index[0]).total_seconds() / 3600

    # 1. DCT high-pass filter. DCT-II coefficient k has a period of about 2·n·step / k,
    #    so coefficients below k_cut describe variations slower than cutoff_days.
    coeffs = dct(x, type=2, norm="ortho")
    k_cut = int(np.ceil(2 * n * step_hours / (cutoff_days * 24)))
    low_coeffs = coeffs.copy()
    low_coeffs[k_cut:] = 0
    seasonal = idct(low_coeffs, type=2, norm="ortho")   # slow, seasonal level
    satv = x - seasonal                                  # seasonally adjusted variations

    # 2. Robust statistics of the SATV over the whole period
    centre = np.median(satv)
    sigma = 1.4826 * np.median(np.abs(satv - centre))    # MAD scaled to a standard deviation
    if sigma == 0:                                       # safety net for constant data
        sigma = satv.std()

    # 3. SPC limits on the original scale and outlier detection
    lower = seasonal + centre - n_std * sigma
    upper = seasonal + centre + n_std * sigma
    is_outlier = (x < lower) | (x > upper)

    outliers = pd.DataFrame({
        variable: x[is_outlier],
        "lower_limit": lower[is_outlier],
        "upper_limit": upper[is_outlier],
        "type": np.where(x[is_outlier] > upper[is_outlier], "high", "low"),
    }, index=series.index[is_outlier])

    # 4. Interactive Plotly figure: data, SPC limit curves and outliers in a contrasting colour.
    #    Scattergl draws the ~8760 hourly points with WebGL, which keeps the chart fast.
    unit = UNITS.get(variable, "")
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=series.index, y=x, mode="lines", name=f"Hourly {variable}",
                               line=dict(color="#60a5fa", width=1)))
    fig.add_trace(go.Scattergl(x=series.index, y=upper, mode="lines", name="SPC limits",
                               line=dict(color="#f59e0b", width=1.5, dash="dash")))
    fig.add_trace(go.Scattergl(x=series.index, y=lower, mode="lines", name="SPC limits",
                               line=dict(color="#f59e0b", width=1.5, dash="dash"),
                               showlegend=False))
    fig.add_trace(go.Scattergl(x=outliers.index, y=outliers[variable], mode="markers",
                               name=f"Outliers ({int(is_outlier.sum())})",
                               marker=dict(color="#dc2626", size=6)))
    fig.update_layout(
        title=f"{variable.capitalize()} with SPC limits {region_label} "
              f"(cut-off {cutoff_days} days, ±{n_std} robust SD)",
        xaxis_title="Time", yaxis_title=f"{variable.capitalize()} [{unit}]",
        hovermode="x unified", legend=dict(orientation="h", y=1.02, x=1, xanchor="right",
                                           yanchor="bottom"),
    )

    summary = {
        "variable": variable,
        "cutoff_days": cutoff_days,
        "n_std": n_std,
        "dct_coefficients_removed": k_cut,
        "robust_sd": round(float(sigma), 4),
        "n_values": n,
        "n_outliers": int(is_outlier.sum()),
        "outlier_share_%": round(100 * is_outlier.mean(), 2),
        "n_high": int((outliers["type"] == "high").sum()),
        "n_low": int((outliers["type"] == "low").sum()),
        "max_outlier_value": round(float(outliers[variable].max()), 3) if len(outliers) else None,
    }
    return fig, summary, outliers


# ---------------------------------------------------------------------------
# Anomalies: Local Outlier Factor
# ---------------------------------------------------------------------------

def lof_anomalies(weather, variable="temperature_2m", contamination=0.01, n_neighbors=50,
                  region_label=""):
    """Detect anomalies with the Local Outlier Factor method.

    weather       : DataFrame with an hourly DatetimeIndex (e.g. from download_weather)
    variable      : column to analyse (default 'temperature_2m')
    contamination : expected proportion of anomalies (default 1%)
    n_neighbors   : number of neighbours used to estimate the local density
    Returns (figure, summary dict, DataFrame of anomalies).
    """
    from sklearn.neighbors import LocalOutlierFactor
    from sklearn.preprocessing import StandardScaler

    series = weather[variable].astype(float)

    # Features: time (in hours from the start) and value, standardised so that
    # they have the same weight in the distance between points
    hours = (series.index - series.index[0]).total_seconds().to_numpy() / 3600
    features = StandardScaler().fit_transform(np.column_stack([hours, series.to_numpy()]))

    lof = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
    labels = lof.fit_predict(features)          # -1 = anomaly, 1 = normal
    scores = -lof.negative_outlier_factor_      # LOF score: higher = more anomalous
    is_anomaly = labels == -1

    anomalies = pd.DataFrame({
        variable: series[is_anomaly],
        "lof_score": scores[is_anomaly].round(3),
    })

    # Interactive Plotly figure: data with anomalies in a contrasting colour;
    # hovering over an anomaly also shows its LOF score
    unit = UNITS.get(variable, "")
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=series.index, y=series, mode="lines", name=f"Hourly {variable}",
                               line=dict(color="#60a5fa", width=1)))
    fig.add_trace(go.Scattergl(x=anomalies.index, y=anomalies[variable], mode="markers",
                               name=f"Anomalies ({int(is_anomaly.sum())})",
                               marker=dict(color="#dc2626", size=7),
                               customdata=anomalies["lof_score"],
                               hovertemplate="%{x}<br>%{y:.2f}<br>LOF score %{customdata}"))
    fig.update_layout(
        title=f"{variable.capitalize()} with LOF anomalies {region_label} "
              f"(contamination {contamination:.1%}, {n_neighbors} neighbours)",
        xaxis_title="Time", yaxis_title=f"{variable.capitalize()} [{unit}]",
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right", yanchor="bottom"),
    )

    summary = {
        "variable": variable,
        "contamination": contamination,
        "n_neighbors": n_neighbors,
        "n_values": len(series),
        "n_anomalies": int(is_anomaly.sum()),
        "anomaly_share_%": round(100 * is_anomaly.mean(), 2),
        "min_anomaly_value": round(float(anomalies[variable].min()), 2) if len(anomalies) else None,
        "max_anomaly_value": round(float(anomalies[variable].max()), 2) if len(anomalies) else None,
        "max_lof_score": round(float(scores.max()), 3),
    }
    return fig, summary, anomalies


# ---------------------------------------------------------------------------
# Reservoir statistics: STL decomposition and spectrogram
# ---------------------------------------------------------------------------

NVE_URL = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligData"


def load_reservoirs():
    """Download the weekly reservoir statistics from the NVE Magasinstatistikk API."""
    response = requests.get(NVE_URL, timeout=60)
    response.raise_for_status()
    res = pd.DataFrame(response.json())
    # ISO year + ISO week -> date (Monday of the week)
    res["Date"] = pd.to_datetime(
        res["iso_aar"].astype(str) + "-" + res["iso_uke"].astype(str) + "-1", format="%G-%V-%u"
    )
    return res.rename(columns={"omrType": "Area_Type", "omrnr": "Area_Number",
                               "fyllingsgrad": "Fill_Rate"})


def reservoir_series(reservoirs, area_type="EL", area_number=3):
    """Weekly filling rate of one area as a regular time series (no gaps)."""
    s = (reservoirs[(reservoirs.Area_Type == area_type) & (reservoirs.Area_Number == area_number)]
         .set_index("Date")["Fill_Rate"].sort_index())
    s = s[~s.index.duplicated()].dropna()
    # STL and the spectrogram need at least two full years (2 x 52 weeks) of data.
    # Some areas have no reservoir statistics at all, so stop with a clear message
    # instead of a cryptic error inside statsmodels.
    if len(s) < 104:
        raise ValueError(f"Not enough reservoir data for {area_type} {area_number} "
                         f"({len(s)} weeks; at least 104 are needed).")
    return s.asfreq("W-MON").interpolate()   # fill any missing week by linear interpolation


def stl_decomposition(reservoirs, area_type="EL", area_number=3,
                      seasonal=13, trend=105, robust=True):
    """STL decomposition of the weekly filling rate. Returns the figure.

    seasonal : length of the seasonal smoother in weeks (odd, >= 7)
    trend    : length of the trend smoother in weeks (odd, longer than the 52-week period)
    robust   : robust fitting that reduces the influence of outliers
    """
    from statsmodels.tsa.seasonal import STL

    series = reservoir_series(reservoirs, area_type, area_number)
    result = STL(series, period=52, seasonal=seasonal, trend=trend, robust=robust).fit()

    parts = [("Observed", result.observed), ("Trend", result.trend),
             ("Seasonal", result.seasonal), ("Residual", result.resid)]
    # Four panels on top of each other with a shared time axis (zooming one zooms all)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        subplot_titles=[name for name, _ in parts])
    for row, (name, values) in enumerate(parts, start=1):
        if name == "Residual":
            fig.add_trace(go.Scatter(x=values.index, y=values, mode="markers", name=name,
                                     marker=dict(color="#1d4ed8", size=3)), row=row, col=1)
            fig.add_hline(y=0, line_color="black", line_width=1, row=row, col=1)
        else:
            fig.add_trace(go.Scatter(x=values.index, y=values, mode="lines", name=name,
                                     line=dict(color="#1d4ed8", width=1.5)), row=row, col=1)
    fig.update_layout(
        height=850, showlegend=False,
        title=f"STL decomposition of the filling rate – {area_type} {area_number} "
              f"(seasonal={seasonal}, trend={trend}, robust={robust})",
    )
    fig.update_xaxes(title_text="Time", row=4, col=1)
    return fig


def reservoir_spectrogram(reservoirs, area_type="EL", area_number=3,
                          window_length=104, window_overlap=78, max_frequency=6):
    """Spectrogram of the weekly filling rate. Returns the figure.

    window_length  : window length in weeks
    window_overlap : overlap between consecutive windows in weeks (must be < window_length)
    max_frequency  : highest frequency shown, in cycles per year
    """
    from scipy.signal import spectrogram

    if window_overlap >= window_length:
        raise ValueError("window_overlap must be smaller than window_length")

    series = reservoir_series(reservoirs, area_type, area_number)
    freqs, times, power = spectrogram(
        series.to_numpy(),
        fs=52,                    # 52 weekly samples per year -> frequencies in cycles/year
        nperseg=window_length,
        noverlap=window_overlap,
        detrend="constant",       # remove the mean of each window
        scaling="density",
    )
    # Window centres (in years from the start) -> calendar dates
    dates = series.index[0] + pd.to_timedelta(times * 365.25, unit="D")
    keep = freqs <= max_frequency

    # Interactive heatmap: hovering shows time, frequency and power of each cell
    fig = go.Figure(go.Heatmap(
        x=dates, y=freqs[keep], z=10 * np.log10(power[keep] + 1e-12),
        colorscale="Viridis", colorbar=dict(title="Power [dB]"),
        hovertemplate="Time %{x|%b %Y}<br>Frequency %{y:.2f} cycles/year"
                      "<br>Power %{z:.1f} dB<extra></extra>",
    ))
    fig.update_layout(
        title=f"Spectrogram of the filling rate – {area_type} {area_number} "
              f"(window {window_length} weeks, overlap {window_overlap} weeks)",
        xaxis_title="Time", yaxis_title="Frequency [cycles per year]", height=500,
    )
    return fig


# ---------------------------------------------------------------------------
# Exchange rates from Norges Bank (part 4)
# ---------------------------------------------------------------------------

NB_URL = "https://data.norges-bank.no/api/data/EXR/{frequency}.{currencies}.NOK.SP"


def download_exchange_rates(start_date, end_date, currencies=("EUR", "USD"), frequency="B"):
    """Download exchange rates against NOK from the Norges Bank API (same as project_4.ipynb).

    start_date, end_date : period to download, as "YYYY-MM-DD" strings
    currencies           : base currencies, e.g. ("EUR", "USD")
    frequency            : "B" = business days, "M" = monthly, "A" = annual
    Returns a DataFrame with one row per date and one column per currency,
    containing the price of 1 unit of the currency in NOK.
    """
    import io

    # Series key, e.g. "B.EUR+USD.NOK.SP" ("+" selects several currencies at once)
    url = NB_URL.format(frequency=frequency, currencies="+".join(currencies))
    params = {"format": "csv", "startPeriod": start_date, "endPeriod": end_date, "locale": "en"}
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()

    # sep=None lets pandas detect the separator (Norges Bank uses ";")
    raw = pd.read_csv(io.StringIO(response.text), sep=None, engine="python")
    values = pd.to_numeric(raw["OBS_VALUE"].astype(str).str.replace(",", "."), errors="coerce")
    values = values / 10 ** raw["UNIT_MULT"].astype(int)   # always the price of 1 unit

    rates = (pd.DataFrame({"date": pd.to_datetime(raw["TIME_PERIOD"]),
                           "currency": raw["BASE_CUR"], "nok": values.values})
             .pivot(index="date", columns="currency", values="nok").sort_index())
    rates.columns.name = None
    return rates


def to_weekly(series, how="mean"):
    """Aggregate a daily or hourly series (or DataFrame) to weeks (same as project_4.ipynb).

    Weeks run Monday-Sunday and are labelled with the Monday, like the NVE reservoir data.
    how : "mean" (e.g. temperature, exchange rates) or "sum" (e.g. precipitation, energy)
    """
    s = series.copy()
    if s.index.tz is not None:   # time-zone aware -> Norwegian local time, then naive
        s.index = s.index.tz_convert("Europe/Oslo").tz_localize(None)
    weekly = s.resample("W-MON", closed="left", label="left")
    return weekly.sum() if how == "sum" else weekly.mean()