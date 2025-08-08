import streamlit as st
import pandas as pd
import re
import asyncio
import time
import os
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor

# --------- Paths for Chromium and Chromedriver
CHROME_PATH = "/usr/bin/google-chrome"
CHROMEDRIVER_PATH = "/usr/bin/chromedriver"

# --------- Function to Install Chromium if Not Present
def ensure_chromium_installed():
    if os.path.exists(CHROME_PATH) and os.path.exists(CHROMEDRIVER_PATH):
        return True

    with st.spinner("Installing Chromium and Chromedriver... This may take 1–2 minutes"):
        start_time = time.time()
        try:
            subprocess.run("apt-get update", shell=True, check=True)
            subprocess.run("apt-get install -y chromium-browser chromium-chromedriver", shell=True, check=True)
            elapsed = round(time.time() - start_time, 1)
            st.success(f"Chromium installed in {elapsed} seconds.")
            return True
        except subprocess.CalledProcessError:
            st.error("❌ Chromium installation failed. Try again or use a supported environment.")
            return False

# --------- Setup Page
st.set_page_config(layout="centered", page_title="Facebook Email Scraper")

# --------- Check & Install Chromium
if not ensure_chromium_installed():
    st.stop()

# --------- Create Selenium Chrome Driver
def get_driver():
    chrome_options = Options()
    chrome_options.binary_location = CHROME_PATH
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    service = Service(executable_path=CHROMEDRIVER_PATH)
    return webdriver.Chrome(service=service, options=chrome_options)

# --------- Scrape Emails from One URL
def scrape_emails_from_url(url):
    try:
        driver = get_driver()
        driver.get(url)
        html = driver.page_source
        driver.quit()
        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html)
        emails = list(set(emails))
        return (
            [{"URL": url, "Email": email} for email in emails]
            if emails
            else [{"URL": url, "Email": "No email found"}]
        )
    except Exception:
        return [{"URL": url, "Email": "Error fetching"}]

# --------- Asynchronous Scraping of All URLs
async def run_scraper_async(urls, spinner_placeholder):
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=3)
    start_time = time.time()
    results = []

    for i, url in enumerate(urls):
        row_result = await loop.run_in_executor(executor, scrape_emails_from_url, url)
        results.extend(row_result)

        elapsed = time.time() - start_time
        remaining = len(urls) - (i + 1)
        est_seconds = (elapsed / (i + 1)) * remaining
        est_minutes = round(est_seconds / 60, 1)

        if i == 0:
            spinner_placeholder.empty()

        yield {
            "progress": (i + 1) / len(urls),
            "scraped": i + 1,
            "emails_found": len([e for e in results if "@" in e["Email"]]),
            "estimated_time": f"{est_minutes} min",
            "current_data": list(results),
        }

# --------- UI: Upload File
st.title("📧 Facebook Email Scraper")
uploaded_file = st.file_uploader("Upload a CSV or XLSX file containing Facebook URLs", type=["csv", "xlsx"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        url_column = st.selectbox("Select the column containing Facebook URLs", df.columns)
        urls = df[url_column].dropna().unique().tolist()

    except Exception as e:
        st.error(f"❌ Failed to process file: {e}")
        st.stop()

    if st.button("🚀 Start Scraping"):
        spinner_placeholder = st.empty()
        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        table_placeholder = st.empty()

        async def scrape_and_display():
            all_results = []
            async for update in run_scraper_async(urls, spinner_placeholder):
                progress_bar.progress(update["progress"])
                status_placeholder.markdown(f"""
                    ✅ **Scraped:** {update["scraped"]} / {len(urls)}  
                    📬 **Emails Found:** {update["emails_found"]}  
                    ⏳ **Estimated Time Left:** {update["estimated_time"]}
                """)
                table_placeholder.dataframe(pd.DataFrame(update["current_data"]))
                all_results = update["current_data"]

            st.success("✅ Scraping completed successfully!")

            # Merge with original and export
            emails_df = pd.DataFrame(all_results).drop_duplicates()
            merged_df = df.merge(emails_df, left_on=url_column, right_on="URL", how="left")
            merged_df.drop(columns=["URL"], inplace=True)
            csv_data = merged_df.to_csv(index=False).encode("utf-8")

            st.download_button(
                "⬇️ Download Scraped Emails",
                csv_data,
                "scraped_emails.csv",
                "text/csv"
            )

        asyncio.run(scrape_and_display())
