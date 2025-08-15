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
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor

#  Helper to display loader countdown
def countdown_loader(seconds=5):
    placeholder = st.empty()
    for sec in range(seconds, 0, -1):
        placeholder.markdown(f"Starting in {sec} seconds…")
        time.sleep(1)
    placeholder.empty()

#  Custom CSS (if provided)
def local_css(file_name="style.css"):
    if os.path.exists(file_name):
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css()

st.set_page_config(layout="centered")
uploaded_file = st.file_uploader("Upload CSV or XLSX file containing Facebook URLs", type=["csv", "xlsx"])
if not uploaded_file:
    st.info("Please upload your file to proceed.")
    st.stop()

try:
    if uploaded_file.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
    url_column = st.selectbox("Select the column containing Facebook URLs", df.columns)
    urls = df[url_column].dropna().unique().tolist()
except Exception as e:
    st.error(f"Error reading uploaded file: {e}")
    st.stop()

if not st.button("Start Scraping"):
    st.stop()

countdown_loader(5)

#  Begin using WebDriver Manager
with st.spinner("Setting up Selenium WebDriver..."):
    driver_path = ChromeDriverManager().install()

async def scrape_async(urls, spinner_placeholder):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=3)

    results = []
    start_time = time.time()

    for idx, url in enumerate(urls):
        batch = await loop.run_in_executor(executor, lambda: scrape_emails(driver, url))
        results.extend(batch)

        elapsed = time.time() - start_time
        remaining = len(urls) - idx - 1
        eta = round((elapsed / (idx + 1)) * remaining / 60, 1) if idx + 1 else 0

        spinner_placeholder.empty()
        yield {
            "progress": (idx + 1) / len(urls),
            "scraped": idx + 1,
            "emails_found": sum(1 for item in results if "@" in item["Email"]),
            "eta": f"{eta} min",
            "data": results.copy()
        }

    driver.quit()

def scrape_emails(driver, url):
    try:
        driver.get(url.rstrip("/") + "/about")
        html = driver.page_source
        emails = list(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html)))
        return [{"URL": url, "Email": e} for e in emails] if emails else [{"URL": url, "Email": "No email found"}]
    except Exception:
        return [{"URL": url, "Email": "Error"}]

#  UI Elements for progress
spinner_placeholder = st.empty()
progress_bar = st.progress(0)
status_placeholder = st.empty()
table_placeholder = st.empty()

async def orchestrate():
    start_time = time.time()
    all_data = []

    async for update in scrape_async(urls, spinner_placeholder):
        progress_bar.progress(update["progress"])
        status_placeholder.markdown(
            f"Scraped {update['scraped']} of {len(urls)} — "
            f"Emails found: {update['emails_found']} — ETA: {update['eta']}"
        )
        table_placeholder.dataframe(pd.DataFrame(update["data"]))
        all_data = update["data"]

    spinner_placeholder.empty()
    duration = round(time.time() - start_time, 2)
    st.success(f"Scraping completed in {duration} seconds!")

    emails_df = pd.DataFrame(all_data).drop_duplicates()
    merged = df.merge(emails_df, left_on=url_column, right_on="URL", how="left").drop(columns=["URL"])
    st.download_button("Download Results", merged.to_csv(index=False).encode("utf-8"), "emails.csv", "text/csv")

asyncio.run(orchestrate())
