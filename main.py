import streamlit as st
import pandas as pd
import re
import asyncio
import time
import os
import zipfile
import urllib.request
import subprocess
import tempfile
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor

# ----------------- Setup Temporary Directory --------------------
temp_dir = tempfile.mkdtemp()

# ----------------- Install Chrome & Driver --------------------
def install_chrome_driver():
    os.system("apt-get update")
    os.system("apt-get install -y wget unzip curl")
    os.system("wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb")
    os.system("dpkg -i google-chrome-stable_current_amd64.deb || apt-get -fy install")

    # Skip subprocess – just download a known working ChromeDriver version
    known_driver_version = "124.0.6367.91"  # Compatible with Chrome 124
    driver_url = f"https://chromedriver.storage.googleapis.com/{known_driver_version}/chromedriver_linux64.zip"

    urllib.request.urlretrieve(driver_url, "chromedriver.zip")
    with zipfile.ZipFile("chromedriver.zip", "r") as zip_ref:
        zip_ref.extractall(temp_dir)

    os.chmod(f"{temp_dir}/chromedriver", 0o755)


install_chrome_driver()

# ----------------- Page Setup --------------------
st.set_page_config(layout="centered")

def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css("style.css")

# ----------------- Session State --------------------
if "total_scraped" not in st.session_state:
    st.session_state.total_scraped = 0
if "estimated_time" not in st.session_state:
    st.session_state.estimated_time = "0 min"

# ----------------- Scraper Logic --------------------
def scrape_emails_from_url(driver, url):
    try:
        driver.get(url)
        html = driver.page_source
        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html)
        emails = list(set(emails))
        return [{"URL": url, "Email": email} for email in emails] if emails else [{"URL": url, "Email": "No email found"}]
    except Exception:
        return [{"URL": url, "Email": "Error fetching"}]

async def run_scraper_async(urls, spinner_placeholder):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.binary_location = "/opt/google/chrome/google-chrome"

    service = Service(executable_path=f"{temp_dir}/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=3)

    start_time = time.time()
    results = []
    total = len(urls)

    for i, url in enumerate(urls):
        row_result = await loop.run_in_executor(executor, scrape_emails_from_url, driver, url)
        results.extend(row_result)
        st.session_state.total_scraped += 1

        elapsed = time.time() - start_time
        remaining = total - (i + 1)
        est_seconds = (elapsed / (i + 1)) * remaining
        est_minutes = round(est_seconds / 60, 1)
        st.session_state.estimated_time = f"{est_minutes} min"

        if i == 0:
            spinner_placeholder.empty()

        yield {
            "progress": (i + 1) / total,
            "scraped": i + 1,
            "emails_found": len([e for e in results if "@" in e["Email"]]),
            "estimated_time": st.session_state.estimated_time,
            "current_data": list(results),
        }

    driver.quit()

# ----------------- File Upload UI --------------------
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
        spinner_placeholder = st.empty()
        countdown_placeholder = st.empty()

        spinner_placeholder.markdown("""
            <div style="display:flex;flex-direction:row;gap:10px;justify-content:flex-start;align-items:center;">
                <div class="loader"></div>
                <p style="margin-top:16px;font-size:14px;color:#555;">Initializing the scraper...</p>
            </div>
            <style>
            .st-b7{ background-color:white !important; box-shadow:0px 0px 1px black; }
            .loader {
                border: 5px solid white;
                box-shadow:0px 0px 2px black;
                border-top: 5px solid #FD653D;
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
        """, unsafe_allow_html=True)

        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        table_placeholder = st.empty()

        async def scrape_and_display():
            all_results = []
            async for update in run_scraper_async(urls, spinner_placeholder):
                progress_bar.progress(update["progress"])
                status_placeholder.markdown(f"""
                    **Progress:** {update["scraped"]} / {len(urls)}  
                    **Emails Found:** {update["emails_found"]}  
                    **Estimated Time Left:** {update["estimated_time"]}
                """)
                table_placeholder.dataframe(pd.DataFrame(update["current_data"]))
                all_results = update["current_data"]

            st.success("Scraping completed successfully!")

            emails_df = pd.DataFrame(all_results).drop_duplicates()
            merged_df = df.merge(emails_df, left_on=url_column, right_on="URL", how="left")
            merged_df.drop(columns=["URL"], inplace=True)
            csv_data = merged_df.to_csv(index=False).encode("utf-8")

            st.download_button(
                "Download Scraped Emails",
                csv_data,
                "Scraped_by_the_SeekGps.csv",
                "text/csv"
            )

        asyncio.run(scrape_and_display())

