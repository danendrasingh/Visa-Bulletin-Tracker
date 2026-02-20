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

# Using Tuples and Dictionaries to bypass chat platform formatting bugs
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
MONTHS_DICT = {
    1: "january", 2: "february", 3: "march", 4: "april",
    5: "may", 6: "june", 7: "july", 8: "august",
    9: "september", 10: "october", 11: "november", 12: "december"
}

st.set_page_config(page_title="EB-2 & EB-3 India Visa Tracker", layout="wide")

# --- HIDE STREAMLIT BRANDING & MENUS ---
# Using chr(123) and chr(125) to safely create { and } for CSS without the chat UI breaking them
hide_st_style = "<style>\n"
hide_st_style += "#MainMenu " + chr(123) + "visibility: hidden;" + chr(125) + "\n"
hide_st_style += "header " + chr(123) + "visibility: hidden;" + chr(125) + "\n"
hide_st_style += "footer " + chr(123) + "visibility: hidden;" + chr(125) + "\n"
hide_st_style += " " + chr(123) + "visibility: hidden;" + chr(125) + "\n"
hide_st_style += "</style>"
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- UTILITY FUNCTIONS ---
def parse_priority_date(date_str, bulletin_date):
    if not date_str or pd.isna(date_str): 
        return pd.NaT
    date_str = str(date_str).strip().upper()
    
    if date_str in ("C", "CURRENT"):
        return bulletin_date
    if date_str in ("U", "UNAUTHORIZED", "UNAVAILABLE"):
        return pd.NaT
        
    try:
        return pd.to_datetime(date_str, format='%d%b%y')
    except:
        try:
            return pd.to_datetime(date_str)
        except:
            return pd.NaT

def get_bulletin_url(month_name, year):
    month_idx = MONTHS.index(month_name.lower()) + 1
    fiscal_year = year + 1 if month_idx >= 10 else year
    return f"https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/{fiscal_year}/visa-bulletin-for-{month_name.lower()}-{year}.html"

# --- SCRAPING LOGIC ---
def extract_india_dates(df_table):
    cols_as_list = df_table.columns.values.tolist()
    raw_data = list((cols_as_list,))
    raw_data.extend(df_table.values.tolist())
    
    india_col_idx = None
    for row in raw_data:
        for j, cell in enumerate(row):
            if 'INDIA' in str(cell).upper():
                india_col_idx = j
                break
        if india_col_idx is not None: 
            break
            
    second_row_idx = None
    third_row_idx = None
    
    for i, row in enumerate(raw_data):
        for cell in row:
            cell_str = str(cell).upper()
            if second_row_idx is None and re.search(r'\b2ND\b', cell_str):
                second_row_idx = i
            if third_row_idx is None and re.search(r'\b3RD\b', cell_str):
                third_row_idx = i
        if second_row_idx is not None and third_row_idx is not None:
            break
            
    eb2_date, eb3_date = None, None
    if india_col_idx is not None:
        for i, row in enumerate(raw_data):
            if i == second_row_idx:
                for j, cell in enumerate(row):
                    if j == india_col_idx: eb2_date = cell
            if i == third_row_idx:
                for j, cell in enumerate(row):
                    if j == india_col_idx: eb3_date = cell
                        
    return eb2_date, eb3_date

def fetch_bulletin_dates(month_name, year):
    url = get_bulletin_url(month_name, year)
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: 
            return pd.NaT, pd.NaT, pd.NaT, pd.NaT
        
        soup = BeautifulSoup(response.content, 'lxml')
        tables = pd.read_html(str(soup))
        
        dates_found_eb2 = list()
        dates_found_eb3 = list()
        
        for df_table in tables:
            eb2_d, eb3_d = extract_india_dates(df_table)
            if eb2_d: dates_found_eb2.append(eb2_d)
            if eb3_d: dates_found_eb3.append(eb3_d)
                
        bulletin_date = pd.to_datetime(f"01 {month_name} {year}")
        eb2_fad, eb2_dof, eb3_fad, eb3_dof = pd.NaT, pd.NaT, pd.NaT, pd.NaT
        
        for idx, date_val in enumerate(dates_found_eb2):
            if idx == 0: eb2_fad = parse_priority_date(date_val, bulletin_date)
            elif idx == 1: eb2_dof = parse_priority_date(date_val, bulletin_date)
            
        for idx, date_val in enumerate(dates_found_eb3):
            if idx == 0: eb3_fad = parse_priority_date(date_val, bulletin_date)
            elif idx == 1: eb3_dof = parse_priority_date(date_val, bulletin_date)
            
        return eb2_fad, eb2_dof, eb3_fad, eb3_dof
    except Exception:
        return pd.NaT, pd.NaT, pd.NaT, pd.NaT

