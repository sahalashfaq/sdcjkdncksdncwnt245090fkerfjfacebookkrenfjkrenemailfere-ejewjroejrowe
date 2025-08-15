import streamlit as st
import pandas as pd
import re
import asyncio
import time
import os
import zipfile
import urllib.request
import tempfile
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor

# ----------------- Custom CSS Loader --------------------
def local_css(file_name):
    if os.path.exists(file_name):
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css("style.css")

# ----------------- Temporary Directory --------------------
temp_dir = tempfile.mkdtemp()

# ----------------- Try to find Chrome & Driver --------------------
CHROME_PATH = (
    shutil.which("google-chrome") or
    shutil.which("google-chrome-stable") or
    shutil.which("chromium-browser") or
    shutil.which("chromium")
)

CHROMEDRIVER_PATH = shutil.which("chromedriver")

# ----------------- ChromeDriver Installer (Fallback) --------------------
def download_chromedriver():
    # Default to latest Chrome for Testing (121.0.6167.85 as example — adjust if needed)
    driver_url = "https://storage.googleapis.com/chrome-for-testing-public/121.0.6167.85/linux64/chromedriver-linux64.zip"
    zip_path = os.path.join(temp_dir, "chromedriver.zip")
    urllib.request.urlretrieve(driver_url, zip_path)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)

    extracted_driver = os.path.join(temp_dir, "chromedriver-linux64", "chromedriver")
    os.chmod(extracted_driver, 0o755)
    return extracted_driver

# If ChromeDriver not found, try to download
if not CHROMEDRIVER_PATH:
    st.warning("ChromeDriver not found — downloading it...")
    CHROMEDRIVER_PATH = download_chromedriver()

# Stop if Chrome is not found
if not CHROME_PATH:
    st.error("Google Chrome or Chromium browser not found in this environment.")
    st.stop()

# ----------------- Scraper Logic --------------------
def scrape_emails_from_url(driver, url):
    about_url = url.rstrip("/") + "/about"
    try:
        driver.get(about_url)
        html = driver.page_source
        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html)
        emails = list(set(emails))
        return [{"URL": url, "Email": email} for email in emails] if emails else [{"URL": url, "Email": "No email found"}]
    except Exception:
        return [{"URL": url, "Email": "Error fetching"}]

async def run_scraper_async(urls, spinner_placeholder):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.binary_location = CHROME_PATH

    service = Service(executable_path=CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=3)

    start_time = time.time()
    results = []
    total = len(urls)

    for i, url in enumerate(urls):
        row_result = await loop.run_in_executor(executor, scrape_emails_from_url, driver, url)
        results.extend(row_result)

        elapsed = time.time() - start_time
        remaining = total - (i + 1)
        est_seconds = (elapsed / (i + 1)) * remaining
        est_minutes = round(est_seconds / 60, 1)

        if i == 0:
            spinner_placeholder.empty()

        yield {
            "progress": (i + 1) / total,
            "scraped": i + 1,
            "emails_found": len([e for e in results if "@" in e["Email"]]),
            "estimated_time": f"{est_minutes} min",
            "current_data": list(results),
        }

    driver.quit()

# ----------------- Streamlit UI --------------------
st.set_page_config(layout="centered")
uploaded_file = st.file_uploader("Upload CSV or XLSX file containing Facebook URLs", type=["csv", "xlsx"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        url_column = st.selectbox("Select the column containing Facebook URLs", df.columns)
        urls = df[url_column].dropna().unique().tolist()
    except Exception as e:
        st.error(f"Failed to process file: {e}")
        st.stop()

    if st.button("Start Scraping"):

        # ----------------- First Spinner --------------------
        first_spinner_placeholder = st.empty()
        countdown = 5
        for i in range(countdown, 0, -1):
            first_spinner_placeholder.markdown(
                """
                <div style="display:flex;align-items:center;gap:10px;margin:10px 0;">
                    <div class="loader"></div>
                    <p style="margin:0;">Starting process… (approx. 1 or half min)</p>
                </div>
                <style>
                .loader {
                    border: 6px solid white;
                    border-top: 6px solid #3498db;
                    border-radius: 50%;
                    width: 30px;
                    height: 30px;
                    animation: spin 1s linear infinite;
                }
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
                </style>
                """, unsafe_allow_html=True
            )
            time.sleep(1)

        # ----------------- Second Spinner + Progress Bar --------------------
        second_spinner_placeholder = st.empty()
        second_spinner_placeholder.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;margin:10px 0;">
                <div class="loader"></div>
                <p style="margin:0;">Processing…</p>
            </div>
            <style>
            .loader {
                border: 6px solid white;
                border-top: 6px solid #3498db;
                border-radius: 50%;
                width: 30px;
                height: 30px;
                animation: spin 1s linear infinite;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            </style>
            """, unsafe_allow_html=True
        )

        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        table_placeholder = st.empty()

        # ----------------- Run Scraper --------------------
        async def scrape_and_display():
            start_scrape_time = time.time()
            all_results = []
            async for update in run_scraper_async(urls, first_spinner_placeholder):
                progress_bar.progress(update["progress"])
                status_placeholder.markdown(
                    f"Progress: {update['scraped']} / {len(urls)}  \n"
                    f"Emails Found: {update['emails_found']}  \n"
                    f"Estimated Time Left: {update['estimated_time']}"
                )
                table_placeholder.dataframe(pd.DataFrame(update["current_data"]))
                all_results = update["current_data"]

            total_scrape_time = round(time.time() - start_scrape_time, 2)
            second_spinner_placeholder.empty()
            st.success(f"Scraping completed in {total_scrape_time} seconds!")

            emails_df = pd.DataFrame(all_results).drop_duplicates()
            merged_df = df.merge(emails_df, left_on=url_column, right_on="URL", how="left").drop(columns=["URL"])
            csv_data = merged_df.to_csv(index=False).encode("utf-8")

            st.download_button(
                "Download Scraped Emails",
                csv_data,
                "Scraped_by_SeekGps.csv",
                "text/csv"
            )

        asyncio.run(scrape_and_display())
