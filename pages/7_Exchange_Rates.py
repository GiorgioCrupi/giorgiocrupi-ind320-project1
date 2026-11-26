"""
Page: Exchange rates

Official exchange rates against NOK from the Norges Bank API, for the period chosen in the
global sidebar selection. Local choices: which currencies and which frequency (business days,
weekly mean or monthly). Shows an interactive Plotly line chart, the latest rate and the change
over the period for each currency (st.metric), and the data in a table.
The download function is shared with the notebook through analysis.py.
"""
import datetime as dt

import plotly.express as px
import requests
import streamlit as st

from analysis import download_exchange_rates, to_weekly

st.title("Exchange Rates (Norges Bank)")

CURRENCIES = {"EUR": "Euro", "USD": "US dollar", "GBP": "British pound",
              "SEK": "Swedish krona", "DKK": "Danish krone"}

# Period chosen in the sidebar (global selection shared by all pages)
start, end = st.session_state.get("period", (dt.date(2024, 1, 1), dt.date(2024, 12, 31)))
st.write(f"Price of one unit of each currency in **Norwegian kroner (NOK)**, "
         f"**{start:%b %Y} – {end:%b %Y}** (change the period in the sidebar).")

# ---------------------------------------------------------------------------
# Local choices: currencies and time resolution
# ---------------------------------------------------------------------------
col1, col2 = st.columns([2, 1])
with col1:
    currencies = st.multiselect("Currencies", list(CURRENCIES), default=["EUR", "USD"],
                                format_func=lambda c: f"{c} – {CURRENCIES[c]}")
with col2:
    resolution = st.radio("Resolution", ["Daily", "Weekly", "Monthly"], index=1, horizontal=True,
                          help="Weekly = mean of the business days of each week (Monday-Sunday), "
                               "the same weeks as the reservoir data.")

if not currencies:
    st.info("Select at least one currency.")
    st.stop()


# Cached per (period, currencies, frequency): the API is called only once for each combination
@st.cache_data(ttl=24 * 3600, show_spinner="Downloading exchange rates from Norges Bank...")
def get_rates(start, end, currencies, frequency):
    return download_exchange_rates(start.isoformat(), end.isoformat(),
                                   currencies=currencies, frequency=frequency)


# Error handling: clear messages instead of a crash if the API cannot be reached
try:
    # Monthly rates come directly from Norges Bank ("M"); daily and weekly use business days ("B")
    rates = get_rates(start, end, tuple(currencies), "M" if resolution == "Monthly" else "B")
except (requests.RequestException, KeyError, ValueError) as e:
    st.error(f"The exchange rates could not be downloaded from Norges Bank: {e}")
    st.stop()

if rates.empty:
    st.warning("Norges Bank has no exchange rates for the selected period.")
    st.stop()
if resolution == "Weekly":
    rates = to_weekly(rates)   # weekly mean, weeks labelled with the Monday

# ---------------------------------------------------------------------------
# Latest rate and change over the period
# ---------------------------------------------------------------------------
metric_cols = st.columns(len(currencies))
for col, currency in zip(metric_cols, currencies):
    series = rates[currency].dropna()
    change = 100 * (series.iloc[-1] / series.iloc[0] - 1)
    # delta_color="inverse": a higher price of foreign currency = a weaker krone (shown in red)
    col.metric(f"{currency}/NOK ({series.index[-1]:%d %b %Y})", f"{series.iloc[-1]:.3f}",
               f"{change:+.1f} % over the period", delta_color="inverse")

# ---------------------------------------------------------------------------
# Interactive line chart
# ---------------------------------------------------------------------------
fig = px.line(rates, markers=resolution == "Monthly",
              labels={"value": "NOK per unit", "index": "Date", "date": "Date",
                      "variable": "Currency"},
              title=f"{resolution} exchange rates against NOK")
fig.update_layout(hovermode="x unified", legend_title_text="Currency")
st.plotly_chart(fig, use_container_width=True)

with st.expander("Data table"):
    st.dataframe(rates.round(4), use_container_width=True)

with st.expander("About the data"):
    st.markdown(
        """
- **Source:** Norges Bank open data API (SDMX), series `EXR` (exchange rates), spot rates against NOK.
- **Business days only:** no rates on weekends and Norwegian bank holidays (see the time-zone
  analysis in the project notebook).
- **Weekly** values are means over Monday–Sunday, the same weeks as the NVE reservoir data,
  so they can be combined with the reservoir filling (e.g. as exogenous variables in the forecast).
- A rising line means that the foreign currency becomes more expensive, i.e. the krone weakens.
"""
    )