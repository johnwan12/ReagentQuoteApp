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
SLEEP_TIME = 2.0
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
        "Addgene Inc": "https://www.addgene.org",
        "Bio-Rad Laboratories Inc": "https://www.bio-rad.com",
        "QIAGEN LLC": "https://www.qiagen.com/us",
        "STEMCELL Technologies Inc": "https://www.stemcell.com",
        "Zymo Research Corp": "https://www.zymoresearch.com",
        "VWR International LLC": "https://www.avantorsciences.com/us/en",
        "Alkali Scientific LLC": "https://alkalisci.com/",
        "Baker Company": "https://bakerco.com/",
        "BioLegend Inc": "https://www.biolegend.com/",
        "Cayman Chemical Company Inc": "https://www.caymanchem.com/",
        "Cell Signaling Technology": "https://www.cellsignal.com/",
        "Cerillo, Inc.": "https://cerillo.bio/",
        "Cole-Parmer": "https://www.coleparmer.com/",
        "Corning Incorporated": "https://www.corning.com/life-sciences",
        "Creative Biogene": "https://microbiosci.creative-biogene.com/",
        "Creative Biolabs Inc": "https://www.creative-biolabs.com/",
        "Eurofins Genomics LLC": "https://www.eurofinsgenomics.eu/",
        "Genesee Scientific LLC": "https://www.geneseesci.com/",
        "Integrated DNA Technologies Inc": "https://www.idtdna.com/",
        "InvivoGen": "https://www.invivogen.com/",
        "LI-COR Biotech LLC": "https://www.licorbio.com/",
        "Omega Bio-tek Inc": "https://omegabiotek.com/",
        "PEPperPRINT GmbH": "https://www.pepperprint.com/",
        "Pipette.com": "https://pipette.com/",
        "Santa Cruz Biotechnology": "https://www.scbt.com/",
        "RWD Life Science Inc": "https://www.rwdstco.com/",
        "IBL-America": "https://www.ibl-america.com/",
        "Thomas Scientific INC": "https://www.thomassci.com/",
        "INVENT BIOTECHNOLOGIES INC": "https://inventbiotech.com/",
        "NEW ENGLAND BIOLABS INC": "https://www.neb.com/en-us"
    }
    df["Website"] = df["Company Name"].map(websites)
    df = df.dropna(subset=["Website"]).drop_duplicates("Company Name")
    df["Email Address"] = df["Email Address"].fillna("Not provided")
    return df

df = load_data()

# ---------------- HELPERS ---------------- #
def vendor_direct_search(company_name: str, search_term: str) -> str | None:
    term = quote(search_term.strip())
    company_lower = company_name.lower().strip()

    # Sigma-Aldrich: prefer direct product link for catalog numbers
    if any(kw in company_lower for kw in ["sigma-aldrich", "sigma aldrich", "milliporesigma", "merck"]):
        cat_match = re.match(r'^([A-Za-z]+\d+)(?:[-]\d+[A-Za-z]?)?$', search_term.strip())
        if cat_match:
            base_cat = cat_match.group(1).upper()
            return f"https://www.sigmaaldrich.com/US/en/product/sigma/{base_cat}"
        else:
            return f"https://www.sigmaaldrich.com/US/en/search/{term}?focus=products&page=1&perpage=30&sort=relevance&term={term}&type=product"

    # Thermo Fisher
    if any(kw in company_lower for kw in ["thermo fisher", "fisher scientific", "thermo scientific", "life technologies"]):
        return f"https://www.thermofisher.com/search/results?query={term}"

    # MedChemExpress
    if any(kw in company_lower for kw in ["medchemexpress", "mce", "medchem express"]):
        return f"https://www.medchemexpress.com/search.html?kwd={term}"

    # Abcam
    if "abcam" in company_lower:
        return f"https://www.abcam.com/search?keywords={term}"

    # ... (add other specific vendors as needed)

    # Generic fallback
    website_row = df.loc[df["Company Name"] == company_name, "Website"]
    if website_row.empty:
        return None
    base = website_row.values[0].rstrip("/")
    return f"{base}/search?q={term}"

