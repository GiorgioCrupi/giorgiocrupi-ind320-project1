"""
IND320 - Norwegian Energy Dashboard (Streamlit entry point)

Run locally (from the project folder) with:
    uv run streamlit run app.py

This file defines:
  - the pages, grouped by type of task (Explore, Anomalies, Relations and prediction),
    as in the sketch in project_4.ipynb;
  - a custom sidebar menu: one coloured header per group, links to the pages, and the
    current page highlighted in the colour of its group;
  - the global selections (area and period), stored in st.session_state so that every
    page uses the same selection;
  - a coloured banner at the top of each page that shows the active group.
Every page lives in its own .py file and is executed by Streamlit when the user selects it.
"""
import datetime as dt

import streamlit as st

# set_page_config must be the first Streamlit command that is executed.
st.set_page_config(page_title="IND320 Energy Dashboard", page_icon=":material/bolt:",
                   layout="wide")

# ---------------------------------------------------------------------------
# Areas that can be selected
# ---------------------------------------------------------------------------
# Only EL (price) and VASS (watercourse) areas are offered, because they have a matching
# weather region and GeoJSON outline.
AREAS = {
    "NO1 – South-East Norway (price area)": ("EL", 1),
    "NO2 – South-West Norway (price area)": ("EL", 2),
    "NO3 – Central Norway (price area)": ("EL", 3),
    "NO4 – Northern Norway (price area)": ("EL", 4),
    "NO5 – Western Norway (price area)": ("EL", 5),
    "VASS1 – South-East Norway (watercourse area)": ("VASS", 1),
    "VASS2 – Western Norway (watercourse area)": ("VASS", 2),
    "VASS3 – Central Norway (watercourse area)": ("VASS", 3),
    "VASS4 – Northern Norway (watercourse area)": ("VASS", 4),
}
AREA_LABELS = {area: label for label, area in AREAS.items()}   # ("EL", 3) -> label

# ---------------------------------------------------------------------------
# Pages, grouped by type of task
# ---------------------------------------------------------------------------
# Each group has an emoji, a strong colour (text, borders, active page) and a light
# background colour (group header), the same colours as in the sketch.
GROUP_STYLE = {
    "Explore": ("🧭", "#1d4ed8", "#dbeafe"),                    # blue
    "Anomalies": ("⚠️", "#c2410c", "#ffedd5"),                  # orange
    "Relations and prediction": ("📈", "#15803d", "#dcfce7"),   # green
}

home = st.Page("home.py", title="Home", icon=":material/home:", default=True)
PAGES = {
    "Explore": [
        st.Page("pages/1_Map.py", title="Map", icon=":material/map:"),
        st.Page("pages/2_Reservoir_Overview.py", title="Reservoir overview",
                icon=":material/water_drop:"),
        st.Page("pages/4_Cross_Border_Flows.py", title="Cross-border flows",
                icon=":material/swap_horiz:"),
        st.Page("pages/7_Exchange_Rates.py", title="Exchange rates",
                icon=":material/currency_exchange:"),
    ],
    "Anomalies": [
        st.Page("pages/5_Reservoir_Analysis.py", title="Reservoir seasonality",
                icon=":material/insights:"),
        st.Page("pages/6_Weather_Anomalies.py", title="Weather outliers and anomalies",
                icon=":material/thermostat:"),
    ],
    "Relations and prediction": [
        st.Page("pages/8_Sliding_Correlation.py", title="Sliding window correlation",
                icon=":material/compare_arrows:"),
        st.Page("pages/9_Forecast.py", title="Forecast", icon=":material/trending_up:"),
    ],
}

# position="hidden": Streamlit still handles the pages, but does not draw its default menu,
# because we draw our own, coloured menu in the sidebar below.
pg = st.navigation({"": [home], **PAGES}, position="hidden")

# Group of the page that is currently open (None for the home page)
current_group = next((group for group, pages in PAGES.items()
                      if pg.title in [p.title for p in pages]), None)

