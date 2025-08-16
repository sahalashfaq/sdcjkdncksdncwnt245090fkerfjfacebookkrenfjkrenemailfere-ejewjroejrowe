import streamlit as st
import pandas as pd
import re
import asyncio
import time
import os
import zipfile
import urllib.request
import platform
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor

# ----------------- ChromeDriver Downloader --------------------
def get_chromedriver():
    system = platform.system().lower()
    arch = platform.machine().lower()

    chrome_version = "126.0.6478.126"  # Set Chrome version
    base_url = "https://storage.googleapis.com/chrome-for-testing-public"

    if system == "windows":
        platform_folder = "win64"
        zip_name = "chromedriver-win64.zip"
        exe_name = "chromedriver.exe"
    elif system == "darwin":
        platform_folder = "mac-arm64" if "arm" in arch else "mac-x64"
        zip_name = f"chromedriver-{platform_folder}.zip"
        exe_name = "chromedriver"
    else:  # linux
        platform_folder = "linux64"
        zip_name = "chromedriver-linux64.zip"
        exe_name = "chromedriver"

    url = f"{base_url}/{chrome_version}/{platform_folder}/{zip_name}"
    driver_dir = os.path.join(os.getcwd(), "drivers")
    os.makedirs(driver_dir, exist_ok=True)
    zip_path = os.path.join(driver_dir, zip_name)

    driver_path = os.path.join(driver_dir, exe_name)
    if not os.path.exists(driver_path):
        st.write(f"⬇️ Downloading ChromeDriver from {url}")
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(driver_dir)
        os.remove(zip_path)

    os.chmod(driver_path, 0o755)
    return driver_path


# ----------------- Email Extractor --------------------
def extract_emails(text):
    return re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)


# ----------------- Scraper --------------------
def scrape_url(url, driver_path):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get(url)
        time.sleep(2)
        emails = extract_emails(driver.page_source)
    except Exception as e:
        emails = [f"Error: {e}"]
    finally:
        driver.quit()

    return {"url": url, "emails": emails}


async def run_scraper_async(urls, driver_path, progress_placeholder):
    results = []
    loop = asyncio.get_event_loop()

    with ThreadPoolExecutor(max_workers=3) as executor:
        tasks = [
            loop.run_in_executor(executor, scrape_url, url, driver_path)
            for url in urls
        ]
        for i, task in enumerate(asyncio.as_completed(tasks)):
            result = await task
            results.append(result)
            progress_placeholder.text(f"Scraped {i+1}/{len(urls)} URLs")

    return results


# ----------------- Streamlit UI --------------------
async def scrape_and_display():
    st.title("📧 Facebook Email Scraper")

    uploaded_file = st.file_uploader("Upload CSV or XLSX with URLs", type=["csv", "xlsx"])
    if uploaded_file is None:
        return

    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    if "url" not in df.columns:
        st.error("The file must contain a 'url' column.")
        return

    urls = df["url"].dropna().tolist()
    st.info(f"Found {len(urls)} URLs")

    if st.button("Start Scraping"):
        driver_path = get_chromedriver()
        progress_placeholder = st.empty()
        results = await run_scraper_async(urls, driver_path, progress_placeholder)

        # Display results
        result_df = pd.DataFrame(results)
        st.dataframe(result_df)

        # Export to CSV
        csv = result_df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, "emails.csv", "text/csv")


if __name__ == "__main__":
    asyncio.run(scrape_and_display())
