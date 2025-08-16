import streamlit as st
import pandas as pd
import re
import asyncio
import time
import os
import zipfile
import platform
import subprocess
import urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor

# ----------------- ChromeDriver Setup --------------------
def get_chromedriver():
    system = platform.system().lower()
    arch = platform.machine().lower()

    base_url = "https://storage.googleapis.com/chrome-for-testing-public/"
    chrome_version = "126.0.6478.126"  # set compatible version

    if system == "windows":
        zip_name = "chromedriver-win64.zip"
        exe_name = "chromedriver.exe"
    elif system == "darwin":
        zip_name = "chromedriver-mac-x64.zip" if "x86" in arch else "chromedriver-mac-arm64.zip"
        exe_name = "chromedriver"
    else:
        zip_name = "chromedriver-linux64.zip"
        exe_name = "chromedriver"

    url = f"{base_url}{chrome_version}/chromedriver/{zip_name}"
    driver_dir = os.path.join(os.getcwd(), "drivers")
    os.makedirs(driver_dir, exist_ok=True)
    zip_path = os.path.join(driver_dir, zip_name)

    if not os.path.exists(os.path.join(driver_dir, exe_name)):
        st.write("⬇️ Downloading ChromeDriver...")
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(driver_dir)
        os.remove(zip_path)

    driver_path = os.path.join(driver_dir, exe_name)
    os.chmod(driver_path, 0o755)
    return driver_path

# ----------------- Scraper Function --------------------
async def scrape_url(url, driver_path):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape_url_blocking, url, driver_path)

def _scrape_url_blocking(url, driver_path):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    result = {"url": url, "email": None}
    try:
        driver.get(url)
        time.sleep(3)
        text = driver.page_source
        emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        if emails:
            result["email"] = emails[0]
    except Exception as e:
        result["error"] = str(e)
    finally:
        driver.quit()

    return result

# ----------------- Async Generator --------------------
async def run_scraper_async(urls, driver_path):
    for url in urls:
        result = await scrape_url(url, driver_path)
        yield result  # stream results

# ----------------- Streamlit UI --------------------
async def scrape_and_display():
    st.title("📧 Facebook Email Scraper Tool")

    uploaded_file = st.file_uploader("Upload CSV/XLSX with URLs", type=["csv", "xlsx"])

    if uploaded_file is not None:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        urls = df.iloc[:, 0].dropna().tolist()
        st.write("✅ Loaded URLs:", urls)

        driver_path = get_chromedriver()

        results = []
        progress = st.progress(0)
        total = len(urls)

        i = 0
        async for result in run_scraper_async(urls, driver_path):
            results.append(result)
            i += 1
            progress.progress(i / total)
            st.write(result)

        results_df = pd.DataFrame(results)
        st.download_button(
            "📥 Download Results CSV",
            results_df.to_csv(index=False),
            "results.csv",
            "text/csv"
        )

if __name__ == "__main__":
    asyncio.run(scrape_and_display())
