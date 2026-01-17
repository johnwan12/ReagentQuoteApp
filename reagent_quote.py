import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
import time
import os

# ---------------- CONFIG ---------------- #
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 10
SLEEP_TIME = 1.2

# ---------------- LOAD DATA ---------------- #
EXCEL_FILE = "Companies.xlsx"  # ← Updated filename

@st.cache_data(show_spinner="Loading company database...")
def load_data():
    if not os.path.exists(EXCEL_FILE):
        st.error(f"Excel file not found: {EXCEL_FILE}\nCurrent directory: {os.getcwd()}\nFiles: {os.listdir('.')}")
        st.stop()

    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name="Sheet1")
        st.success(f"Loaded {len(df)} companies from {EXCEL_FILE}", icon="✅")
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
        # Add more company → website mappings here as needed
    }

    df["Website"] = df["Company Name"].map(websites)
    df = df.dropna(subset=["Website"]).drop_duplicates("Company Name")
    df["Email Address"] = df["Email Address"].fillna("Not provided")
    return df

df = load_data()

# ---------------- HELPERS ---------------- #
def google_search(query):
    """Return first plausible product URL from Google results"""
    url = f"https://www.google.com/search?q={quote(query)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for div in soup.find_all("div", class_="g"):
            a = div.find("a")
            if a and "href" in a.attrs:
                href = a["href"]
                if href.startswith("/url?q="):
                    clean = href.split("/url?q=")[1].split("&")[0]
                    if "google" not in clean.lower() and "youtube" not in clean.lower():
                        # Prefer product/catalog/shop links when possible
                        if any(kw in clean.lower() for kw in ["/product/", "/catalog/", "/shop/", "/order/"]):
                            return clean
                        # Otherwise return first non-Google link
                        return clean
        return None
    except Exception:
        return None

def extract_price(text):
    """Improved price extraction"""
    prices = re.findall(r'(?:USD|\$|€|Price:?\s*|\$?\s*)[\d,]+(?:\.\d{1,2})?', text, re.IGNORECASE)
    if prices:
        cleaned = [p.strip('$€ USD: \t') for p in prices if any(c.isdigit() for c in p)]
        return cleaned[0] if cleaned else "Not found"
    return "Not found"

def extract_email(text):
    emails = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    return emails[0] if emails else "Not found"

def scrape_product_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        return {
            "price": extract_price(text),
            "email": extract_email(text),
        }
    except Exception:
        return {"price": "Error", "email": "Error"}

# ---------------- UI ---------------- #
st.title("Reagent Quote Lookup")
st.markdown("Search by **reagent name**, **catalog number**, or **both**.")

col1, col2 = st.columns(2)
with col1:
    reagent = st.text_input("Reagent Name", placeholder="e.g. 8-Bromoadenosine, DMEM, ...", key="reagent")
with col2:
    catnum = st.text_input("Catalog Number", placeholder="e.g. 11965-092, B6272, ...", key="catnum")

if st.button("Search", type="primary"):
    if not reagent.strip() and not catnum.strip():
        st.warning("Please enter at least a reagent name or a catalog number.")
    else:
        # Build search term flexibly
        terms = []
        if reagent.strip():
            terms.append(f'"{reagent.strip()}"')
        if catnum.strip():
            terms.append(f'"{catnum.strip()}"')
        search_term = " ".join(terms)

        with st.spinner(f"Searching suppliers for: {search_term} ..."):
            results = []
            for _, row in df.iterrows():
                query = f'{search_term} site:{row["Website"]}'
                product_url = google_search(query)
                time.sleep(SLEEP_TIME)
                if product_url:
                    data = scrape_product_page(product_url)
                    results.append({
                        "Company": row["Company Name"],
                        "Link": product_url,
                        "Sales Email": row["Email Address"],
                        "Price": data["price"],
                    })
                else:
                    results.append({
                        "Company": row["Company Name"],
                        "Link": "Not found",
                        "Sales Email": row["Email Address"],
                        "Price": "Not found",
                    })

            # Broad fallback if no direct hits
            broad_results = []
            if not any(r["Link"] != "Not found" for r in results):
                broad_query = f'{search_term} buy price'
                url = google_search(broad_query)
                if url:
                    data = scrape_product_page(url)
                    broad_results.append({
                        "Company": url.split("//")[1].split("/")[0],
                        "Link": url,
                        "Sales Email": data["email"],
                        "Price": data["price"],
                    })

        if results:
            st.subheader("Results from Known Suppliers")
            st.dataframe(
                pd.DataFrame(results),
                column_config={
                    "Link": st.column_config.LinkColumn("Link", display_text="View Product"),
                },
                use_container_width=True,
                hide_index=True,
            )

        if broad_results:
            st.subheader("Additional Results (Broad Search)")
            st.dataframe(
                pd.DataFrame(broad_results),
                column_config={
                    "Link": st.column_config.LinkColumn("Link", display_text="View Product"),
                },
                use_container_width=True,
                hide_index=True,
            )

        if not results and not broad_results:
            st.info("No matching products found. Try different spelling, format, or fewer terms.")
