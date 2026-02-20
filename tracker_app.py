import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import plotly.express as px
from datetime import datetime
import os
import time
import re

# --- CONSTANTS & CONFIG ---
DATA_FILE = 'eb2_india_data.csv'
MONTHS =

st.set_page_config(page_title="EB-2 India Visa Tracker", layout="wide")

# --- UTILITY FUNCTIONS ---
def parse_priority_date(date_str, bulletin_date):
    """Converts varying State Dept string formats into standard dates."""
    if not date_str or pd.isna(date_str): 
        return pd.NaT
    date_str = str(date_str).strip().upper()
    
    if date_str in:
        return bulletin_date
    if date_str in:
        return pd.NaT
        
    try:
        # Tries specific formats like '01DEC13' or '15SEP13'
        return pd.to_datetime(date_str, format='%d%b%y')
    except:
        try:
            # Fallback to general pandas parser
            return pd.to_datetime(date_str)
        except:
            return pd.NaT

def get_bulletin_url(month_name, year):
    """Builds the URL taking into account the US Gov Fiscal Year (Starts in Oct)"""
    month_idx = MONTHS.index(month_name.lower()) + 1
    fiscal_year = year + 1 if month_idx >= 10 else year
    return f"https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/{fiscal_year}/visa-bulletin-for-{month_name.lower()}-{year}.html"

# --- SCRAPING LOGIC ---
def extract_eb2_india_date(df):
    """Safely finds the intersection of '2ND' row and 'INDIA' column in any HTML table format."""
    raw_data = + df.values.tolist()
    
    india_col_idx = None
    for row in raw_data:
        for j, cell in enumerate(row):
            if 'INDIA' in str(cell).upper():
                india_col_idx = j
                break
        if india_col_idx is not None: 
            break
            
    second_row_idx = None
    for i, row in enumerate(raw_data):
        for cell in row:
            if re.search(r'\b2ND\b', str(cell).upper()):
                second_row_idx = i
                break
        if second_row_idx is not None: 
            break
            
    if india_col_idx is not None and second_row_idx is not None:
        try:
            return raw_data
        except:
            return None
    return None

def fetch_bulletin_dates(month_name, year):
    url = get_bulletin_url(month_name, year)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: 
            return pd.NaT, pd.NaT
        
        soup = BeautifulSoup(response.content, 'lxml')
        tables = pd.read_html(str(soup))
        
        dates_found =[]
        for df in tables:
            extracted_date = extract_eb2_india_date(df)
            if extracted_date:
                dates_found.append(extracted_date)
                
        bulletin_date = pd.to_datetime(f"01 {month_name} {year}")
        
        fad, dof = pd.NaT, pd.NaT
        # Usually, Table 1 is Final Action Date (FAD), Table 2 is Date of Filing (DOF)
        if len(dates_found) >= 1: 
            fad = parse_priority_date(dates_found, bulletin_date)
        if len(dates_found) >= 2: 
            dof = parse_priority_date(dates_found, bulletin_date)
            
        return fad, dof
    except Exception as e:
        return pd.NaT, pd.NaT

def init_or_update_db():
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        df = pd.to_datetime(df)
        df = pd.to_datetime(df)
        df = pd.to_datetime(df)
    else:
        df = pd.DataFrame(columns=)
        
    today = datetime.today()
    start_date = datetime(2017, 1, 1)
    target_date = datetime(today.year, today.month, 1)
    
    if today.day >= 25:
        target_date = target_date + pd.DateOffset(months=1)
        
    dates_to_check = pd.date_range(start=start_date, end=target_date, freq='MS')
    
    missing_dates =[]
    for d in dates_to_check:
        if df.empty or d not in df.values:
            missing_dates.append(d)
            
    if missing_dates:
        st.warning(f"Fetching real historical data for {len(missing_dates)} missing months... This only happens once!")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        new_rows =[]
        for i, d in enumerate(missing_dates):
            month_name = MONTHS
            status_text.text(f"Scraping {month_name.capitalize()} {d.year}...")
            
            fad, dof = fetch_bulletin_dates(month_name, d.year)
            
            new_rows.append({
                'Bulletin_Date': d,
                'Date_of_Filing': dof,
                'Final_Action_Date': fad
            })
            
            progress_bar.progress((i + 1) / len(missing_dates))
            time.sleep(0.3) # Respect State Dept servers
            
        df_new = pd.DataFrame(new_rows)
        df = pd.concat(, ignore_index=True)
        df = df.sort_values('Bulletin_Date').reset_index(drop=True)
        df.to_csv(DATA_FILE, index=False)
        status_text.text("Database fully synchronized with State Dept real dates!")
        time.sleep(2)
        st.rerun()
        
    return df

# --- UI & CHARTS ---
st.title("📈 True EB-2 India Visa Bulletin Tracker")
st.markdown("Live scraping of Final Action Dates and Dates of Filing directly from the U.S. State Department.")

# Manage DB Reset
with st.sidebar:
    st.markdown("### Admin Controls")
    st.markdown("If charts look wrong or linear, click below to wipe the mock data and fetch real history.")
    if st.button("Delete Database & Re-Scrape"):
        if os.path.exists(DATA_FILE):
            os.remove(DATA_FILE)
            st.rerun()

# Load Data
with st.spinner("Checking for missing bulletin releases..."):
    df = init_or_update_db()

# Filter out NaT (Not a Time) values for cleaner charting
df_clean = df.dropna(subset=, how='all')

# Layout Metrics
col1, col2, col3 = st.columns(3)
with col1:
    val = df_clean.iloc.strftime('%B %Y') if not df_clean.empty and pd.notna(df_clean.iloc) else "N/A"
    st.metric(label="Latest Bulletin Month", value=val)
with col2:
    val = df_clean.iloc.strftime('%d %b %Y') if not df_clean.empty and pd.notna(df_clean.iloc) else "N/A"
    st.metric(label="Latest Date of Filing", value=val)
with col3:
    val = df_clean.iloc.strftime('%d %b %Y') if not df_clean.empty and pd.notna(df_clean.iloc) else "N/A"
    st.metric(label="Latest Final Action Date", value=val)

st.divider()

# Chart 1: Date of Filing
st.subheader("🗓️ Date of Filing Movement")
fig_dof = px.line(df_clean.dropna(subset=), x='Bulletin_Date', y='Date_of_Filing', 
                  markers=True, 
                  labels={'Bulletin_Date': 'Visa Bulletin Release Month', 'Date_of_Filing': 'Cutoff Priority Date'},
                  line_shape='hv')
fig_dof.update_layout(yaxis=dict(tickformat="%b %Y"), xaxis=dict(tickformat="%b %Y"))
fig_dof.update_traces(line_color='#1f77b4')
st.plotly_chart(fig_dof, use_container_width=True)

# Chart 2: Final Action Date
st.subheader("⚖️ Final Action Date Movement")
fig_fad = px.line(df_clean.dropna(subset=), x='Bulletin_Date', y='Final_Action_Date', 
                  markers=True, 
                  labels={'Bulletin_Date': 'Visa Bulletin Release Month', 'Final_Action_Date': 'Cutoff Priority Date'},
                  line_shape='hv')
fig_fad.update_layout(yaxis=dict(tickformat="%b %Y"), xaxis=dict(tickformat="%b %Y"))
fig_fad.update_traces(line_color='#d62728')
st.plotly_chart(fig_fad, use_container_width=True)

# Data Table
with st.expander("View Scraped Raw Data"):
    st.dataframe(df.sort_values(by="Bulletin_Date", ascending=False).reset_index(drop=True))
