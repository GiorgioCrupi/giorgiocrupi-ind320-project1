import streamlit as st
import pandas as pd

st.set_page_config(page_title="Data Table", layout="wide")
st.title("Imported Data Overview")

@st.cache_data
def load_data():
    df = pd.read_csv('reservoirs.csv')
    
    column_translation = {
        'dato_Id': 'Date_Id', 'omrType': 'Area_Type', 'omrnr': 'Area_Number',
        'iso_aar': 'Year', 'iso_uke': 'Week', 'fyllingsgrad': 'Fill_Rate',
        'kapasitet_TWh': 'Capacity_TWh', 'fylling_TWh': 'Filled_TWh',
        'neste_Publiseringsdato': 'Next_Publishing_Date',
        'fyllingsgrad_forrige_uke': 'Fill_Rate_Last_Week',
        'endring_fyllingsgrad': 'Fill_Rate_Change'
    }
    df.rename(columns=column_translation, inplace=True)
    
    # Convert ISO Year and Week to a standard Date and Month string
    df['Date'] = pd.to_datetime(df['Year'].astype(str) + '-' + df['Week'].astype(str) + '-1', format='%G-%V-%u')
    df['Month_Str'] = df['Date'].dt.strftime('%Y-%m')
    return df

df = load_data()

# Isolate the first available month in the dataset
first_month = df['Month_Str'].min()
st.write(f"### Trend Analysis for the First Month: {first_month}")

# Filter dataframe for the first month only
df_first_month = df[df['Month_Str'] == first_month]

numeric_columns = ['Fill_Rate', 'Capacity_TWh', 'Filled_TWh', 'Fill_Rate_Last_Week', 'Fill_Rate_Change']

summary_data = []
for col in numeric_columns:
    # Extract ALL raw records for the month 
    # We use dropna() and astype(float) to prevent Streamlit rendering crashes.
    raw_values = df_first_month[col].dropna().astype(float).tolist()
    
    summary_data.append({
        "Variable Name": col,
        "Trend (First Month)": raw_values
    })

summary_df = pd.DataFrame(summary_data)

# Display dataframe using LineChartColumn for the raw values
st.dataframe(
    summary_df,
    column_config={
        "Variable Name": st.column_config.TextColumn("Column Name", width="medium"),
        "Trend (First Month)": st.column_config.LineChartColumn(
            "Trend Line",
            help="Raw data points for the first month (all areas)"
        )
    },
    hide_index=True,
    use_container_width=True
)