import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
import time
import os

# Optional Selenium fallback
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# ---------------- CONFIG ---------------- #
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 12
SLEEP_TIME = 2.0          # Increased for politeness / anti-blocking
MAX_RETRIES = 2

# ---------------- LOAD COMPANY DATA ---------------- #
EXCEL_FILE = "Companies.xlsx"

@st.cache_data(show_spinner="Loading supplier database...")
def load_data():
    if not os.path.exists(EXCEL_FILE):
        st.error(f"Excel file not found: {EXCEL_FILE}\nCurrent dir: {os.getcwd()}")
        st.stop()
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"Failed to load {EXCEL_FILE}: {str(e)}")
        st.stop()

    # Your hardcoded website mappings (can be moved to Excel later)
    websites = {
        "Thermo Fisher Life Technologies": "https://www.thermofisher.com",
        "Google": "https://www.google.com",
        "Fisher Scientific": "https://www.fishersci.com",
        "MCE (MedChemExpress LLC)": "https://www.medchemexpress.com",
        "Sigma-Aldrich Inc": "https://www.sigmaaldrich.com/US/en",
        "Abcam Inc": "https://www.abcam.com/en-us",
        # ... (keep all your other mappings here)
        "NEW ENGLAND BIOLABS INC": "https://www.neb.com/en-us"
    }
    df["Website"] = df["Company Name"].map(websites)
    df = df.dropna(subset=["Website"]).drop_duplicates("Company Name")
    df["Email Address"] = df["Email Address"].fillna("Not provided")
    return df

df = load_data()

# ---------------- VENDOR-SPECIFIC SEARCH URL BUILDERS ---------------- #
def vendor_direct_search(company_name: str, search_term: str) -> str | None:
    term = quote(search_term.strip())
    company_lower = company_name.lower().strip()

    if any(kw in company_lower for kw in ["thermo fisher", "fisher scientific", "thermo scientific"]):
        return f"https://www.thermofisher.com/search/results?query={term}"
    elif any(kw in company_lower for kw in ["sigma-aldrich", "sigma aldrich", "milliporesigma"]):
        return f"https://www.sigmaaldrich.com/US/en/search/{term}?focus=products&page=1&perpage=30&sort=relevance&term={term}&type=product"
    elif any(kw in company_lower for kw in ["medchemexpress", "mce"]):
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
    elif "cayman chemical" in company_lower:
        return f"https://www.caymanchem.com/search?q={term}"
    elif "cell signaling" in company_lower:
        return f"https://www.cellsignal.com/search?keywords={term}"
    elif any(kw in company_lower for kw in ["santa cruz", "scbt"]):
        return f"https://www.scbt.com/search?query={term}"
    elif any(kw in company_lower for kw in ["new england biolabs", "neb"]):
        return f"https://www.neb.com/en-us/search?keyword={term}"
    # Fallback generic pattern
    website = df.loc[df["Company Name"] == company_name, "Website"]
    if website.empty:
        return None
    base = website.values[0].rstrip("/")
    return f"{base}/search?q={term}"

# ---------------- PRICE / STATUS EXTRACTION ---------------- #
def extract_status_from_page(text: str) -> str:
    text_lower = text.lower()

    # Priority: No-results / not-found patterns
    no_results_indicators = [
        r'no results', r'0 results', r'no matches found',
        r'there are no results', r'couldn\'?t find', r'we couldn\'?t find',
        r'sorry.*no.*found', r'sorry.*not available', r'sorry.*not matched',
        r'no products found', r'your search.*not found', r'no items match',
        r'nothing found', r'0 items', r'no matching products',
    ]
    for pat in no_results_indicators:
        if re.search(pat, text_lower):
            return "No results found (item likely not carried by this supplier)"

    # Common B2B price-hiding phrases
    hidden_price_indicators = [
        r'request quote', r'call for price', r'login for price',
        r'quote required', r'contact us for pricing', r'log in to see price',
        r'price on request', r'pricing upon request',
    ]
    for pat in hidden_price_indicators:
        if re.search(pat, text_lower):
            return "Price hidden (login or quote required)"

    # Actual price patterns (rare on public pages)
    price_patterns = [
        r'\$[\s]*[\d,]+(?:\.\d{1,2})?',
        r'USD[\s]*[\d,]+(?:\.\d{1,2})?',
        r'€[\s]*[\d,]+(?:\.\d{1,2})?',
        r'(?:Price|List Price|Your Price):\s*[\$\€]?[\s]*[\d,]+(?:\.\d{1,2})?',
    ]
    for pat in price_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()

    # Default fallback
    return "Price / availability not visible (may require login or be dynamic)"

