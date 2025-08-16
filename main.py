import streamlit as st
import pandas as pd
import re
import asyncio
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor

# ----------------- Custom CSS Loader --------------------
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

local_css("style.css")

# ----------------- ChromeDriver Setup --------------------
def get_chrome_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # Only headless mode

    service = Service("/usr/bin/chromedriver")  # Update path if needed
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # ChromeDriver test
    try:
        version = driver.capabilities.get("browserVersion") or driver.capabilities.get("version")
        st.info(f"ChromeDriver initialized successfully! Chrome version: {version}")
    except Exception as e:
        st.error(f"ChromeDriver failed to start: {e}")
        driver.quit()
        st.stop()

    return driver

# ----------------- Scraper Logic --------------------
def scrape_emails_from_url(driver, url):
    about_url = url.rstrip("/") + "/about"
    try:
        driver.get(about_url)
        # Wait for page to load fully (max 5 seconds)
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except:
            pass  # Continue even if timeout

        html = driver.page_source
        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html)
        emails = list(set(emails))
        return [{"URL": url, "Email": email} for email in emails] if emails else [{"URL": url, "Email": "No email found"}]
    except Exception:
        return [{"URL": url, "Email": "Error fetching"}]

async def run_scraper_async(urls, driver, spinner_placeholder):
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
        est_seconds = (elapsed / (i + 1)) * remaining if i + 1 > 0 else 0
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
st.set_page_config(page_title="Facebook Email Scraper", layout="centered")
st.title("Facebook Email Scraper Tool")

uploaded_file = st.file_uploader("Upload CSV or XLSX file containing Facebook URLs", type=["csv", "xlsx"])

if uploaded_file:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
        url_column = st.selectbox("Select the column containing Facebook URLs", df.columns)
        urls = df[url_column].dropna().unique().tolist()
    except Exception as e:
        st.error(f"Failed to process file: {e}")
        st.stop()

    if st.button("Start Scraping"):
        first_spinner_placeholder = st.empty()
        for i in range(3, 0, -1):
            first_spinner_placeholder.markdown(f"<p>Starting in {i}...</p>", unsafe_allow_html=True)
            time.sleep(1)

        driver = get_chrome_driver()  # ChromeDriver check

        second_spinner_placeholder = st.empty()
        second_spinner_placeholder.markdown("<p>Processing…</p>", unsafe_allow_html=True)

        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        table_placeholder = st.empty()

        async def scrape_and_display():
            start_scrape_time = time.time()
            all_results = []
            async for update in run_scraper_async(urls, driver, first_spinner_placeholder):
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
                "Scraped_Emails.csv",
                "text/csv"
            )

        asyncio.run(scrape_and_display())
