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
        # Expand as needed
    }

    df["Website"] = df["Company Name"].map(websites)
    df = df.dropna(subset=["Website"]).drop_duplicates("Company Name")
    df["Email Address"] = df["Email Address"].fillna("Not provided")
    return df

df = load_data()

# ---------------- HELPERS ---------------- #
def vendor_direct_search(company_name, search_term):
    """Prefer direct vendor search URL; fallback to Google"""
    term = quote(search_term.strip())
    company = company_name.lower()

    if "thermo fisher" in company or "fisher scientific" in company:
        return f"https://www.thermofisher.com/search/results?query={term}"

    elif "sigma-aldrich" in company or "sial" in company:
        return f"https://www.sigmaaldrich.com/US/en/search/{term}?focus=products&page=1&perpage=30&sort=relevance"

    elif "medchemexpress" in company or "mce" in company:
        return f"https://www.medchemexpress.com/search.html?kwd={term}"

    elif "abcam" in company:
        return f"https://www.abcam.com/search?keywords={term}"

    elif "qiagen" in company:
        return f"https://www.qiagen.com/us/search?query={term}"

    elif "stemcell" in company:
        return f"https://www.stemcell.com/search?query={term}"

    # For others → fallback to Google site: search
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
    """Better regex for various price formats"""
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
    if not url:
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
        return {"price": f"Error: {str(e)[:60]}", "email": "Error"}

# ---------------- UI ---------------- #
st.title("Reagent Quote Lookup")
st.markdown("Search by reagent name, catalog number, or both. Uses direct vendor searches where possible.")

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
                data = scrape_product_page(product_url)
                results.append({
                    "Company": row["Company Name"],
                    "Link": product_url or "Not found",
                    "Sales Email": row["Email Address"],
                    "Price": data["price"],
                })

            # Optional broad fallback only if almost nothing found
            broad_results = []
            if sum(1 for r in results if "Not found" not in r["Link"] and "Error" not in r["Price"]) < 2:
                broad_query = f'{search_term} buy price'
                url = f"https://www.google.com/search?q={quote(broad_query)}"
                try:
                    r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                    soup = BeautifulSoup(r.text, "html.parser")
                    for div in soup.find_all("div", class_="g"):
                        a = div.find("a")
                        if a and "href" in a.attrs and "/url?q=" in a["href"]:
                            clean = a["href"].split("/url?q=")[1].split("&")[0]
                            if "google" not in clean.lower():
                                data = scrape_product_page(clean)
                                broad_results.append({
                                    "Company": clean.split("//")[1].split("/")[0],
                                    "Link": clean,
                                    "Sales Email": data["email"],
                                    "Price": data["price"],
                                })
                                break
                except:
                    pass

        if results:
            st.subheader("Results from Known Suppliers")
            st.caption("Note: Prices often require login/cart/JS. 'Not found' is common — check link or email supplier.")
            st.dataframe(
                pd.DataFrame(results),
                column_config={
                    "Link": st.column_config.LinkColumn("Link", display_text="View Page"),
                },
                use_container_width=True,
                hide_index=True,
            )

        if broad_results:
            st.subheader("Additional / Broad Search Results")
            st.dataframe(
                pd.DataFrame(broad_results),
                column_config={
                    "Link": st.column_config.LinkColumn("Link", display_text="View Page"),
                },
                use_container_width=True,
                hide_index=True,
            )

        if not any("Not found" not in r["Price"] for r in results):
            st.info("Most prices not visible (dynamic loading or login required). Try specific catalog numbers or contact suppliers directly via email.")