def init_or_update_db():
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        df = df.assign(Bulletin_Date=pd.to_datetime(df.Bulletin_Date))
        df = df.assign(EB2_Filing=pd.to_datetime(df.EB2_Filing))
        df = df.assign(EB2_FAD=pd.to_datetime(df.EB2_FAD))
        df = df.assign(EB3_Filing=pd.to_datetime(df.EB3_Filing))
        df = df.assign(EB3_FAD=pd.to_datetime(df.EB3_FAD))
    else:
        df = pd.DataFrame(columns=('Bulletin_Date', 'EB2_Filing', 'EB2_FAD', 'EB3_Filing', 'EB3_FAD'))
        
    today = datetime.today()
    start_date = datetime(2017, 1, 1)
    
    next_month = today + pd.DateOffset(months=1)
    target_date = datetime(next_month.year, next_month.month, 1)
    current_month_start = datetime(today.year, today.month, 1)
    
    dates_to_check = pd.date_range(start=start_date, end=target_date, freq='MS')
    
    missing_dates = list()
    for d in dates_to_check:
        if df.empty or d not in df.Bulletin_Date.values:
            missing_dates.append(d)
            
    if missing_dates:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        new_rows = list()
        for i, d in enumerate(missing_dates):
            month_name = MONTHS_DICT.get(d.month)
            status_text.text(f"Scraping {month_name.capitalize()} {d.year}...")
            
            eb2_fad, eb2_dof, eb3_fad, eb3_dof = fetch_bulletin_dates(month_name, d.year)
            
            if pd.isna(eb2_fad) and pd.isna(eb3_fad):
                if d >= current_month_start:
                    break 
                else:
                    continue
            
            new_rows.append(dict(
                Bulletin_Date=d,
                EB2_Filing=eb2_dof,
                EB2_FAD=eb2_fad,
                EB3_Filing=eb3_dof,
                EB3_FAD=eb3_fad
            ))
            
            progress_bar.progress((i + 1) / len(missing_dates))
            time.sleep(0.3) 
            
        if new_rows:
            df_new = pd.DataFrame(new_rows)
            df = pd.concat((df, df_new), ignore_index=True)
            df = df.sort_values(by='Bulletin_Date').reset_index(drop=True)
            df.to_csv(DATA_FILE, index=False)
            status_text.text("Database fully synchronized with State Dept real dates!")
            time.sleep(2)
            st.rerun()
        else:
            time.sleep(1)
            status_text.empty()
            progress_bar.empty()
        
    return df


# --- UI & CHARTS ---
st.title("📈 EB-2 & EB-3 India Visa Bulletin Tracker")
st.markdown("Live scraping of Final Action Dates and Dates of Filing directly from the U.S. State Department.")

# --- SECRET ADMIN CONTROLS ---
# Check if the secret query parameter is present in the URL
query_params = st.query_params.to_dict()
if query_params.get("admin") == "true":
    with st.sidebar:
        st.markdown("### Admin Controls (Unlocked)")
        if st.button("Delete Database & Re-Scrape"):
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
                st.rerun()

with st.spinner("Checking for missing bulletin releases..."):
    df = init_or_update_db()

df_clean = df.dropna(subset=list(('EB2_Filing', 'EB2_FAD', 'EB3_Filing', 'EB3_FAD')), how='all')

# Layout Metrics
col1, col2, col3 = st.columns(3)
with col1:
    val1 = "N/A"
    if not df_clean.empty:
        val1 = df_clean.Bulletin_Date.tail(1).item().strftime('%B %Y')
    st.metric(label="Latest Bulletin Month", value=val1)
    
with col2:
    val2 = "N/A"
    if not df_clean.dropna(subset=list(('EB2_Filing',))).empty:
        val2 = df_clean.dropna(subset=list(('EB2_Filing',))).EB2_Filing.tail(1).item().strftime('%d %b %Y')
    st.metric(label="Latest EB-2 Date of Filing", value=val2)
    
with col3:
    val3 = "N/A"
    if not df_clean.dropna(subset=list(('EB3_Filing',))).empty:
        val3 = df_clean.dropna(subset=list(('EB3_Filing',))).EB3_Filing.tail(1).item().strftime('%d %b %Y')
    st.metric(label="Latest EB-3 Date of Filing", value=val3)

st.divider()

# Prepare DataFrames for plotting
df_plot_dof = pd.DataFrame(dict(
    Bulletin_Date=df_clean.Bulletin_Date,
    EB2=df_clean.EB2_Filing,
    EB3=df_clean.EB3_Filing
))

df_plot_fad = pd.DataFrame(dict(
    Bulletin_Date=df_clean.Bulletin_Date,
    EB2=df_clean.EB2_FAD,
    EB3=df_clean.EB3_FAD
))

# Chart 1: Date of Filing
st.subheader("🗓️ Date of Filing Movement (EB-2 vs EB-3)")
fig_dof = px.line(df_plot_dof.dropna(subset=list(('EB2', 'EB3')), how='all'), 
                  x='Bulletin_Date', y=list(('EB2', 'EB3')), 
                  markers=True, 
                  labels=dict(Bulletin_Date='Visa Bulletin Release Month', value='Cutoff Priority Date', variable='Category'),
                  line_shape='hv')
fig_dof.update_layout(yaxis=dict(tickformat="%b %Y"), xaxis=dict(tickformat="%b %Y"))
st.plotly_chart(fig_dof, use_container_width=True)

# Chart 2: Final Action Date
st.subheader("⚖️ Final Action Date Movement (EB-2 vs EB-3)")
fig_fad = px.line(df_plot_fad.dropna(subset=list(('EB2', 'EB3')), how='all'), 
                  x='Bulletin_Date', y=list(('EB2', 'EB3')), 
                  markers=True, 
                  labels=dict(Bulletin_Date='Visa Bulletin Release Month', value='Cutoff Priority Date', variable='Category'),
                  line_shape='hv')
fig_fad.update_layout(yaxis=dict(tickformat="%b %Y"), xaxis=dict(tickformat="%b %Y"))
st.plotly_chart(fig_fad, use_container_width=True)

# Data Table
with st.expander("View Scraped Raw Data"):
    st.dataframe(df.sort_values(by="Bulletin_Date", ascending=False).reset_index(drop=True))
