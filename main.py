import streamlit as st
import pandas as pd
import re
import asyncio
import time
import os
import zipfile
import urllib.request
import tempfile
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor

# ----------------- Custom CSS Loader --------------------
def load_css():
    st.markdown("""
        <style>
        body {
            background-color: #f5f7fa;
        }
        .stButton>button {
            border-radius: 12px;
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
        }
        .stButton>button:hover {
            background-color: #45a049;
        }
        </style>
    """, unsafe_allow_html=True)

# ----------------- Chrome Driver Installer --------------------
def install_chrome_driver_hidden():
    """Download and extract ChromeDriver compatible with installed Chrome."""
    try:
        # Try to detect Chrome version
        try:
            version = subprocess.check_output(
                ["google-chrome", "--version"]
            ).decode("utf-8").strip().split()[-1]
        except FileNotFoundError:
            try:
                version = subprocess.check_output(
                    ["chromium-browser", "--version"]
                ).decode("utf-8").strip().split()[-1]
            except FileNotFoundError:
                st.error("Could not detect Chrome version. Please make sure Chrome/Chromium is installed.")
                return None

        major_version = version.split(".")[0]
        url = f"https://chromedriver.storage.googleapis.com/LATEST_RELEASE_{major_version}"
        latest_driver_version = urllib.request.urlopen(url).read().decode("utf-8").strip()

        download_url = f"https://chromedriver.storage.googleapis.com/{latest_driver_version}/chromedriver_linux64.zip"
        zip_path = os.path.join(tempfile.gettempdir(), "chromedriver.zip")
        extract_path = os.path.join(tempfile.gettempdir(), "chromedriver")

        # Download driver
        st.info("Downloading ChromeDriver... Please wait ⏳")
        urllib.request.urlretrieve(download_url, zip_path)

        # Extract
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)

        driver_path = os.path.join(extract_path, "chromedriver")
        os.chmod(driver_path, 0o755)
        return driver_path

    except Exception as e:
        st.error(f"Error installing ChromeDriver: {e}")
        return None

# ----------------- Selenium Scraper --------------------
def scrape_email_from_url(url, driver_path):
    """Scrape emails from a given URL using Selenium."""
    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(service=Service(driver_path), options=options)

        driver.get(url)
        time.sleep(3)

        page_source = driver.page_source
        driver.quit()

        emails = list(set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", page_source)))
        return {"url": url, "emails": emails if emails else ["No email found"]}
    except Exception as e:
        return {"url": url, "emails": [f"Error: {str(e)}"]}

# ----------------- Async Wrapper --------------------
async def scrape_and_display(urls):
    driver_path = install_chrome_driver_hidden()
    if not driver_path:
        return []

    loop = asyncio.get_event_loop()
    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        tasks = [loop.run_in_executor(executor, scrape_email_from_url, url, driver_path) for url in urls]
        for task in asyncio.as_completed(tasks):
            result = await task
            results.append(result)
            st.write(f"✅ Scraped: {result['url']}")
    return results

# ----------------- Streamlit UI --------------------
def main():
    st.title("📧 Facebook Email Scraper Tool")
    load_css()

    uploaded_file = st.file_uploader("Upload CSV or Excel with URLs", type=["csv", "xlsx"])
    if uploaded_file:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        # ✅ User selects which column contains URLs
        column = st.selectbox("Select the column that contains URLs", df.columns)

        urls = df[column].dropna().tolist()

        if st.button("🚀 Start Scraping"):
            results = asyncio.run(scrape_and_display(urls))
            output_df = pd.DataFrame(results)
            st.dataframe(output_df)

            # Save results
            csv = output_df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download CSV", csv, "emails.csv", "text/csv")

if __name__ == "__main__":
    main()
