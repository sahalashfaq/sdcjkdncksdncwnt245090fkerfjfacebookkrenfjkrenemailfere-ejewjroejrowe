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

# ------------- Helper to estimate download time -------------
def estimate_time(size_bytes, speed_mbps=5):
    """
    Estimate download time (seconds) given file size in bytes 
    and speed in megabits per second.
    """
    speed_bps = speed_mbps * 1_000_000 / 8  # convert Mbps to bytes/sec
    return size_bytes / speed_bps

# ------------- Custom CSS Loader ----------------
def local_css(file_name):
    if os.path.exists(file_name):
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css("style.css")

# ------------- UI Setup ----------------
st.set_page_config(layout="centered")
uploaded_file = st.file_uploader("Upload CSV or XLSX file containing Facebook URLs", type=["csv", "xlsx"])
if not uploaded_file:
    st.info("Upload a CSV/XLSX file to begin.")
    st.stop()

try:
    df = pd.read_csv(uploaded_file) if uploaded_file.name.lower().endswith(".csv") else pd.read_excel(uploaded_file)
    url_column = st.selectbox("Select the column containing Facebook URLs", df.columns)
    urls = df[url_column].dropna().unique().tolist()
except Exception as e:
    st.error(f"Error reading file: {e}")
    st.stop()

if not st.button("Start Scraping"):
    st.stop()

# ------------- Countdown before starting ----------------
first_spinner = st.empty()
for i in range(5, 0, -1):
    first_spinner.markdown(f"Starting in {i} seconds…")
    time.sleep(1)
first_spinner.empty()

# ------------- Main logic within temp directory ----------------
with TemporaryDirectory() as temp_dir:
    CHROME_PATH = (shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome"))
    CHROMEDRIVER_PATH = shutil.which("chromedriver")

    # If ChromeDriver missing — estimate download
    if not CHROMEDRIVER_PATH:
        st.warning("ChromeDriver not found — preparing to download...")
        # Prepare URL for download (use latest or specific version)
        version = "139.0.7258.68"  # Example stable version
        url = f"https://storage.googleapis.com/chrome-for-testing-public/{version}/linux64/chromedriver-linux64.zip"
        st.write(f"ChromeDriver size is approximately **7 MB**, typical for this version.")

        # Estimate download time assuming 5 Mbps (adjust as needed)
        est = estimate_time(7 * 1024 * 1024, speed_mbps=5)  # size in bytes
        st.info(f"Estimated download time at 5 Mbps: **{round(est, 1)} seconds**")

        # Proceed with download
        zip_path = os.path.join(temp_dir, "chromedriver.zip")
        urllib.request.urlretrieve(url, zip_path)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        extracted = os.path.join(temp_dir, "chromedriver-linux64", "chromedriver")
        os.chmod(extracted, 0o755)
        CHROMEDRIVER_PATH = extracted
        st.success("ChromeDriver downloaded and ready.")

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

    async def run_scraper(url_list, spinner):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.binary_location = CHROME_PATH
        service = Service(executable_path=CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)

        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=3)
        results, start_time = [], time.time()

        for idx, u in enumerate(url_list):
            batch = await loop.run_in_executor(executor, scrape_emails, driver, u)
            results.extend(batch)
            elapsed = time.time() - start_time
            remaining = len(url_list) - idx - 1
            est = round((elapsed / (idx + 1)) * remaining / 60, 1)
            spinner.empty()
            yield {
                "progress": (idx + 1) / len(url_list),
                "scraped": idx + 1,
                "emails_found": len([x for x in results if "@" in x["Email"]]),
                "eta": f"{est} min",
                "data": results.copy()
            }

        driver.quit()

    # ------------- Progress UI -----------------
    second_spinner = st.empty()
    second_spinner.markdown("Processing…")
    progress = st.progress(0)
    status = st.empty()
    table = st.empty()

    async def orchestrate():
        start = time.time()
        all_data = []
        async for update in run_scraper(urls, second_spinner):
            progress.progress(update["progress"])
            status.markdown(f"{update['scraped']}/{len(urls)} – Emails found: {update['emails_found']} – ETA: {update['eta']}")
            table.dataframe(pd.DataFrame(update["data"]))
            all_data = update["data"]

        second_spinner.empty()
        st.success(f"Done in {round(time.time() - start, 2)} seconds!")
        df_emails = pd.DataFrame(all_data).drop_duplicates()
        final = df.merge(df_emails, left_on=url_column, right_on="URL", how="left").drop(columns=["URL"])
        st.download_button("Download Results", final.to_csv(index=False).encode("utf-8"),
                           "scraped_emails.csv", "text/csv")

    asyncio.run(orchestrate())
