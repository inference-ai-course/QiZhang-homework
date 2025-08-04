import requests
import xml.etree.ElementTree as ET
import trafilatura
import pytesseract
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import json
import time
import io

# ------------ Config ------------
CATEGORY = "cs.CL"
MAX_RESULTS = 200
OUTPUT_FILE = "arxiv_clean.json"

# ------------ Setup Headless Browser with Suppressed Logs ------------
options = Options()
options.add_argument("--headless")               # run Chrome in headless mode
options.add_argument("--disable-gpu")            # disable GPU acceleration
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--log-level=3")            # suppress console logs
options.add_experimental_option('excludeSwitches', ['enable-logging'])  # hide devtools logs

service = Service()  # default ChromeDriver service
driver = webdriver.Chrome(service=service, options=options)

# ------------ Fetch papers from arXiv API ------------
def fetch_arxiv_papers(category, max_results):
    base_url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"cat:{category}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending"
    }
    response = requests.get(base_url, params=params)
    root = ET.fromstring(response.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    
    papers = []
    for entry in root.findall("atom:entry", ns):
        url = entry.find("atom:id", ns).text
        title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
        authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
        date = entry.find("atom:published", ns).text[:10]
        papers.append({"url": url, "title": title, "authors": authors, "date": date})
    return papers

# ------------ Extract abstract via Trafilatura ------------
def extract_abstract(url):
    try:
        html = requests.get(url).text
        extracted = trafilatura.extract(html)
        if extracted and "abstract" in extracted.lower():
            lines = [line for line in extracted.splitlines() if len(line) > 50]
            for line in lines:
                if "abstract" in line.lower() or len(line) > 150:
                    return line.strip()
    except Exception:
        return None
    return None

# ------------ OCR Fallback ------------
def ocr_abstract(url):
    try:
        driver.get(url)
        time.sleep(2)
        screenshot = driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(screenshot))
        text = pytesseract.image_to_string(img)
        for line in text.splitlines():
            if len(line) > 100:
                return line.strip()
    except Exception:
        return None
    return None

# ------------ Main ------------
papers = fetch_arxiv_papers(CATEGORY, MAX_RESULTS)
results = []

for paper in papers:
    abs_url = paper["url"].replace("/pdf/", "/abs/")
    abstract = extract_abstract(abs_url)
    if not abstract:
        abstract = ocr_abstract(abs_url)
    if abstract:
        paper["abstract"] = abstract
        results.append(paper)

driver.quit()

# ensure file size <= 1MB
json_data = json.dumps(results, indent=2)
while len(json_data.encode("utf-8")) > 1024 * 1024:
    for p in results:
        p["abstract"] = p["abstract"][:500] + "..."
    json_data = json.dumps(results, indent=2)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(json_data)

print(f"Saved {len(results)} papers to {OUTPUT_FILE}")