# ---------------- SCRAPING FUNCTIONS ---------------- #
def scrape_product_page(url: str | None) -> dict:
    if not url:
        return {"status": "No search link generated"}

    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if r.status_code == 404:
                return {"status": "404 - Page not found"}
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")
            visible_text = soup.get_text(" ", strip=True)
            status = extract_status_from_page(visible_text)

            return {"status": status}

        except requests.exceptions.RequestException as e:
            if attempt == MAX_RETRIES:
                return {"status": f"Request failed: {str(e)[:80]}"}
            time.sleep(2 ** attempt * 3)  # exponential backoff

    return {"status": "Unknown error"}

# Selenium fallback (placeholder – expand if needed)
def scrape_with_selenium(url: str | None) -> str:
    if not SELENIUM_AVAILABLE or not url:
        return "Selenium not available"
    # ... implement headless Chrome logic here if desired ...
    return "Selenium: advanced scrape attempted"

# ---------------- STREAMLIT UI ---------------- #
st.title("Reagent / Catalog Quote Lookup")
st.markdown("Quickly generate direct supplier search links and check availability / pricing status.")

col1, col2 = st.columns(2)
with col1:
    reagent = st.text_input("Reagent Name", placeholder="e.g. DMEM, Anti-GFP antibody", key="reagent")
with col2:
    catnum = st.text_input("Catalog Number (optional – preferred)", placeholder="e.g. 11965-092, ab290", key="catnum")

if st.button("Search Suppliers", type="primary"):
    if not reagent.strip() and not catnum.strip():
        st.warning("Please enter at least a reagent name or catalog number.")
    else:
        # Build search term – catalog number gets priority & quotes
        terms = []
        if catnum.strip():
            terms.append(f'"{catnum.strip()}"')
        if reagent.strip():
            terms.append(reagent.strip())
        search_term = " ".join(terms)

        st.subheader(f"Searching for: **{search_term}**")

        results = []
        skipped = []
        progress = st.progress(0)
        total = len(df)

        for i, (_, row) in enumerate(df.iterrows()):
            company = row["Company Name"]
            url = vendor_direct_search(company, search_term)

            if url:
                data = scrape_product_page(url)
                status = data["status"]

                # Optional: try Selenium if clearly hidden/dynamic (uncomment if installed)
                # if "not visible" in status.lower() and SELENIUM_AVAILABLE:
                #     status = scrape_with_selenium(url)

                results.append({
                    "Company": company,
                    "Search Link": url,
                    "Sales Email": row["Email Address"],
                    "Status": status,
                })
            else:
                skipped.append(company)

            progress.progress((i + 1) / total)
            time.sleep(SLEEP_TIME)

        if results:
            st.subheader(f"Results from {len(results)} suppliers")
            st.dataframe(
                pd.DataFrame(results),
                column_config={
                    "Search Link": st.column_config.LinkColumn(
                        "Search Link", display_text="View Search Page"
                    ),
                    "Sales Email": st.column_config.TextColumn("Contact Email"),
                    "Status": st.column_config.TextColumn(
                        "Price / Availability Status",
                        help="Most suppliers hide prices until login or quote request. "
                             "'No results found' usually means the supplier does not carry this item."
                    ),
                },
                use_container_width=True,
                hide_index=True,
            )

            st.info(
                "💡 **Common outcomes explained**\n\n"
                "• **No results found** → Supplier likely does not stock this product\n"
                "• **Price hidden (login or quote required)** → Standard for most life-science vendors\n"
                "• **$XXX.XX** → Rare public list price – you got lucky!\n"
                "• **404 / error** → Bad search URL or temporary issue\n\n"
                "For accurate pricing, click the link, log in with your institutional account, or email sales directly."
            )

        else:
            st.warning("No supplier search links could be generated.")

        if skipped:
            with st.expander(f"Suppliers skipped (no search pattern defined: {len(skipped)})"):
                st.write(", ".join(skipped))
