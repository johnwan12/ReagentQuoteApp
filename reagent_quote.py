import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
import time
import os

# Selenium imports (fallback for dynamic prices)
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
    st.warning("Selenium not installed – using basic scraping only (prices may be missed)")

# ---------------- CONFIG ---------------- #
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 12
SLEEP_TIME = 1.5
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
        "VWR International LLC": "https://www.avantorsciences.com/us/en/",
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

    # Thermo Fisher variants
    if any(kw in company_lower for kw in ["thermo fisher", "fisher scientific", "thermo scientific", "life technologies"]):
        return f"https://www.thermofisher.com/search/results?query={term}"

    # Sigma-Aldrich / MilliporeSigma
    elif any(kw in company_lower for kw in ["sigma-aldrich", "sigma aldrich", "milliporesigma", "merck"]):
        return (
            f"https://www.sigmaaldrich.com/US/en/search/{term}?"
            f"focus=products&page=1&perpage=30&sort=relevance&term={term}&type=product"
        )

    # MedChemExpress (MCE)
    elif any(kw in company_lower for kw in ["medchemexpress", "mce", "medchem express"]):
        return f"https://www.medchemexpress.com/search.html?kwd={term}"

    # Abcam
    elif "abcam" in company_lower:
        return f"https://www.abcam.com/search?keywords={term}"

    # QIAGEN
    elif "qiagen" in company_lower:
        return f"https://www.qiagen.com/us/search?query={term}"

    # STEMCELL Technologies
    elif any(kw in company_lower for kw in ["stemcell", "stem cell", "stemcell technologies"]):
        return f"https://www.stemcell.com/search?query={term}"

    # Avantor / VWR
    elif any(kw in company_lower for kw in ["vwr", "avantor"]):
        return f"https://www.avantorsciences.com/us/en/search?query={term}"

    # Addgene
    elif "addgene" in company_lower:
        return f"https://www.addgene.org/search/catalog/plasmids/?q={term}"

    # Cayman Chemical
    elif any(kw in company_lower for kw in ["cayman chemical", "caymanchem"]):
        return f"https://www.caymanchem.com/search?q={term}"

    # Cell Signaling Technology
    elif any(kw in company_lower for kw in ["cell signaling", "cellsignal"]):
        return f"https://www.cellsignal.com/search?keywords={term}"

    # Santa Cruz Biotechnology
    elif any(kw in company_lower for kw in ["santa cruz", "scbt"]):
        return f"https://www.scbt.com/search?query={term}"

    # New England Biolabs (NEB)
    elif any(kw in company_lower for kw in ["new england biolabs", "neb"]):
        return f"https://www.neb.com/en-us/search?keyword={term}"

    # Bio-Rad
    elif any(kw in company_lower for kw in ["bio-rad", "biorad"]):
        return f"https://www.bio-rad.com/en-us/s?search={term}"

    # BioLegend
    elif "biolegend" in company_lower:
        return f"https://www.biolegend.com/en-us/search?keywords={term}"

    # Zymo Research
    elif "zymo" in company_lower or "zymoresearch" in company_lower:
        return f"https://www.zymoresearch.com/search?q={term}"

    # Integrated DNA Technologies (IDT)
    elif any(kw in company_lower for kw in ["integrated dna", "idtdna", "idt"]):
        return f"https://www.idtdna.com/search?query={term}"

    # InvivoGen
    elif "invivogen" in company_lower:
        return f"https://www.invivogen.com/search?keywords={term}"

    # Eurofins Genomics
    elif "eurofins" in company_lower:
        return f"https://www.eurofinsgenomics.eu/search/?q={term}"

    # Fallback: try common search endpoint using known homepage
    else:
        website_row = df.loc[df["Company Name"] == company_name, "Website"]
        if website_row.empty:
            return None
        base = website_row.values[0].rstrip("/")
        # Try two most common patterns
        for pattern in [f"{base}/search?q={term}", f"{base}/search?keywords={term}", f"{base}/search?query={term}"]:
            try:
                r = requests.head(pattern, headers=HEADERS, timeout=4, allow_redirects=True)
                if r.status_code < 400:
                    return pattern
            except:
                pass
        # If no search endpoint guessed, return homepage
        return base