# ---------------------------------------------------------------------------
# A little CSS for the sidebar (background and the look of the page links)
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* soft blue-to-white background for the whole sidebar */
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #eef4fb 0%, #ffffff 100%); }
    /* rounded page links with a light highlight when the mouse is over them */
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] { border-radius: 8px; }
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover { background: #e5edf8; }
    </style>
    """,
    unsafe_allow_html=True,   # allows HTML/CSS in st.markdown (used only for styling)
)


def group_header(group):
    """Coloured rectangle with the name of a group of pages."""
    emoji, colour, background = GROUP_STYLE[group]
    st.markdown(
        f'<div style="background:{background}; color:{colour}; border-left:6px solid {colour}; '
        f'padding:6px 12px; border-radius:8px; font-weight:700; font-size:0.8rem; '
        f'letter-spacing:0.05em; margin:0.9rem 0 0.3rem 0;">{emoji}&nbsp; {group.upper()}</div>',
        unsafe_allow_html=True,
    )


def active_page_box(title, colour):
    """The current page, shown as a filled box in the colour of its group."""
    st.markdown(
        f'<div style="background:{colour}; color:white; padding:6px 12px; border-radius:8px; '
        f'font-weight:600; margin:2px 0;">▸&nbsp; {title}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Default values of the global selections (only the first time the app is opened)
# ---------------------------------------------------------------------------
st.session_state.setdefault("area_label", AREA_LABELS[("EL", 3)])           # NO3
st.session_state.setdefault("period", (dt.date(2024, 1, 1), dt.date(2024, 12, 31)))

# A page (e.g. the map) can select another area by storing it in "pending_area".
# It is applied here, before the selectbox is created, because Streamlit does not allow
# changing a widget's value after the widget has been drawn in the same run.
if "pending_area" in st.session_state:
    st.session_state["area_label"] = AREA_LABELS[st.session_state.pop("pending_area")]

# ---------------------------------------------------------------------------
# Sidebar: title, coloured menu and global selections
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## ⚡ IND320")
    st.caption("Norwegian Energy Dashboard")

    # Home: a plain link, or a dark box when it is the current page
    if pg.title == home.title:
        active_page_box(home.title, "#1f2937")
    else:
        st.page_link(home, label=home.title, icon=home.icon)

    # One coloured header per group, followed by its pages
    for group, pages in PAGES.items():
        group_header(group)
        colour = GROUP_STYLE[group][1]
        for page in pages:
            if page.title == pg.title:
                active_page_box(page.title, colour)   # current page: filled box
            else:
                st.page_link(page, label=page.title, icon=page.icon)

    st.divider()

    # Global selections in a bordered card. key= links each widget to st.session_state,
    # so the choice survives page changes.
    with st.container(border=True):
        st.markdown("**:material/tune: Selection for the analyses**")
        area_label = st.selectbox("Area", list(AREAS), key="area_label")
        st.slider(
            "Period",
            min_value=dt.date(2018, 1, 1),
            max_value=dt.date.today(),
            format="MMM YYYY",
            key="period",
        )
        st.caption("Used by all analysis pages. The area can also be selected on the map.")

# Make the selected area available to all pages as (area_type, area_number)
st.session_state["area"] = AREAS[area_label]

# ---------------------------------------------------------------------------
# Coloured banner showing the active group, then the selected page
# ---------------------------------------------------------------------------
if current_group is not None:
    emoji, colour, background = GROUP_STYLE[current_group]
    st.markdown(
        f'<div style="background:{background}; color:{colour}; border-left:6px solid {colour}; '
        f'padding:6px 14px; border-radius:6px; font-weight:600; margin-bottom:0.5rem;">'
        f'{emoji}&nbsp; {current_group}</div>',
        unsafe_allow_html=True,
    )

# Run the page currently selected by the user
pg.run()