import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
import time
import os

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    st.warning("Selenium not installed – falling back to basic scraping (prices may be missed)")

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
        "Sigma-Aldrich Inc": "https://www.sigmaaldrich.com",
        "Abcam Inc": "https://www.abcam.com",
        "Addgene Inc": "https://www.addgene.org",
        "Bio-Rad Laboratories Inc": "https://www.bio-rad.com",
        "QIAGEN LLC": "https://www.qiagen.com",
        "STEMCELL Technologies Inc": "https://www.stemcell.com",
        "Zymo Research Corp": "https://www.zymoresearch.com",
    }

    df["Website"] = df["Company Name"].map(websites)
    df = df.dropna(subset=["Website"]).drop_duplicates("Company Name")
    df["Email Address"] = df["Email Address"].fillna("Not provided")
    return df

df = load_data()

# ---------------- HELPERS ---------------- #
def vendor_direct_search(company_name, search_term):
    term = quote(search_term.strip())
    company = company_name.lower()

    if "thermo fisher" in company or "fisher scientific" in company:
        return f"https://www.thermofisher.com/search/results?query={term}"
    elif "sigma-aldrich" in company:
        return f"https://www.sigmaaldrich.com/US/en/search/{term}?focus=products&page=1&perpage=30&sort=relevance"
    elif "medchemexpress" in company or "mce" in company:
        return f"https://www.medchemexpress.com/search.html?kwd={term}"
    elif "abcam" in company:
        return f"https://www.abcam.com/search?keywords={term}"
    elif "qiagen" in company:
        return f"https://www.qiagen.com/us/search?query={term}"
    elif "stemcell" in company:
        return f"https://www.stemcell.com/search?query={term}"

    # Fallback: Google site-restricted search
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
        r'Price:\s*[\$\€]?[\s]*[\d,]+(?:\.\d{1,2})?',
        r'Request Quote|Call for price|Login for price|Quote required',
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return "Not found (may require login/JS)"

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

def scrape_with_selenium(url):
    if not SELENIUM_AVAILABLE:
        return "Selenium not available in this environment"

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

    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
        time.sleep(4.5)  # Allow JS to load prices

        # Try specific selectors first
        price_selectors = [
            '[data-testid="price"]',
            '.price', '.product-price', '[class*="price"]',
            'span.price', 'div.price-amount', '[itemprop="price"]',
            '.buybox-price', '.price-large', '.price-current',
        ]

        for sel in price_selectors:
            try:
                elem = driver.find_element(By.CSS_SELECTOR, sel)
                price_text = elem.text.strip()
                if price_text and any(c.isdigit() for c in price_text):
                    driver.quit()
                    return price_text
            except:
                continue

        # Fallback: full body text
        text = driver.find_element(By.TAG_NAME, "body").text
        driver.quit()
        return extract_price(text)
    except Exception as e:
        try:
            driver.quit()
        except:
            pass
        return f"Selenium failed: {str(e)[:80]}"

# ---------------- UI ---------------- #
st.title("Reagent Quote Lookup")
st.markdown("Search by reagent name, catalog number, or both.\n\n**Note**: Uses Selenium fallback on Render/Railway for better price detection.")

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
            for _, row in df.iterrows():
                product_url = vendor_direct_search(row["Company Name"], search_term)
                time.sleep(SLEEP_TIME)

                # First try fast requests method
                data = scrape_product_page(product_url)

                # If price looks missing → try Selenium
                if "Not found" in data["price"] or "Error" in data["price"] or "Request error" in data["price"]:
                    if SELENIUM_AVAILABLE:
                        data["price"] = scrape_with_selenium(product_url)
                    else:
                        data["price"] += " (Selenium unavailable)"

                results.append({
                    "Company": row["Company Name"],
                    "Link": product_url or "Not found",
                    "Sales Email": row["Email Address"],
                    "Price": data["price"],
                })

        if results:
            st.subheader("Results from Known Suppliers")
            st.caption("Prices may require login/cart. Selenium fallback used when available.")
            st.dataframe(
                pd.DataFrame(results),
                column_config={
                    "Link": st.column_config.LinkColumn("Link", display_text="View Page"),
                },
                use_container_width=True,
                hide_index=True,
            )

        if not any("Not found" not in r["Price"] and "failed" not in r["Price"].lower() for r in results):
            st.info("Many prices still hidden (login required or complex JS). Contact suppliers via email for accurate quotes.")
