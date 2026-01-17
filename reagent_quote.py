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
        "VWR International LLC": "https://www.avantorsciences.com/us/en",
        "Alkali Scientific LLC": "https://alkalisci.com/",
        "Baker Company": "https://bakerco.com/",
        "BioLegend Inc": "https://www.biolegend.com/de-de/bio-bits/welcome-back-to-the-lab",
        "Cayman Chemical Company Inc": "https://www.caymanchem.com/",
        "Cell Signaling Technology": "https://www.cellsignal.com/",
        "Cerillo, Inc.": "https://cerillo.bio/",
        "Cole-Parmer": "https://www.coleparmer.com/",
        "Corning Incorporated": "https://www.coriell.org/",
        "Creative Biogene": "https://microbiosci.creative-biogene.com/",
        "Creative Biolabs Inc": "https://www.creative-biolabs.com/",
        "Eurofins Genomics LLC": "https://www.eurofinsdiscovery.com/",
        "Genesee Scientific LLC": "hhttps://www.geneseesci.com/",
        "Integrated DNA Technologies Inc": "https://www.idtdna.com/page",
        "InvivoGen": "https://www.invivogen.com/",
        "LI-COR Biotech LLC": "https://www.licorbio.com/",
        "Omega Bio-tek Inc": "https://omegabiotek.com/",
        "PEPperPRINT GmbH": "https://www.pepperprint.com/",
        "Pipette.com": "https://pipette.com/",
        "Santa Cruz Biotechnology": "https://www.scbt.com/home",
        "RWD Life Science Inc": "https://www.rwdstco.com/company-profile/",
        "IBL-America": "https://www.ibl-america.com/",
        "invivogen": "https://www.invivogen.com/",
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
def vendor_direct_search(company_name, search_term):
    term = quote(search_term.strip())
    company_lower = company_name.lower()

    # Thermo Fisher variants
    if any(kw in company_lower for kw in ["thermo fisher", "fisher scientific", "thermo scientific", "life technologies"]):
        return f"https://www.thermofisher.com/search/results?query={encoded_term}"
    
    # Sigma-Aldrich / MilliporeSigma
    elif any(kw in company_lower for kw in ["sigma-aldrich", "sigma aldrich", "milliporesigma", "merck"]):
        return (
            f"https://www.sigmaaldrich.com/US/en/search/{encoded_term}?"
            f"focus=products&page=1&perpage=30&sort=relevance&term={encoded_term}&type=product"
        )
    
    # MedChemExpress (MCE)
    elif any(kw in company_lower for kw in ["medchemexpress", "mce", "medchem express"]):
        return f"https://www.medchemexpress.com/search.html?kwd={encoded_term}"
    
    # Abcam
    elif "abcam" in company_lower:
        return f"https://www.abcam.com/search?keywords={encoded_term}"
    
    # QIAGEN
    elif "qiagen" in company_lower:
        return f"https://www.qiagen.com/us/search?query={encoded_term}"
    
    # STEMCELL Technologies
    elif any(kw in company_lower for kw in ["stemcell", "stem cell", "stemcell technologies"]):
        return f"https://www.stemcell.com/search?query={encoded_term}"
    
    # Avantor / VWR
    elif any(kw in company_lower for kw in ["vwr", "avantor"]):
        return f"https://www.avantorsciences.com/us/en/search?text={encoded_term}"
    
    # Addgene (plasmids primary)
    elif "addgene" in company_lower:
        return f"https://www.addgene.org/search/catalog/plasmids/?q={encoded_term}"
    
    # Cayman Chemical
    elif any(kw in company_lower for kw in ["cayman chemical", "caymanchem"]):
        return f"https://www.caymanchem.com/search?q={encoded_term}"
    
    # Cell Signaling Technology
    elif any(kw in company_lower for kw in ["cell signaling", "cellsignal"]):
        return f"https://www.cellsignal.com/search?keywords={encoded_term}"
    
    # Santa Cruz Biotechnology
    elif any(kw in company_lower for kw in ["santa cruz", "scbt"]):
        return f"https://www.scbt.com/search?query={encoded_term}"
    
    # New England Biolabs (NEB)
    elif any(kw in company_lower for kw in ["new england biolabs", "neb"]):
        return f"https://www.neb.com/en-us/search?keyword={encoded_term}"
    
    # Bio-Rad
    elif any(kw in company_lower for kw in ["bio-rad", "biorad"]):
        return f"https://www.bio-rad.com/en-us/s?search={encoded_term}"
    
    # BioLegend
    elif "biolegend" in company_lower:
        return f"https://www.biolegend.com/en-us/search?keywords={encoded_term}"
    
    # Zymo Research
    elif "zymo" in company_lower or "zymoresearch" in company_lower:
        return f"https://www.zymoresearch.com/search?q={encoded_term}"
    
    # Integrated DNA Technologies (IDT)
    elif any(kw in company_lower for kw in ["integrated dna", "idtdna", "idt"]):
        return f"https://www.idtdna.com/search?query={encoded_term}"
    
    # InvivoGen (note: duplicated in list)
    elif "invivogen" in company_lower:
        return f"https://www.invivogen.com/search?keywords={encoded_term}"
    
    # Eurofins Genomics
    elif "eurofins" in company_lower:
        return f"https://www.eurofinsgenomics.eu/search/?q={encoded_term}"  # EU site common; adjust if US needed
    
    # For others with standard /search?q= pattern (common fallback)
    elif any(kw in company_lower for kw in [
        "alkali scientific", "baker company", "cole-parmer", "corning", "creative biogene",
        "creative biolabs", "genesee scientific", "li-cor", "omega bio-tek", "pepperprint",
        "pipette.com", "rwd life science", "ibl-america", "thomas scientific", "invent biotechnologies"
    ]):

    # Google site-restricted fallback
    site = df.loc[df["Company Name"] == company_name, "Website"].values[0]
    query = f'"{search_term}" site:{site}'
    url = f"https://www.google.com/search?q={quote(query)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        for div in soup.find_all("div", class_="g"):
            a = div.find("a")
            if a and "href" in a.attrs:
                href = a["href"]
                if href.startswith("/url?q="):
                    clean = href.split("/url?q=")[1].split("&")[0]
                    if "google" not in clean.lower() and "youtube" not in clean.lower():
                        return clean
    except:
        pass
    return None