def extract_price(text: str) -> str:
    patterns = [
        r'\$[\s]*[\d,]+(?:\.\d{1,2})?',
        r'USD[\s]*[\d,]+(?:\.\d{1,2})?',
        r'€[\s]*[\d,]+(?:\.\d{1,2})?',
        r'(?:Price|List Price|Your Price|Catalog Price):\s*[\$\€]?[\s]*[\d,]+(?:\.\d{1,2})?',
        r'Request Quote|Call for price|Login for price|Quote required|Contact us for pricing|Sign In to View|Login Required',
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return "Price not visible (likely requires login or quote request)"

def scrape_product_page(url: str | None) -> dict:
    if not url:
        return {"price": "No link generated", "skip": True}

    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        
        if r.status_code in (404, 410, 403, 500, 502):
            return {"price": f"Page not available (HTTP {r.status_code})", "skip": True}
        
        r.raise_for_status()
        
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        return {"price": extract_price(text), "skip": False}
    
    except Exception as e:
        error_str = str(e).lower()
        if "404" in error_str or "403" in error_str or "connection" in error_str:
            return {"price": "Access failed", "skip": True}
        return {"price": f"Error: {str(e)[:60]}", "skip": False}

def scrape_with_selenium(url: str | None, company_name: str) -> str:
    if not SELENIUM_AVAILABLE or not url:
        return "Selenium unavailable"
    # Placeholder - add real implementation if needed
    return "Selenium: attempted"

# ---------------- UI ---------------- #
st.title("Reagent / Catalog Quote Lookup")
st.markdown("Input reagent or catalog number → only suppliers with valid pages are shown in results.")

col1, col2 = st.columns(2)
with col1:
    reagent = st.text_input("Reagent Name", placeholder="e.g. DMEM, Anti-CD3", key="reagent")
with col2:
    catnum = st.text_input("Catalog Number", placeholder="e.g. B7880-5MG, 11965-092", key="catnum")

if st.button("Search Suppliers", type="primary"):
    if not reagent.strip() and not catnum.strip():
        st.warning("Please enter at least a reagent name or catalog number.")
    else:
        terms = [f'"{t.strip()}"' for t in [reagent, catnum] if t.strip()]
        search_term = " ".join(terms)
        
        with st.spinner(f"Searching: **{search_term}** …"):
            results = []
            excluded = []  # All companies that were removed (no URL or invalid page)
            progress = st.progress(0)
            total = len(df)
            
            for i, (_, row) in enumerate(df.iterrows()):
                company = row["Company Name"]
                url = vendor_direct_search(company, search_term)
                
                if not url:
                    excluded.append(f"{company} — no search URL")
                else:
                    data = scrape_product_page(url)
                    
                    if data.get("skip", False):
                        reason = data["price"] if data["price"] else "Page invalid"
                        excluded.append(f"{company} — {reason}")
                    else:
                        # Optional Selenium fallback for hidden prices
                        if "not visible" in data["price"].lower() or "login" in data["price"].lower():
                            if SELENIUM_AVAILABLE:
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
            st.subheader(f"Found valid pages ({len(results)} suppliers)")
            st.dataframe(
                pd.DataFrame(results),
                column_config={
                    "Search Link": st.column_config.LinkColumn("Search Link", display_text="Open"),
                    "Sales Email": "Email",
                    "Price Info": "Price / Status",
                },
                use_container_width=True,
                hide_index=True,
            )
            st.caption("Note: Prices often require login or quote request on vendor sites.")
        else:
            st.warning("No suppliers returned a valid page for this search.")
        
        if excluded:
            with st.expander(f"Excluded companies ({len(excluded)})"):
                for item in excluded:
                    st.write(f"- {item}")
        
        st.info("Tip: Catalog numbers (e.g. B7880-5MG) usually give better / more direct results.")
