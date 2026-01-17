import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
import time
import os

# Selenium imports (optional fallback for dynamic content)
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
SLEEP_TIME = 1.2          # Slightly faster but still polite
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

    if any(kw in company_lower for kw in ["thermo fisher", "fisher scientific", "thermo scientific", "life technologies"]):
        return f"https://www.thermofisher.com/search/results?query={term}"

    elif any(kw in company_lower for kw in ["sigma-aldrich", "sigma aldrich", "milliporesigma", "merck"]):
        return f"https://www.sigmaaldrich.com/US/en/search/{term}?focus=products&page=1&perpage=30&sort=relevance&term={term}&type=product"

    elif any(kw in company_lower for kw in ["medchemexpress", "mce", "medchem express"]):
        return f"https://www.medchemexpress.com/search.html?kwd={term}"

    elif "abcam" in company_lower:
        return f"https://www.abcam.com/search?keywords={term}"

    elif "qiagen" in company_lower:
        return f"https://www.qiagen.com/us/search?query={term}"

    elif any(kw in company_lower for kw in ["stemcell", "stem cell"]):
        return f"https://www.stemcell.com/search?query={term}"

    elif any(kw in company_lower for kw in ["vwr", "avantor"]):
        return f"https://www.avantorsciences.com/us/en/search?text={term}"

    elif "addgene" in company_lower:
        return f"https://www.addgene.org/search/catalog/plasmids/?q={term}"

    elif any(kw in company_lower for kw in ["cayman chemical", "caymanchem"]):
        return f"https://www.caymanchem.com/search?q={term}"

    elif any(kw in company_lower for kw in ["cell signaling", "cellsignal"]):
        return f"https://www.cellsignal.com/search?keywords={term}"

    elif any(kw in company_lower for kw in ["santa cruz", "scbt"]):
        return f"https://www.scbt.com/search?query={term}"

    elif any(kw in company_lower for kw in ["new england biolabs", "neb"]):
        return f"https://www.neb.com/en-us/search?keyword={term}"

    elif any(kw in company_lower for kw in ["bio-rad", "biorad"]):
        return f"https://www.bio-rad.com/en-us/s?search={term}"

    elif "biolegend" in company_lower:
        return f"https://www.biolegend.com/en-us/search?keywords={term}"

    elif "zymo" in company_lower:
        return f"https://www.zymoresearch.com/search?q={term}"

    elif any(kw in company_lower for kw in ["integrated dna", "idtdna", "idt"]):
        return f"https://www.idtdna.com/search?query={term}"

    elif "invivogen" in company_lower:
        return f"https://www.invivogen.com/search?keywords={term}"

    elif "eurofins" in company_lower:
        return f"https://www.eurofinsgenomics.eu/search/?q={term}"

    # Fallback for remaining companies
    else:
        website_row = df.loc[df["Company Name"] == company_name, "Website"]
        if website_row.empty:
            return None
        base = website_row.values[0].rstrip("/")
        return f"{base}/search?q={term}"   # most common pattern — works for many

def extract_price(text: str) -> str:
    patterns = [
        r'\$[\s]*[\d,]+(?:\.\d{1,2})?',
        r'USD[\s]*[\d,]+(?:\.\d{1,2})?',
        r'€[\s]*[\d,]+(?:\.\d{1,2})?',
        r'(?:Price|List Price|Your Price):\s*[\$\€]?[\s]*[\d,]+(?:\.\d{1,2})?',
        r'Request Quote|Call for price|Login for price|Quote required|Contact us for pricing',
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return "Price not visible (likely requires login or quote request)"

def scrape_product_page(url: str | None) -> dict:
    if not url:
        return {"price": "No search link generated"}
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        return {"price": extract_price(text)}
    except Exception as e:
        return {"price": f"Page load error: {str(e)[:60]}"}

def scrape_with_selenium(url: str | None, company_name: str) -> str:
    if not SELENIUM_AVAILABLE or not url:
        return "Advanced scraping unavailable"
    # ... (keep your existing Selenium logic here – omitted for brevity) ...
    return "Selenium: price extraction attempted (details on page)"

# ---------------- UI ---------------- #
st.title("Reagent / Catalog Quote Lookup")
st.markdown("Enter reagent name and/or catalog number. Results show direct supplier search links + emails.")

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
            skipped = []
            progress = st.progress(0)
            total = len(df)

            for i, (_, row) in enumerate(df.iterrows()):
                url = vendor_direct_search(row["Company Name"], search_term)
                if url:
                    data = scrape_product_page(url)
                    if "not visible" in data["price"].lower() or "error" in data["price"].lower():
                        if SELENIUM_AVAILABLE:
                            data["price"] = scrape_with_selenium(url, row["Company Name"])
                        else:
                            data["price"] += " — click link to view results"

                    results.append({
                        "Company": row["Company Name"],
                        "Search Link": url,
                        "Sales Email": row["Email Address"],
                        "Price Info": data["price"],
                    })
                else:
                    skipped.append(row["Company Name"])

                progress.progress((i + 1) / total)
                time.sleep(SLEEP_TIME)

        if results:
            st.subheader(f"Results ({len(results)} suppliers)")
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
            st.caption("💡 Many suppliers hide prices until login or quote request. Use links to browse and email for quotes.")
        else:
            st.warning("No supplier search links could be generated. Try a different spelling or more specific term.")

        if skipped:
            with st.expander("Suppliers checked but no link generated"):
                st.write(", ".join(skipped))

        st.info("Tip: Catalog numbers usually give more precise results than names alone.")
