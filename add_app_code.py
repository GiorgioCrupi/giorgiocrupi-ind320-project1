"""
Append the source code of the Streamlit app to a project notebook as Markdown cells,
so the code is visible when the notebook is exported to HTML/PDF.

Run from the project folder (close the notebook in VS Code first):
    uv run python add_app_code.py                                 # project_4.ipynb
    uv run python add_app_code.py notebooks/project_3.ipynb       # another notebook

The script can be run again at any time (e.g. after changing the app): the cells it added
before are recognised by a hidden marker and replaced, so nothing is duplicated.
"""
import json
import sys
from pathlib import Path

NOTEBOOK = Path(sys.argv[1] if len(sys.argv) > 1 else "notebooks/project_4.ipynb")
MARKER = "<!-- streamlit-app-code -->"   # invisible in the rendered notebook

# (file, short description shown above the code), in the order of the app menu
FILES = [
    ("app.py",
     "Entry point: page groups (Explore, Anomalies, Relations and prediction), the custom coloured "
     "sidebar menu, the global area and period selection (st.session_state) and the group banner."),
    (".streamlit/config.toml", "App theme (colours), also used by the Plotly charts."),
    ("home.py", "Front page with a short description of each group and links to the pages."),
    ("analysis.py",
     "Shared module with the functions developed in the notebooks (weather download, SPC, LOF, "
     "STL, spectrogram, Norges Bank exchange rates, weekly aggregation and the SNARIMAX forecast). "
     "All figures are interactive Plotly figures."),
    ("pages/1_Map.py",
     "Explore – Map: GeoJSON areas coloured by filling rate or weather property in the chosen "
     "week; a click selects the area for all pages."),
    ("pages/2_Reservoir_Overview.py",
     "Explore – Reservoir overview: the former table (LineChartColumn) and trend pages joined, "
     "with Plotly charts."),
    ("pages/4_Cross_Border_Flows.py",
     "Explore – Cross-border flows (ENTSO-E data from MongoDB), Plotly charts."),
    ("pages/7_Exchange_Rates.py", "Explore – Exchange rates from Norges Bank."),
    ("pages/5_Reservoir_Analysis.py",
     "Anomalies – Reservoir seasonality: STL decomposition and spectrogram."),
    ("pages/6_Weather_Anomalies.py",
     "Anomalies – Weather outliers (SPC) and anomalies (LOF), temperature as default property."),
    ("pages/8_Sliding_Correlation.py",
     "Relations and prediction – Sliding window correlation with selectable lag and window."),
    ("pages/9_Forecast.py",
     "Relations and prediction – Forecast with River SNARIMAX, selectable parameters and "
     "exogenous variables, Plotly animation and quantile confidence band."),
]

nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))


def markdown_cell(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


# Remove the cells added by an earlier run of this script
nb["cells"] = [c for c in nb["cells"] if MARKER not in "".join(c["source"])]

intro = (
    f"{MARKER}\n"
    "## Appendix: Streamlit app source code\n\n"
    "The app is run with `uv run streamlit run app.py` and is deployed on Streamlit Cloud. "
    "Its source code is copied below as Markdown so it is included in the exported notebook. "
    "The MongoDB connection string is read from `st.secrets` and is not part of the code."
)
nb["cells"].append(markdown_cell(intro))

for path, description in FILES:
    file = Path(path)
    if not file.exists():
        print(f"Skipped (not found): {path}")
        continue
    code = file.read_text(encoding="utf-8").rstrip()
    if "mongodb+srv" in code:   # safety check: never copy a password into the notebook
        raise SystemExit(f"Stopped: {path} contains a MongoDB connection string.")
    language = "toml" if path.endswith(".toml") else "python"
    cell = f"{MARKER}\n### `{path}`\n\n{description}\n\n```{language}\n{code}\n```"
    nb["cells"].append(markdown_cell(cell))
    print(f"Added: {path}")

NOTEBOOK.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Done: {NOTEBOOK} updated.")