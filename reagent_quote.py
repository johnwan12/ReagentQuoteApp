from flask import Flask, request, render_template
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
import time

app = Flask(__name__)

# ---------------- CONFIG ---------------- #
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 10
SLEEP_TIME = 1

# ---------------- LOAD DATA ---------------- #
df = pd.read_excel(
    "Company_name_email_address_and_phone_number.xlsx",
    sheet_name="Sheet1"
)

websites = {
    "Thermo Fisher Life Technologies": "https://www.thermofisher.com",
    "Fisher Scientific": "https://www.fishersci.com",
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

# ---------------- HELPERS ---------------- #
def google_search(query):
    """Return first valid non-Google URL from search results"""
    url = f"https://www.google.com/search?q={quote(query)}"
    r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    soup = BeautifulSoup(r.text, "html.parser")

    for link in soup.select("a"):
        href = link.get("href", "")
        if href.startswith("/url?q="):
            clean_url = href.split("/url?q=")[1].split("&")[0]
            if "google" not in clean_url.lower():
                return clean_url
    return None


def extract_price(html_text):
    """Extract first USD price found"""
    prices = re.findall(r"\$\s*\d+(?:,\d{3})*(?:\.\d+)?", html_text)
    return prices[0] if prices else "Not found"


def extract_email(html_text):
    emails = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", html_text)
    return emails[0] if emails else "Not found"


def scrape_product_page(url):
    r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    return {
        "price": extract_price(text),
        "email": extract_email(text),
    }


# ---------------- ROUTES ---------------- #
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        reagent = request.form["reagent"]
        catnum = request.form["catnum"]

        results = []

        for _, row in df.iterrows():
            query = f'"{reagent} {catnum}" site:{row["Website"]}'
            try:
                product_url = google_search(query)
                time.sleep(SLEEP_TIME)

                if not product_url:
                    raise ValueError("No product link found")

                data = scrape_product_page(product_url)

                results.append({
                    "company": row["Company Name"],
                    "link": product_url,
                    "email": row["Email Address"],
                    "price": data["price"],
                })

            except Exception as e:
                results.append({
                    "company": row["Company Name"],
                    "link": "Not found",
                    "email": row["Email Address"],
                    "price": "Not found",
                })

        # Broad fallback search
        broad_results = []
        if not any(r["link"] != "Not found" for r in results):
            broad_query = f'"{reagent} {catnum}" buy price'
            try:
                url = google_search(broad_query)
                if url:
                    data = scrape_product_page(url)
                    broad_results.append({
                        "company": url.split("//")[1].split("/")[0],
                        "link": url,
                        "email": data["email"],
                        "price": data["price"],
                    })
            except Exception:
                pass

        return render_template(
            "results.html",
            results=results,
            broad_results=broad_results,
        )

    return render_template("form.html")


if __name__ == "__main__":
    app.run(debug=True)


