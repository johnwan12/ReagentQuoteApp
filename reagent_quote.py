import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
import time
import os

# Selenium imports (optional fallback)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    st.warning("Selenium not installed — basic scraping only (prices often hidden behind JS/login)")

# ---------------- CONFIG ---------------- #
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 12
SLEEP_TIME = 1.5  # Slightly increased for politeness
SELENIUM_WAIT_SEC = 6

# ---------------- LOAD DATA ---------------- #
EXCEL_FILE = "Companies.xlsx"

@st.cache_data(show_spinner="Loading company database...")
def load_data():
    if not os.path.exists(EXCEL_FILE):
        st.error(f"Excel file not found: {EXCEL_FILE}\nCurrent dir: {os.getcwd()}\nFiles: {os.listdir('.')}")
        st.stop()
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name="Sheet1")
        st.success(f"Loaded {len(df)} companies", icon="✅")
    except Exception as e:
        st.error(f"Failed to load {EXCEL_FILE}: {str(e)}")
        st.stop()

    websites = {
        "Thermo Fisher Life Technologies": "https://www.thermofisher.com",
        "Google": "https://www.google.com",
        "Fisher Scientific": "https://www.fishersci.com",
        "MCE (MedChemExpress LLC)": "https://www.medchemexpress.com",
        "Sigma-Aldrich Inc": "https://www.sigmaaldrich.com/US/en",
        "Abcam Inc": "https://www.abcam.com/en-us",
        # ... (your full websites dict here - omitted for brevity)
        "NEW ENGLAND BIOLABS INC": "https://www.neb.com/en-us"
    }
    df["Website"] = df["Company Name"].map(websites)
    df = df.dropna(subset=["Website"]).drop_duplicates("Company Name")
    df["Email Address"] = df["Email Address"].fillna("Not provided")
    return df

df = load_data()

# ---------------- HELPERS ---------------- #
def vendor_direct_search(company_name: str, search_term: str) -> str | None:
    # Your existing vendor_direct_search function (unchanged)
    # ... paste your full function here ...
    pass  # placeholder - keep your original implementation

def extract_price(text: str) -> str:
    # Your existing extract_price (unchanged)
    # ... paste your full function here ...
    return "Price not visible (likely requires login or quote request)"

def scrape_product_page(url: str | None) -> dict:
    if not url:
        return {"price": "No search link generated", "skip": False}

    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        
        if r.status_code == 404 or r.status_code in (410, 403):  # 404 Not Found, 410 Gone, sometimes 403 blocks
            return {
                "price": f"Page not found (HTTP {r.status_code})",
                "skip": True
            }
        
        r.raise_for_status()  # raises on 4xx/5xx except handled above
        
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        return {"price": extract_price(text), "skip": False}
    
    except requests.exceptions.HTTPError as http_err:
        if "404" in str(http_err):
            return {"price": "Page not found (404)", "skip": True}
        return {"price": f"HTTP error: {str(http_err)[:60]}", "skip": False}
    except Exception as e:
        return {"price": f"Page load error: {str(e)[:60]}", "skip": False}

def scrape_with_selenium(url: str | None, company_name: str) -> str:
    # Your placeholder or full Selenium logic (unchanged for now)
    return "Selenium: price extraction attempted (implement if needed)"

# ---------------- UI ---------------- #
st.title("Reagent / Catalog Quote Lookup")
st.markdown("Enter reagent name and/or catalog number. Results show direct supplier search links + emails. 404 pages are now hidden.")

col1, col2 = st.columns(2)
with col1:
    reagent = st.text_input("Reagent Name", placeholder="e.g. Nitrile gloves, DMEM", key="reagent")
with col2:
    catnum = st.text_input("Catalog Number (optional)", placeholder="e.g. 11732-010, 89000-496", key="catnum")

if st.button("Search Suppliers", type="primary"):
    if not reagent.strip() and not catnum.strip():
        st.warning("Please enter at least a reagent name or catalog number.")
    else:
        terms = [f'"{t.strip()}"' for t in [reagent, catnum] if t.strip()]
        search_term = " ".join(terms)
        
        with st.spinner(f"Checking suppliers for: **{search_term}** …"):
            results = []
            skipped = []       # General skips (no URL)
            not_found = []     # New: 404 / page not found
            progress = st.progress(0)
            total = len(df)
            
            for i, (_, row) in enumerate(df.iterrows()):
                company = row["Company Name"]
                url = vendor_direct_search(company, search_term)
                
                if not url:
                    skipped.append(company)
                else:
                    data = scrape_product_page(url)
                    
                    if data.get("skip", False):
                        not_found.append(company)
                    else:
                        # Optional: try Selenium if price looks hidden
                        if "not visible" in data["price"].lower() and SELENIUM_AVAILABLE:
                            data["price"] = scrape_with_selenium(url, company)
                        
                        results.append({
                            "Company": company,
                            "Search Link": url,
                            "Sales Email": row["Email Address"],
                            "Price Info": data["price"],
                        })
                
                progress.progress((i + 1) / total)
                time.sleep(SLEEP_TIME)
        
        if results:
            st.subheader(f"Results ({len(results)} suppliers with valid pages)")
            st.dataframe(
                pd.DataFrame(results),
                column_config={
                    "Search Link": st.column_config.LinkColumn("Search Link", display_text="Open Search"),
                    "Sales Email": "Contact Email",
                    "Price Info": "Price / Status",
                },
                use_container_width=True,
                hide_index=True,
            )
            st.caption("💡 Many suppliers hide prices until login or quote request. Use links to browse / email for quotes.")
        else:
            st.warning("No valid supplier pages found for this search term.")
        
        if skipped or not_found:
            with st.expander("Suppliers checked but excluded"):
                if skipped:
                    st.write(f"**No search URL generated:** {', '.join(skipped)}")
                if not_found:
                    st.write(f"**Page not found (404):** {', '.join(not_found)}")
        
        st.info("Tip: Catalog numbers usually give more precise results than names alone.")
