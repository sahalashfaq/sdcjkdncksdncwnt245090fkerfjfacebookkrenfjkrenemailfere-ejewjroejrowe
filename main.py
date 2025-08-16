import streamlit as st
import pandas as pd
import asyncio
import time
import os
import platform
import zipfile
import tarfile
import subprocess
import urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor

# ----------------- Utility Functions --------------------

DRIVERS_DIR = "drivers"
os.makedirs(DRIVERS_DIR, exist_ok=True)

def download_file(url, dest):
    if not os.path.exists(dest):
        st.info(f"Downloading: {url}")
        urllib.request.urlretrieve(url, dest)
    return dest

def extract_zip(zip_path, extract_to):
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_to)

def extract_tar(tar_path, extract_to):
    with tarfile.open(tar_path, "r:gz") as tar_ref:
        tar_ref.extractall(extract_to)

def setup_chromium_and_driver():
    arch = platform.machine()
    if arch in ["aarch64", "arm64"]:
        # ARM64 Linux (Streamlit Cloud often runs this)
        chromium_url = "https://commondatastorage.googleapis.com/chromium-browser-snapshots/Linux_ARM64/123456/chrome-linux-arm64.zip"
        chromedriver_url = "https://storage.googleapis.com/chrome-for-testing-public/126.0.6478.126/linux-arm64/chromedriver-linux-arm64.zip"
    else:
        # Default to Linux x86_64
        chromium_url = "https://commondatastorage.googleapis.com/chromium-browser-snapshots/Linux_x64/123456/chrome-linux.zip"
        chromedriver_url = "https://storage.googleapis.com/chrome-for-testing-public/126.0.6478.126/linux64/chromedriver-linux64.zip"

    # Paths
    chromium_zip = os.path.join(DRIVERS_DIR, "chromium.zip")
    chromedriver_zip = os.path.join(DRIVERS_DIR, "chromedriver.zip")
    chromium_path = os.path.join(DRIVERS_DIR, "chromium")
    chromedriver_path = os.path.join(DRIVERS_DIR, "chromedriver")

    # Download Chromium
    if not os.path.exists(chromium_path):
        download_file(chromium_url, chromium_zip)
        extract_zip(chromium_zip, DRIVERS_DIR)
        os.rename(os.path.join(DRIVERS_DIR, "chrome-linux"), chromium_path)

    # Download Chromedriver
    if not os.path.exists(chromedriver_path):
        download_file(chromedriver_url, chromedriver_zip)
        extract_zip(chromedriver_zip, DRIVERS_DIR)
        # chromedriver extracted folder has /chromedriver/chromedriver
        if os.path.exists(os.path.join(DRIVERS_DIR, "chromedriver-linux64", "chromedriver")):
            os.rename(os.path.join(DRIVERS_DIR, "chromedriver-linux64", "chromedriver"), chromedriver_path)
        elif os.path.exists(os.path.join(DRIVERS_DIR, "chromedriver-linux-arm64", "chromedriver")):
            os.rename(os.path.join(DRIVERS_DIR, "chromedriver-linux-arm64", "chromedriver"), chromedriver_path)

    # Ensure permissions
    os.chmod(chromedriver_path, 0o755)

    return os.path.join(chromium_path, "chrome"), chromedriver_path

def get_driver():
    chromium_binary, chromedriver_binary = setup_chromium_and_driver()

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.binary_location = chromium_binary

    service = Service(chromedriver_binary)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

# ----------------- Scraper Logic --------------------

async def scrape_url(url):
    driver = get_driver()
    driver.get(url)
    await asyncio.sleep(2)
    title = driver.title
    driver.quit()
    return {"url": url, "title": title}

async def run_scraper_async(urls):
    results = []
    for url in urls:
        result = await scrape_url(url)
        results.append(result)
        yield result
    return results

async def scrape_and_display():
    st.title("Facebook Email Scraper Tool")
    uploaded_file = st.file_uploader("Upload CSV/XLSX with URLs", type=["csv", "xlsx"])

    if uploaded_file is not None:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        urls = df.iloc[:, 0].dropna().tolist()
        st.write("Loaded URLs:", urls)

        results = []
        progress = st.progress(0)

        async for i, result in enumerate(run_scraper_async(urls)):
            results.append(result)
            progress.progress((i + 1) / len(urls))
            st.write(result)

        results_df = pd.DataFrame(results)
        st.download_button("Download Results CSV", results_df.to_csv(index=False), "results.csv", "text/csv")

if __name__ == "__main__":
    asyncio.run(scrape_and_display())
