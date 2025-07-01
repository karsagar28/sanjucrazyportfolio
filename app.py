import streamlit as st
import pandas as pd
import plotly.express as px

# --- Page Configuration ---
st.set_page_config(
    page_title="Stock Portfolio",
    page_icon="💹",
    layout="wide",
)

# --- Initialize Session State ---
# This will store the dataframe so it persists across reruns
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False


# --- Data Loading Function ---
@st.cache_data
def load_data(url):
    """
    Loads data from the provided Google Sheet URL.
    The data is cached to avoid reloading on every interaction.
    Returns a pandas DataFrame.
    """
    try:
        # Use the 'python' engine and 'on_bad_lines' to handle formatting
        # issues in the source sheet, such as extra data below the main table.
        df = pd.read_csv(url, engine='python', on_bad_lines='skip')
        
        # --- Data Validation and Cleaning ---
        if df.empty:
            st.error("The Google Sheet is empty or could not be read. Please verify the URL and sheet content.")
            return pd.DataFrame()

        # Define expected columns
        numeric_cols = ['Shares', 'Cost of Shares', 'Current Price of Shares',
                        'Capital Input', 'Current Value', '% change', 'P/L']
        all_expected_cols = ['Account', 'Ticker', 'Tag', 'Name', 'Type', 'Action'] + numeric_cols

        # Check for missing columns
        missing_cols = [col for col in all_expected_cols if col not in df.columns]
        if missing_cols:
            st.error(f"The following required columns are missing from your sheet: {', '.join(missing_cols)}")
            return pd.DataFrame()

        # --- Clean currency and percentage columns before numeric conversion ---
        cols_to_clean = ['Cost of Shares', 'Current Price of Shares', 'Capital Input', 'Current Value', 'P/L', '% change']
        for col in cols_to_clean:
            if col in df.columns:
                # Remove currency and percentage symbols
                df[col] = df[col].astype(str).str.replace(r'[$,%]', '', regex=True)

        # Convert relevant columns to numeric, coercing errors to NaN
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # --- Handle CASH entries ---
        # For rows where Type is 'Cash', fill irrelevant numeric columns with 0
        # This prevents them from being dropped by dropna.
        # Using .str.upper() to make the check case-insensitive.
        if 'Type' in df.columns:
            cash_mask = df['Type'].str.upper().fillna('') == 'CASH'
            cols_to_zero_for_cash = ['Shares', 'Cost of Shares', 'Current Price of Shares', '% change', 'P/L']
            for col in cols_to_zero_for_cash:
                if col in df.columns:
                    df.loc[cash_mask, col] = df.loc[cash_mask, col].fillna(0)

        # Fill any potential NaN values in key categorical columns
        df['Account'].fillna('Unknown', inplace=True)
        df['Type'].fillna('Unknown', inplace=True)
        
        # Drop rows where essential numeric values for calculations are still missing.
        # This will now keep cash rows (as we filled NaNs) but drop other malformed rows.
        df.dropna(subset=['Current Value', 'Capital Input'], inplace=True)

        return df
    except Exception as e:
        st.error("An error occurred while loading the data.")
        st.exception(e) # Display the full error traceback
        return pd.DataFrame()

# --- Sidebar: Data Loading Controls ---
default_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR7KnmZufiJnMG0N5_zJFRiJKXQ0I-TM_lvuCCBIs7WBXfuk04E5GS5F0j-arRJ9cRTxQndZTs6kUF0/pub?gid=743265364&single=true&output=csv"
sheet_url = st.sidebar.text_input(
    "Paste your 'Publish to web' CSV URL here:",
    default_url
)

if st.sidebar.button("Load Portfolio Data", type="primary"):
    if not sheet_url:
        st.sidebar.warning("Please enter the Google Sheet URL.")
        st.session_state.data_loaded = False
    else:
        with st.spinner("Fetching and processing data from Google Sheet..."):
            # Clear cache before loading new data
            st.cache_data.clear()
            st.session_state.df = load_data(sheet_url)
            if not st.session_state.df.empty:
                st.session_state.data_loaded = True
                st.sidebar.success("Data loaded successfully!")
            else:
                st.session_state.data_loaded = False
                # Error messages are handled inside load_data()

