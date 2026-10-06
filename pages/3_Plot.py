import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="Interactive Plot", layout="wide")
st.title("Interactive Data Visualization")

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
    
    # Create Date and Month_Str columns for filtering
    df['Date'] = pd.to_datetime(df['Year'].astype(str) + '-' + df['Week'].astype(str) + '-1', format='%G-%V-%u')
    df['Month_Str'] = df['Date'].dt.strftime('%Y-%m')
    return df

df = load_data()

numeric_columns = ['Fill_Rate', 'Capacity_TWh', 'Filled_TWh', 'Fill_Rate_Last_Week', 'Fill_Rate_Change']

# --- WIDGET 1: Select Slider for Month Range ---
# Extract unique sorted months
unique_months = sorted(df['Month_Str'].unique())
first_month = unique_months[0]

# Using a tuple (first_month, first_month) creates a range slider defaulting to the first month
selected_months = st.select_slider(
    "Select a subset of months:",
    options=unique_months,
    value=(first_month, first_month)
)

# Filter dataframe based on the selected month range
mask = (df['Month_Str'] >= selected_months[0]) & (df['Month_Str'] <= selected_months[1])
df_filtered = df[mask]


# --- WIDGET 2: Selectbox for Columns ---
options = ['All Columns'] + numeric_columns
selected_col = st.selectbox("Choose a column to plot:", options=options)

st.write("---")

# --- PLOTTING ---
# Aggregate data by Date to calculate the national average and avoid visual artifacts
df_plot = df_filtered.groupby('Date')[numeric_columns].mean().reset_index()

# Set up the Matplotlib figure
fig, ax = plt.subplots(figsize=(12, 6))

if selected_col == 'All Columns':
    # Normalize data (Min-Max scaling) to make the graph natural despite different scales
    df_normalized = df_plot.copy()
    for col in numeric_columns:
        min_val = df_plot[col].min()
        max_val = df_plot[col].max()
        if max_val != min_val:
            df_normalized[col] = (df_plot[col] - min_val) / (max_val - min_val)
        else:
            df_normalized[col] = 0.5
            
    # Plot all normalized columns
    for col in numeric_columns:
        ax.plot(df_normalized['Date'], df_normalized[col], label=col, linewidth=2)
        
    ax.set_ylabel("Normalized Values (0-1 Scale)", fontsize=12)
    ax.set_title(f"National Averages - All Columns ({selected_months[0]} to {selected_months[1]})", fontsize=16, fontweight='bold')

else:
    # Plot only the single selected column
    ax.plot(df_plot['Date'], df_plot[selected_col], color='#1f77b4', linewidth=2, label=selected_col)
    ax.set_ylabel(selected_col, fontsize=12)
    ax.set_title(f"{selected_col} Trend ({selected_months[0]} to {selected_months[1]})", fontsize=16, fontweight='bold')

# Formatting the plot (headers, axes, grid)
ax.set_xlabel("Date", fontsize=12)
ax.grid(True, alpha=0.3)
ax.legend(loc='best')
plt.xticks(rotation=45)
plt.tight_layout()

# Display the plot in Streamlit
st.pyplot(fig)