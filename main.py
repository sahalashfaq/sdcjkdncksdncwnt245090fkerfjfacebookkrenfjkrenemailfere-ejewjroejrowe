import streamlit as st
import pandas as pd
import re
import asyncio
import time
import os
import zipfile
import urllib.request
from tempfile import TemporaryDirectory
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor

# ------------- Custom CSS Loader ----------------
def local_css(file_name):
    if os.path.exists(file_name):
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css("style.css")

# ----------- Streamlit UI Setup ----------------
st.set_page_config(layout="centered")
uploaded_file = st.file_uploader("Upload CSV or XLSX file containing Facebook URLs", type=["csv", "xlsx"])

if not uploaded_file:
    st.info("Please upload a CSV or Excel file to begin.")
    st.stop()

try:
    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
    url_column = st.selectbox("Select the column containing Facebook URLs", df.columns)
    urls = df[url_column].dropna().unique().tolist()
except Exception as e:
    st.error(f"Error reading file: {e}")
    st.stop()

if not st.button("Start Scraping"):
    st.stop()

# ------------- Spinner (Countdown) ---------------
first_spinner = st.empty()
for i in range(5, 0, -1):
    first_spinner.markdown(
        f"<div style='display:flex;align-items:center;gap:10px;margin:10px 0;'>"
        f"<div class='loader'></div>"
        f"<p style='margin:0;'>Starting in {i} seconds…</p></div>"
        "<style>.loader{border:6px solid white;border-top:6px solid #3498db;border-radius:50%;"
        "width:30px;height:30px;animation:spin 1s linear infinite;}@keyframes spin{0%{transform:rotate(0deg);}100%{transform:rotate(360deg);}}</style>",
        unsafe_allow_html=True
    )
    time.sleep(1)
first_spinner.empty()

# ----------------- Temp Directory Context -------------
with TemporaryDirectory() as temp_dir:
    # Detect available browser and driver
    CHROME_PATH = (shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome"))
    CHROMEDRIVER_PATH = shutil.which("chromedriver")

    # Fallback to download Chromedriver if not found
    if not CHROMEDRIVER_PATH:
        st.warning("ChromeDriver not found. Downloading Chromedriver…")
        # Example version — adjust as needed
        driver_version = "121.0.6167.85"
        url = f"https://storage.googleapis.com/chrome-for-testing-public/{driver_version}/linux64/chromedriver-linux64.zip"
        zipfile_path = os.path.join(temp_dir, "chromedriver.zip")
        urllib.request.urlretrieve(url, zipfile_path)
        with zipfile.ZipFile(zipfile_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        extracted = os.path.join(temp_dir, "chromedriver-linux64", "chromedriver")
        os.chmod(extracted, 0o755)
        CHROMEDRIVER_PATH = extracted

    if not CHROME_PATH:
        st.error("No suitable browser found (chromium or google-chrome). Cannot proceed.")
        st.stop()

    # ------------- Scraper Functions -----------------
    def scrape_emails(driver, url):
        try:
            driver.get(url.rstrip("/") + "/about")
            html = driver.page_source
            emails = list(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html)))
            return [{"URL": url, "Email": e} for e in emails] or [{"URL": url, "Email": "No email found"}]
        except Exception:
            return [{"URL": url, "Email": "Error"}]

    async def run_scraper(url_list, spinner_placeholder):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.binary_location = CHROME_PATH

        service = Service(executable_path=CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)

        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=3)
        results = []
        start_time = time.time()

        for idx, u in enumerate(url_list):
            batch = await loop.run_in_executor(executor, scrape_emails, driver, u)
            results.extend(batch)
            elapsed = time.time() - start_time
            remaining = (len(url_list) - idx - 1)
            if idx >= 0:
                est = round((elapsed / (idx + 1)) * remaining / 60, 1)
            spinner_placeholder.empty()
            yield {
                "progress": (idx + 1) / len(url_list),
                "scraped": idx + 1,
                "emails_found": len([x for x in results if "@" in x["Email"]]),
                "eta": f"{est} min",
                "data": results.copy()
            }

        driver.quit()

    # -------------- UI for Progress -----------------
    second_spinner = st.empty()
    second_spinner.markdown(
        "<div style='display:flex;align-items:center;gap:10px;margin:10px 0;'>"
        "<div class='loader'></div><p style='margin:0;'>Processing…</p></div>"
        "<style>.loader{border:6px solid white;border-top:6px solid #3498db;border-radius:50%;"
        "width:30px;height:30px;animation:spin 1s linear infinite;}@keyframes spin{0%{transform:rotate(0deg);}100%{transform:rotate(360deg);}}</style>",
        unsafe_allow_html=True
    )
    progress = st.progress(0)
    status = st.empty()
    table = st.empty()

    # Run scraper
    async def orchestrator():
        start = time.time()
        all_data = []
        async for update in run_scraper(urls, second_spinner):
            progress.progress(update["progress"])
            status.markdown(f"Scraped {update['scraped']} / {len(urls)} — Emails found: {update['emails_found']} — ETA: {update['eta']}")
            table.dataframe(pd.DataFrame(update["data"]))
            all_data = update["data"]

        second_spinner.empty()
        total_time = round(time.time() - start, 2)
        st.success(f"Done in {total_time} seconds!")
        df_emails = pd.DataFrame(all_data).drop_duplicates()
        final = df.merge(df_emails, left_on=url_column, right_on="URL", how="left").drop(columns=["URL"])
        st.download_button("Download Results", final.to_csv(index=False).encode("utf-8"), "scraped_emails.csv", "text/csv")

    asyncio.run(orchestrator())