# --- Main Dashboard Display ---
if st.session_state.data_loaded:
    df = st.session_state.df
    # --- Sidebar Filters (only show if data is loaded) ---
    st.sidebar.header("Display Filters")
    
    # Handle case where a filter option might be removed after initial load
    accounts = df["Account"].unique()
    selected_account = st.sidebar.multiselect(
        "Filter by Account",
        options=accounts,
        default=accounts
    )

    types = df["Type"].unique()
    selected_type = st.sidebar.multiselect(
        "Filter by Type",
        options=types,
        default=types
    )

    # Filter data based on selections
    filtered_df = df[
        df["Account"].isin(selected_account) &
        df["Type"].isin(selected_type)
    ]
    
    if not filtered_df.empty:
        # --- Main Dashboard ---
        st.title("📈 Stock Portfolio Dashboard")
        st.markdown("A real-time view of your investment portfolio.")

        # --- Key Performance Indicators (KPIs) ---
        # Totals now correctly include cash (which can be negative)
        total_value = filtered_df["Current Value"].sum()
        total_pl = filtered_df["P/L"].sum()
        total_capital_input = filtered_df['Capital Input'].sum()
        
        # Calculate overall portfolio % change on invested capital (excluding cash)
        invested_capital = filtered_df[filtered_df['Type'].str.upper() != 'CASH']['Capital Input'].sum()
        if invested_capital > 0:
            overall_pct_change = (total_pl / invested_capital) * 100
        else:
            overall_pct_change = 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="Total Portfolio Value (incl. Cash)", value=f"${total_value:,.2f}")
        with col2:
            st.metric(label="Total Profit/Loss (on Investments)", value=f"${total_pl:,.2f}", delta=f"{overall_pct_change:.2f}%")
        with col3:
            st.metric(label="Total Capital Input", value=f"${total_capital_input:,.2f}")

        st.markdown("---")

        # --- Visualizations ---
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Portfolio Value by Ticker")
            value_by_ticker = filtered_df.groupby("Ticker")["Current Value"].sum().sort_values(ascending=False)
            fig_bar = px.bar(value_by_ticker, x=value_by_ticker.index, y=value_by_ticker.values,
                             title="Current Value per Ticker (incl. Cash)", labels={"y": "Current Value ($)", "x": "Ticker"},
                             template="plotly_white", height=400)
            fig_bar.update_layout(xaxis={'categoryorder':'total descending'})
            st.plotly_chart(fig_bar, use_container_width=True)

        with col2:
            st.subheader("Portfolio Distribution by Type")
            # Exclude 'Cash' from the pie chart as it doesn't represent an investment type in the same way
            pie_df = filtered_df[filtered_df['Type'].str.upper() != 'CASH']
            type_distribution = pie_df.groupby("Type")["Current Value"].sum()
            fig_pie = px.pie(type_distribution, values=type_distribution.values, names=type_distribution.index,
                             title="Invested Portfolio by Type (Excluding Cash)", hole=.3, template="plotly_white", height=400)
            st.plotly_chart(fig_pie, use_container_width=True)

        st.subheader("Portfolio Composition by Company")
        # Exclude 'Cash' from the treemap as it's not an 'invested' holding
        treemap_df = filtered_df[filtered_df['Type'].str.upper() != 'CASH']
        fig_treemap = px.treemap(treemap_df, path=[px.Constant("Portfolio"), 'Type', 'Name'], values='Current Value',
                                 color='P/L', hover_data={'P/L': ':.2f', 'Current Value': ':.2f'},
                                 color_continuous_scale='RdYlGn', title="Treemap of Invested Holdings (Excluding Cash)",
                                 template="plotly_white", height=600)
        st.plotly_chart(fig_treemap, use_container_width=True)

        st.subheader("Detailed Portfolio View")
        st.dataframe(filtered_df)
    else:
        st.warning("No data matches the current filter settings. Please adjust the filters in the sidebar.")

else:
    st.info("Welcome! Please provide your Google Sheet URL and click 'Load Portfolio Data' in the sidebar to get started.")