def extract_price(text: str) -> str:
    patterns = [
        r'\$[\s]*[\d,]+(?:\.\d{1,2})?',
        r'USD[\s]*[\d,]+(?:\.\d{1,2})?',
        r'€[\s]*[\d,]+(?:\.\d{1,2})?',
        r'[\d,]+(?:\.\d{1,2})?[\s]*(?:USD|EUR|\$|€)',
        r'(?:Price|List Price|Your Price|Catalog Price):\s*[\$\€]?[\s]*[\d,]+(?:\.\d{1,2})?',
        r'Request Quote|Call for price|Login for price|Quote required|Contact us for pricing|Login Required',
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return "Not found (may require login/JS)"

def scrape_product_page(url: str | None) -> dict:
    if not url:
        return {"price": "No link available"}
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        return {"price": extract_price(text)}
    except Exception as e:
        return {"price": f"Request error: {str(e)[:60]}"}

def scrape_with_selenium(url: str | None, company_name: str) -> str:
    if not SELENIUM_AVAILABLE:
        return "Selenium not available"
    if not url:
        return "No valid URL"
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    # Adjust paths if needed for your deployment environment
    options.binary_location = os.getenv("CHROME_BIN", "/usr/bin/chromium")
    service = Service(os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver"))
    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
        time.sleep(3)
        company_lower = company_name.lower()
        # Example: Sigma-Aldrich price table
        if "sigma-aldrich" in company_lower:
            try:
                expand = WebDriverWait(driver, SELENIUM_WAIT_SEC).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".expandArrow, [aria-label*='expand'], .pricing-toggle"))
                )
                expand.click()
                time.sleep(2)
                table = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, "productSizePriceQtyTable"))
                )
                prices = [row.text.strip() for row in table.find_elements(By.TAG_NAME, "tr")[1:]]
                if prices:
                    driver.quit()
                    return " | ".join(prices[:3])
            except:
                pass
        # General fallback
        text = driver.find_element(By.TAG_NAME, "body").text
        driver.quit()
        return extract_price(text)
    except Exception as e:
        if driver:
            driver.quit()
        return f"Selenium error: {str(e)[:80]}"

# ---------------- UI ---------------- #
st.title("Reagent Quote Lookup")
st.markdown("Search by reagent name, catalog number, or both.\nOnly suppliers with product links are shown.")

col1, col2 = st.columns(2)
with col1:
    reagent = st.text_input("Reagent Name", placeholder="e.g. 8-Bromoadenosine, DMEM", key="reagent")
with col2:
    catnum = st.text_input("Catalog Number", placeholder="e.g. 11965-092, B6272", key="catnum")

if st.button("Search", type="primary"):
    if not reagent.strip() and not catnum.strip():
        st.warning("Enter at least a reagent name or catalog number.")
    else:
        terms = [f'"{t.strip()}"' for t in [reagent, catnum] if t.strip()]
        search_term = " ".join(terms)
        with st.spinner(f"Searching suppliers for: {search_term} ..."):
            results = []
            progress_bar = st.progress(0)
            total = len(df)

            for i, (_, row) in enumerate(df.iterrows()):
                product_url = vendor_direct_search(row["Company Name"], search_term)
                time.sleep(SLEEP_TIME)

                if product_url:
                    data = scrape_product_page(product_url)
                    if "Not found" in data["price"] or "error" in data["price"].lower():
                        if SELENIUM_AVAILABLE:
                            data["price"] = scrape_with_selenium(product_url, row["Company Name"])
                        else:
                            data["price"] += " (Selenium unavailable)"

                    results.append({
                        "Company": row["Company Name"],
                        "Link": product_url,
                        "Sales Email": row["Email Address"],
                        "Price": data["price"],
                    })

                progress_bar.progress((i + 1) / total)

        if results:
            st.subheader("Suppliers with Matching Products")
            st.dataframe(
                pd.DataFrame(results),
                column_config={
                    "Link": st.column_config.LinkColumn("Link", display_text="View Page"),
                    "Sales Email": st.column_config.TextColumn("Sales Email"),
                },
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No direct product pages found. Try a more specific catalog number, or contact suppliers via email for quotes.")

        st.info("Note: Many suppliers require login or quote requests for exact pricing. Use the provided emails/links for follow-up.")



