from flask import Flask, request, render_template, url_for
import pandas as pd
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup
import re
import time

app = Flask(__name__)

# Load the company data
df = pd.read_excel('Company name, email address and phone number.xlsx', sheet_name='Sheet1')

# Define websites dict
websites = {
    'Thermo Fisher Life Technologies': 'https://www.thermofisher.com',
    'Fisher Scientific': 'https://www.fishersci.com',
    'MCE (MedChemExpress LLC)': 'https://www.medchemexpress.com',
    'Sigma-Aldrich Inc': 'https://www.sigmaaldrich.com',
    'Abcam Inc': 'https://www.abcam.com',
    'Addgene Inc': 'https://www.addgene.org',
    'Airgas USA, LLC': 'https://www.airgas.com',
    'Alkali Scientific LLC': 'https://alkalisci.com',
    'Baker Company': 'https://bakerco.com',
    'BioLegend Inc': 'https://www.biolegend.com',
    'Bio-Rad Laboratories Inc': 'https://www.bio-rad.com',
    'Bio-Techne Sales Corporation': 'https://www.bio-techne.com',
    'Cayman Chemical Company Inc': 'https://www.caymanchem.com',
    'Cell Signaling Technology': 'https://www.cellsignal.com',
    'Cerillo, Inc.': 'https://cerillo.bio',
    'Cole-Parmer': 'https://www.coleparmer.com',
    'Coriell Institute for Medical Research': 'https://www.coriell.org',
    'Corning Incorporated': 'https://www.corning.com',
    'Creative Biogene': 'https://www.creative-biogene.com',
    'Creative Biolabs Inc': 'https://www.creative-biolabs.com',
    'Eurofins Genomics LLC': 'https://eurofinsgenomics.com',
    'Genesee Scientific LLC': 'https://www.geneseesci.com',
    'Global Life Sciences Solutions USA LLC': 'https://www.cytivalifesciences.com',
    'Integrated DNA Technologies Inc': 'https://www.idtdna.com',
    'InvivoGen': 'https://www.invivogen.com',
    'LI-COR Biotech LLC': 'https://www.licorbio.com',
    'Omega Bio-tek Inc': 'https://omegabiotek.com',
    'PEPperPRINT GmbH': 'https://www.pepperprint.com',
    'Pipette.com': 'https://pipette.com',
    'QIAGEN LLC': 'https://www.qiagen.com',
    'RWD Life Science Inc': 'https://www.rwdstco.com',
    'Santa Cruz Biotechnology': 'https://www.scbt.com',
    'STEMCELL Technologies Inc': 'https://www.stemcell.com',
    'Zymo Research Corp': 'https://www.zymoresearch.com',
    'IBL-America': 'https://www.ibl-america.com',
    'Thomas Scientific INC': 'https://www.thomassci.com',
    'VWR Internatonal LLC': 'https://www.vwr.com',
    'INVENT BIOTECHNOLOGIES INC': 'https://inventbiotech.com',
    'NEW ENGLAND BIOLABS INC': 'https://www.neb.com',
    'BIOSEARCH TECHNOLOGIES INC': 'https://www.biosearchtech.com'
}

# Map websites
df['Website'] = df['Company Name'].map(websites)
df = df.dropna(subset=['Website'])
df = df.drop_duplicates(subset=['Company Name'])
df['Email Address'] = df['Email Address'].fillna('Not provided')

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        reagent = request.form['reagent']
        catnum = request.form['catnum']
        results = []
        for _, row in df.iterrows():
            query = f'"{reagent} {catnum}" site:{row["Website"]}'
            google_url = f"https://www.google.com/search?q={quote(query)}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            try:
                response = requests.get(google_url, headers=headers)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                product_link = None
                for g in soup.find_all('div', class_='g'):
                    a = g.find('a')
                    if a:
                        href = a['href']
                        if href.startswith('/url?q='):
                            url = href[7:].split('&')[0]
                            if row['Website'] in url and 'accounts.google' not in url:
                                product_link = url
                                break
                if product_link:
                    time.sleep(1)  # Avoid rate limiting
                    prod_response = requests.get(product_link, headers=headers)
                    prod_response.raise_for_status()
                    prod_soup = BeautifulSoup(prod_response.text, 'html.parser')
                    # Find price elements
                    price_elements = prod_soup.find_all(attrs={'class': re.compile(r'(?i)price')})
                    prices = [el.get_text().strip() for el in price_elements if '$' in el.get_text()]
                    if not prices:
                        text = prod_soup.get_text()
                        prices = re.findall(r'\$\s*\d+(?:,\d+)?(?:\.\d+)?', text)
                    price = prices[0] if prices else 'Not found'
                else:
                    product_link = 'Not found'
                    price = 'Not found'
                results.append({
                    'company': row['Company Name'],
                    'link': product_link,
                    'email': row['Email Address'],
                    'price': price
                })
            except Exception as e:
                results.append({
                    'company': row['Company Name'],
                    'link': 'Error',
                    'email': row['Email Address'],
                    'price': str(e)
                })
        # Check if any valid results
        valid_results = [r for r in results if r['link'] != 'Not found' and r['link'] != 'Error']
        broad_results = []
        if not valid_results:
            # Broaden search
            query = f'"{reagent} {catnum}" price buy'
            google_url = f"https://www.google.com/search?q={quote(query)}"
            try:
                response = requests.get(google_url, headers=headers)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                found_links = []
                for g in soup.find_all('div', class_='g'):
                    a = g.find('a')
                    if a:
                        href = a['href']
                        if href.startswith('/url?q='):
                            url = href[7:].split('&')[0]
                            if 'google' not in url.lower() and 'youtube' not in url.lower():
                                found_links.append(url)
                                if len(found_links) >= 5:
                                    break
                for url in found_links:
                    time.sleep(1)
                    prod_response = requests.get(url, headers=headers)
                    prod_response.raise_for_status()
                    prod_soup = BeautifulSoup(prod_response.text, 'html.parser')
                    price_elements = prod_soup.find_all(attrs={'class': re.compile(r'(?i)price')})
                    prices = [el.get_text().strip() for el in price_elements if '$' in el.get_text()]
                    if not prices:
                        text = prod_soup.get_text()
                        prices = re.findall(r'\$\s*\d+(?:,\d+)?(?:\.\d+)?', text)
                    price = prices[0] if prices else 'Not found'
                    # Find email
                    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.[\w]+', prod_soup.get_text())
                    email = emails[0] if emails else 'Not found'
                    broad_results.append({
                        'company': url.split('//')[1].split('/')[0],  # Domain as company
                        'link': url,
                        'email': email,
                        'price': price
                    })
            except Exception:
                pass
        return render_template('results.html', results=results, broad_results=broad_results)
    return render_template('form.html')

if __name__ == '__main__':
    app.run(debug=True)