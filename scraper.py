import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import re

# --- CONSTANTS & CONFIG ---
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
MONTHS_DICT = dict()
MONTHS_DICT.update({
    1: "january", 2: "february", 3: "march", 4: "april",
    5: "may", 6: "june", 7: "july", 8: "august",
    9: "september", 10: "october", 11: "november", 12: "december"
})

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
    except Exception:
        try:
            return pd.to_datetime(date_str)
        except Exception:
            return pd.NaT

def get_bulletin_url(month_name, year):
    month_idx = MONTHS.index(month_name.lower()) + 1
    fiscal_year = year + 1 if month_idx >= 10 else year
    return f"https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/{fiscal_year}/visa-bulletin-for-{month_name.lower()}-{year}.html"

def extract_india_dates(df_table):
    raw_data = list()
    
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
    headers = dict()
    headers.setdefault("User-Agent", "Mozilla/5.0")
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200: 
            return pd.NaT, pd.NaT, pd.NaT, pd.NaT
        
        soup = BeautifulSoup(response.content, 'lxml')
        tables = pd.read_html(str(soup))
        
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

def run_scraper():
    print("🚀 Starting local scrape of Visa Bulletins...")
    start_date = datetime(2017, 1, 1)
    today = datetime.today()
    
    # Calculate target (next month)
    next_month = today + pd.DateOffset(months=1)
    target_date = datetime(next_month.year, next_month.month, 1)
    current_month_start = datetime(today.year, today.month, 1)
    
    dates_to_check = pd.date_range(start=start_date, end=target_date, freq='MS')
    new_rows = list()
    
    for d in dates_to_check:
        month_name = MONTHS_DICT.get(d.month)
        print(f"Scraping {month_name.capitalize()} {d.year}...")
        
        eb2_fad, eb2_dof, eb3_fad, eb3_dof = fetch_bulletin_dates(month_name, d.year)
        
        if pd.isna(eb2_fad) and pd.isna(eb3_fad):
            if d >= current_month_start:
                print("   -> Not published yet. Stopping.")
                break 
            else:
                print("   -> Data format mismatch or missing. Skipping.")
                continue
        
        new_rows.append(dict(
            Bulletin_Date=d,
            EB2_Filing=eb2_dof,
            EB2_FAD=eb2_fad,
            EB3_Filing=eb3_dof,
            EB3_FAD=eb3_fad
        ))
        
        # Be polite to the State Dept servers
        time.sleep(0.5) 
        
    if new_rows:
        df = pd.DataFrame(new_rows)
        df = df.sort_values(by='Bulletin_Date').reset_index(drop=True)
        df.to_csv('eb2_india_data.csv', index=False)
        print(f"\n✅ Success! Scraped {len(new_rows)} months of data.")
        print("💾 File saved as: eb2_india_data.csv")
    else:
        print("\n❌ No data was extracted.")

if __name__ == "__main__":
    run_scraper()
