"""
Page: Reservoir analysis

Two analyses of the weekly reservoir filling rate (NVE Magasinstatistikk API) for the area
chosen in the global sidebar selector, organised in tabs:
  - STL decomposition (trend, seasonal and residual components)
  - Spectrogram (frequency content over time)
The analysis functions are shared with the notebook through analysis.py.
"""
import streamlit as st

from analysis import load_reservoirs, reservoir_spectrogram, stl_decomposition

st.title("Reservoirs: Seasonal Analysis")

# Area chosen in the global selector (app.py); NO3 if the page is opened directly
area_type, area_number = st.session_state.get("area", ("EL", 3))
st.write(f"Weekly filling rate for **{area_type} {area_number}** "
         "(change the area in the sidebar).")


# The full reservoir history is downloaded at most once a day and shared by both tabs
@st.cache_data(ttl=24 * 3600, show_spinner="Loading reservoir statistics from NVE...")
def get_reservoirs():
    return load_reservoirs()


reservoirs = get_reservoirs()

tab_stl, tab_spec = st.tabs(["STL decomposition", "Spectrogram"])

# ---------- TAB 1: STL decomposition ----------
with tab_stl:
    st.subheader("Seasonal-Trend decomposition with LOESS (STL)")
    col1, col2, col3 = st.columns(3)
    with col1:
        # STL requires odd smoother lengths: the options are restricted to odd numbers
        seasonal = st.select_slider(
            "Seasonal smoother [weeks]", options=list(range(7, 53, 2)), value=13,
            help="Longer values give a more stable seasonal pattern over the years.",
        )
    with col2:
        trend = st.select_slider(
            "Trend smoother [weeks]", options=list(range(53, 263, 2)), value=105,
            help="Must be longer than the 52-week period. Longer values give a smoother trend.",
        )
    with col3:
        robust = st.checkbox("Robust fitting", value=True,
                             help="Reduces the influence of outliers on the decomposition.")

    st.pyplot(stl_decomposition(reservoirs, area_type, area_number,
                                seasonal=seasonal, trend=trend, robust=robust))

# ---------- TAB 2: Spectrogram ----------
with tab_spec:
    st.subheader("Spectrogram of the filling rate")
    col1, col2 = st.columns(2)
    with col1:
        window_length = st.slider(
            "Window length [weeks]", min_value=26, max_value=260, value=104, step=2,
            help="Longer windows give a finer frequency resolution but a coarser time resolution.",
        )
    with col2:
        # The overlap must be smaller than the window; the default is 75% of the window
        window_overlap = st.slider(
            "Window overlap [weeks]", min_value=0, max_value=window_length - 2,
            value=min(78, window_length - 2), step=2,
            help="More overlap gives a smoother evolution over time.",
        )

    st.pyplot(reservoir_spectrogram(reservoirs, area_type, area_number,
                                    window_length=window_length, window_overlap=window_overlap))

# ---------- DATA SOURCE ----------
with st.expander("About the data and methods"):
    st.markdown(
        """
- **Source:** NVE (Norwegian Water Resources and Energy Directorate), *Magasinstatistikk* API:
  weekly filling rate of the hydropower reservoirs (0 = empty, 1 = full).
- **STL** splits the series into a long-term **trend**, a yearly **seasonal** cycle (period
  52 weeks) and a **residual**.
- The **spectrogram** shows the power of each frequency (in cycles per year) in sliding windows;
  the yearly cycle appears at 1 cycle per year.
- The same functions are developed and tested in the project notebook (`analysis.py`).
"""
    )