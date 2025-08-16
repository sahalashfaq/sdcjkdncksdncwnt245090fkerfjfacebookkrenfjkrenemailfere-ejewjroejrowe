import streamlit as st
import pandas as pd
import re
import asyncio
import time
import os
import platform
import subprocess
import zipfile
import urllib.request
import json
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

# ----------------- ChromeDriver Installer --------------------
def install_chrome_driver_hidden():
    system_os = platform.system().lower()
    base_driver_dir = os.path.join(os.getcwd(), "drivers")
    os.makedirs(base_driver_dir, exist_ok=True)

    # Decide binary name based on OS
    if "windows" in system_os:
        driver_name = "chromedriver.exe"
    elif "linux" in system_os:
        driver_name = "chromedriver"
    elif "darwin" in system_os:
        driver_name = "chromedriver"
    else:
        raise Exception("Unsupported OS")

    driver_path = os.path.join(base_driver_dir, driver_name)

    # If already exists, return it
    if os.path.exists(driver_path):
        return driver_path

    st.info("Downloading ChromeDriver... Please wait ⏳")

    # Detect local Chrome major version
    try:
        if "windows" in system_os:
            version = subprocess.check_output(
                r'reg query "HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon" /v version',
                shell=True
            ).decode("utf-8")
            chrome_version = re.search(r"(\d+)\.", version).group(1)
        elif "linux" in system_os:
            version = subprocess.check_output(["google-chrome", "--version"]).decode("utf-8")
            chrome_version = re.search(r"(\d+)\.", version).group(1)
        elif "darwin" in system_os:
            version = subprocess.check_output(
                ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"]
            ).decode("utf-8")
            chrome_version = re.search(r"(\d+)\.", version).group(1)
    except Exception as e:
        raise Exception("Could not detect Chrome version. Please install Chrome first.") from e

    # Get latest matching ChromeDriver version
    latest_url = f"https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_{chrome_version}"
    with urllib.request.urlopen(latest_url) as response:
        latest_version = response.read().decode("utf-8").strip()

    # Build download URL based on OS
    if "windows" in system_os:
        zip_url = f"https://storage.googleapis.com/chrome-for-testing-public/{latest_version}/win64/chromedriver-win64.zip"
    elif "linux" in system_os:
        zip_url = f"https://storage.googleapis.com/chrome-for-testing-public/{latest_version}/linux64/chromedriver-linux64.zip"
    elif "darwin" in system_os:
        zip_url = f"https://storage.googleapis.com/chrome-for-testing-public/{latest_version}/mac-x64/chromedriver-mac-x64.zip"

    zip_path = os.path.join(base_driver_dir, "chromedriver.zip")

    # Download zip
    urllib.request.urlretrieve(zip_url, zip_path)

    # Extract chromedriver binary
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for file in zip_ref.namelist():
            if driver_name in file:
                zip_ref.extract(file, base_driver_dir)
                extracted_path = os.path.join(base_driver_dir, file)
                os.rename(extracted_path, driver_path)
                break

    os.remove(zip_path)
    os.chmod(driver_path, 0o755)
    return driver_path

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

async def run_scraper_async(urls, driver_path, spinner_placeholder):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    service = Service(executable_path=driver_path)
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
        first_spinner_placeholder = st.empty()
        countdown = 5
        for i in range(countdown, 0, -1):
            first_spinner_placeholder.markdown(
                f"""
                <div style="display:flex;align-items:center;gap:10px;margin:10px 0;">
                    <div class="loader"></div>
                    <p style="margin:0;">Starting process… (approx. 1 or half min)</p>
                </div>
                <style>
                .loader {{
                    border: 6px solid white;
                    border-top: 6px solid #3498db;
                    border-radius: 50%;
                    width: 30px;
                    height: 30px;
                    animation: spin 1s linear infinite;
                }}
                @keyframes spin {{
                    0% {{ transform: rotate(0deg); }}
                    100% {{ transform: rotate(360deg); }}
                }}
                </style>
                """, unsafe_allow_html=True
            )
            time.sleep(1)

        driver_path = install_chrome_driver_hidden()

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

        async def scrape_and_display():
            start_scrape_time = time.time()
            all_results = []
            async for update in run_scraper_async(urls, driver_path, first_spinner_placeholder):
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
