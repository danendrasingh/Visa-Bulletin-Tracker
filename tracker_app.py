import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import plotly.express as px
from datetime import datetime
import os
import time
import re
import urllib.parse

# --- CONSTANTS & CONFIG ---
DATA_FILE = 'eb2_india_data.csv'

MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
MONTHS_DICT = {
    1: "january", 2: "february", 3: "march", 4: "april",
    5: "may", 6: "june", 7: "july", 8: "august",
    9: "september", 10: "october", 11: "november", 12: "december"
}

st.set_page_config(page_title="EB-2 & EB-3 India Visa Tracker", layout="wide")

# --- HIDE STREAMLIT BRANDING & MENUS ---
hide_st_style = "<style>\n"
hide_st_style += "#MainMenu " + chr(123) + "visibility: hidden;" + chr(125) + "\n"
hide_st_style += ".stDeployButton " + chr(123) + "display: none;" + chr(125) + "\n"
hide_st_style += "footer " + chr(123) + "visibility: hidden;" + chr(125) + "\n"
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

def fetch_html_content(url):
    """Fetches HTML and uses free proxies if the US Gov firewall blocks the Cloud IP"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    # 1. Try Direct Request First
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200 and "Access Denied" not in res.text:
            return res.text
    except Exception:
        pass
        
    # 2. Proxy Fallback (Bypasses Akamai Firewall blocking Streamlit Cloud)
    try:
        proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(url)}"
        proxy_res = requests.get(proxy_url, headers=headers, timeout=15)
        if proxy_res.status_code == 200 and "Access Denied" not in proxy_res.text:
            return proxy_res.text
    except Exception:
        pass

    return None

# --- SCRAPING LOGIC ---
def extract_india_dates(df_table):
    raw_data = list()
    
    # Securely map headers and rows
    if isinstance(df_table.columns, pd.MultiIndex):
        raw_data.extend(list(list(c) for c in df_table.columns.values))
    else:
        raw_data.append(df_table.columns.values.tolist())
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
            if second_row_idx is None and "2ND" in cell_str:
                second_row_idx = i
            if third_row_idx is None and "3RD" in cell_str:
                third_row_idx = i
            
    eb2_date, eb3_date = None, None
    if india_col_idx is not None:
        if second_row_idx is not None and second_row_idx < len(raw_data):
            try: eb2_date = raw_data[second_row_idx][india_col_idx]
            except Exception: pass
        if third_row_idx is not None and third_row_idx < len(raw_data):
            try: eb3_date = raw_data[third_row_idx][india_col_idx]
            except Exception: pass
                        
    return eb2_date, eb3_date

def fetch_bulletin_dates(month_name, year):
    url = get_bulletin_url(month_name, year)
    html_content = fetch_html_content(url)
    
    if not html_content:
        return pd.NaT, pd.NaT, pd.NaT, pd.NaT
        
    try:
        tables = pd.read_html(html_content)
        
        dates_found_eb2 = list()
        dates_found_eb3 = list()
        
        for df_table in tables:
            eb2_d, eb3_d = extract_india_dates(df_table)
            if eb2_d is not None and str(eb2_d).strip() != "": 
                dates_found_eb2.append(eb2_d)
            if eb3_d is not None and str(eb3_d).strip() != "": 
                dates_found_eb3.append(eb3_d)
                
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
        skipped_count = 0
        
        for i, d in enumerate(missing_dates):
            month_name = MONTHS_DICT.get(d.month)
            status_text.text(f"Proxy Scraping {month_name.capitalize()} {d.year} (Bypassing Firewall)...")
            
            eb2_fad, eb2_dof, eb3_fad, eb3_dof = fetch_bulletin_dates(month_name, d.year)
            
            if pd.isna(eb2_fad) and pd.isna(eb3_fad):
                if d >= current_month_start:
                    break 
                else:
                    skipped_count += 1
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
            status_text.success(f"Database synced! ({skipped_count} invalid historical links bypassed)")
            time.sleep(2)
            st.rerun()
        else:
            time.sleep(1)
            status_text.error("Network firewall blocked the request entirely. Upload historical CSV manually.")
            progress_bar.empty()
        
    return df

# --- UI & CHARTS ---
st.title("📈 EB-2 & EB-3 India Visa Bulletin Tracker")
st.markdown("Live scraping of Final Action Dates and Dates of Filing directly from the U.S. State Department.")

is_admin = False
try:
    if str(st.query_params.get("admin", "")).lower() == "true":
        is_admin = True
except Exception:
    pass

if is_admin:
    with st.sidebar:
        st.markdown("### Admin Controls (Unlocked)")
        if st.button("Delete Database & Re-Scrape"):
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
                st.rerun()

with st.spinner("Bypassing firewall and fetching data..."):
    df = init_or_update_db()

df_clean = df.dropna(subset=list(('EB2_Filing', 'EB2_FAD', 'EB3_Filing', 'EB3_FAD')), how='all')

col1, col2, col3 = st.columns(3)
with col1:
    val1 = "N/A"
    if not df_clean.empty:
        val1 = df_clean.Bulletin_Date.iloc[-1].strftime('%B %Y')
    st.metric(label="Latest Bulletin Month", value=val1)
    
with col2:
    val2 = "N/A"
    df_eb2 = df_clean.dropna(subset=list(('EB2_Filing',)))
    if not df_eb2.empty:
        val2 = df_eb2.EB2_Filing.iloc[-1].strftime('%d %b %Y')
    st.metric(label="Latest EB-2 Date of Filing", value=val2)
    
with col3:
    val3 = "N/A"
    df_eb3 = df_clean.dropna(subset=list(('EB3_Filing',)))
    if not df_eb3.empty:
        val3 = df_eb3.EB3_Filing.iloc[-1].strftime('%d %b %Y')
    st.metric(label="Latest EB-3 Date of Filing", value=val3)

st.divider()

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

st.subheader("🗓️ Date of Filing Movement (EB-2 vs EB-3)")
df_plot_dof_clean = df_plot_dof.dropna(subset=list(('EB2', 'EB3')), how='all')

# Prevent crash if data is empty
if not df_plot_dof_clean.empty:
    fig_dof = px.line(df_plot_dof_clean, 
                      x='Bulletin_Date', y=list(('EB2', 'EB3')), 
                      markers=True, 
                      labels=dict(Bulletin_Date='Visa Bulletin Release Month', value='Cutoff Priority Date', variable='Category'),
                      line_shape='hv')
    fig_dof.update_layout(yaxis=dict(tickformat="%b %Y"), xaxis=dict(tickformat="%b %Y"))
    st.plotly_chart(fig_dof, use_container_width=True, key="dof_chart")
else:
    st.info("No data available to plot Date of Filing.")

st.subheader("⚖️ Final Action Date Movement (EB-2 vs EB-3)")
df_plot_fad_clean = df_plot_fad.dropna(subset=list(('EB2', 'EB3')), how='all')

# Prevent crash if data is empty
if not df_plot_fad_clean.empty:
    fig_fad = px.line(df_plot_fad_clean, 
                      x='Bulletin_Date', y=list(('EB2', 'EB3')), 
                      markers=True, 
                      labels=dict(Bulletin_Date='Visa Bulletin Release Month', value='Cutoff Priority Date', variable='Category'),
                      line_shape='hv')
    fig_fad.update_layout(yaxis=dict(tickformat="%b %Y"), xaxis=dict(tickformat="%b %Y"))
    st.plotly_chart(fig_fad, use_container_width=True, key="fad_chart")
else:
    st.info("No data available to plot Final Action Date.")

with st.expander("View Scraped Raw Data"):
    st.dataframe(df.sort_values(by="Bulletin_Date", ascending=False).reset_index(drop=True))
    
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Database to File",
        data=csv,
        file_name='eb2_india_data.csv',
        mime='text/csv',
    )
