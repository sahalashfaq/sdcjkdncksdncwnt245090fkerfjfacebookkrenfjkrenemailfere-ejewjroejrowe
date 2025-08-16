import streamlit as st
import pandas as pd
import re
import asyncio
import time
import os
import zipfile
import urllib.request
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor

# ----------------- Custom CSS Loader --------------------
st.markdown(
    """
    <style>
        .stButton>button {
            width: 100%;
            border-radius: 8px;
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
        }
        .stProgress > div > div > div > div {
            background-color: #4CAF50;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------- Chrome Driver Setup --------------------
def install_chrome_driver_hidden():
    driver_dir = os.path.join(os.getcwd(), "drivers")
    os.makedirs(driver_dir, exist_ok=True)

    # ✅ Fixed version compatible with Streamlit Cloud Chromium
    chrome_driver_version = "114.0.5735.90"
    url = f"https://chromedriver.storage.googleapis.com/{chrome_driver_version}/chromedriver_linux64.zip"

    zip_path = os.path.join(driver_dir, "chromedriver.zip")
    driver_path = os.path.join(driver_dir, "chromedriver")

    if not os.path.exists(driver_path):
        st.info("Downloading ChromeDriver... Please wait ⏳")
        urllib.request.urlretrieve(url, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(driver_dir)

        os.chmod(driver_path, 0o755)  # make executable
        os.remove(zip_path)

    return driver_path

# ----------------- Email Extraction --------------------
def extract_emails(text):
    return list(set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}", text)))

# ----------------- Scraper Worker --------------------
def scrape_url(url, driver_path):
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.get(url)
        time.sleep(3)  # let page load

        emails = extract_emails(driver.page_source)
        driver.quit()
        return {"url": url, "emails": emails}
    except Exception as e:
        return {"url": url, "emails": [], "error": str(e)}

# ----------------- Async Orchestration --------------------
async def scrape_and_display(urls):
    driver_path = install_chrome_driver_hidden()
    results = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    with ThreadPoolExecutor(max_workers=3) as executor:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(executor, scrape_url, url, driver_path)
            for url in urls
        ]
        for i, task in enumerate(asyncio.as_completed(tasks)):
            result = await task
            results.append(result)
            progress_bar.progress((i + 1) / len(urls))
            status_text.text(f"Processed {i+1}/{len(urls)}")

    return results

# ----------------- Streamlit UI --------------------
st.title("📧 Facebook Email Scraper Tool")

uploaded_file = st.file_uploader("Upload CSV or Excel with URLs", type=["csv", "xlsx"])
if uploaded_file:
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    if "url" not in df.columns:
        st.error("Your file must have a 'url' column")
    else:
        urls = df["url"].dropna().tolist()

        if st.button("Start Scraping"):
            results = asyncio.run(scrape_and_display(urls))
            output_df = pd.DataFrame(results)
            st.dataframe(output_df)

            # Save results
            csv = output_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, "emails.csv", "text/csv")