def extract_price(text):
    patterns = [
        r'\$[\s]*[\d,]+(?:\.\d{1,2})?',
        r'USD[\s]*[\d,]+(?:\.\d{1,2})?',
        r'€[\s]*[\d,]+(?:\.\d{1,2})?',
        r'[\d,]+(?:\.\d{1,2})?[\s]*(?:USD|EUR|\$|€)',
        r'(?:Price|List Price|Your Price):\s*[\$\€]?[\s]*[\d,]+(?:\.\d{1,2})?',
        r'Request Quote|Call for price|Login for price|Quote required|Contact us for pricing',
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return "Not found (may require interaction/JS)"

def extract_email(text):
    emails = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    return emails[0] if emails else "Not found"

def scrape_product_page(url):
    if not url or "Not found" in url:
        return {"price": "No link", "email": "N/A"}
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        return {
            "price": extract_price(text),
            "email": extract_email(text),
        }
    except Exception as e:
        return {"price": f"Request error: {str(e)[:60]}", "email": "Error"}

def scrape_with_selenium(url, company_name):
    if not SELENIUM_AVAILABLE:
        return "Selenium not available"

    if not url or "Not found" in url:
        return "No valid URL"

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = os.getenv("CHROME_BIN", "/usr/bin/chromium")

    service = Service(os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver"))

    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
        time.sleep(3)

        company_lower = company_name.lower()

        # Sigma-Aldrich specific handling
        if "sigma-aldrich" in company_lower:
            try:
                expand_button = WebDriverWait(driver, SELENIUM_WAIT_SEC).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".expandArrow, [aria-label*='expand'], .pricing-toggle"))
                )
                expand_button.click()
                time.sleep(2.5)

                price_table = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, "productSizePriceQtyTable"))
                )
                rows = price_table.find_elements(By.TAG_NAME, "tr")
                prices = []
                for row in rows[1:]:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 2:
                        size_info = cells[0].text.strip()
                        price_text = cells[1].text.strip()
                        if price_text and any(c.isdigit() for c in price_text):
                            prices.append(f"{size_info}: {price_text}")
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
            try:
                driver.quit()
            except:
                pass
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
            no_results_companies = []  # Optional: track companies with no hit

            for _, row in df.iterrows():
                product_url = vendor_direct_search(row["Company Name"], search_term)
                time.sleep(SLEEP_TIME)

                data = scrape_product_page(product_url)

                if "Not found" in data["price"] or "Error" in data["price"] or "Request error" in data["price"]:
                    if SELENIUM_AVAILABLE:
                        data["price"] = scrape_with_selenium(product_url, row["Company Name"])
                    else:
                        data["price"] += " (Selenium unavailable)"

                # Only include if we found a product page
                if product_url and "Not found" not in product_url:
                    results.append({
                        "Company": row["Company Name"],
                        "Link": product_url,
                        "Sales Email": row["Email Address"],
                        "Price": data["price"],
                    })
                else:
                    no_results_companies.append(row["Company Name"])

        if results:
            st.subheader("Suppliers with Matching Products")
            st.dataframe(
                pd.DataFrame(results),
                column_config={
                    "Link": st.column_config.LinkColumn("Link", display_text="View Page"),
                },
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No product pages found across suppliers. Try a more specific catalog number or different spelling.")

        # Optional: show summary of checked suppliers
        if no_results_companies:
            with st.expander("Checked but no product found"):
                st.write(", ".join(no_results_companies))

        if not results:
            st.info("Many reagents require login or quote request. Contact suppliers directly via email for accurate pricing.")


