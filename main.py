import streamlit as st
import pandas as pd
import re
import time
from tempfile import TemporaryDirectory
import os
import urllib.request
import zipfile
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

#  Simplified countdown loader
def countdown(seconds=5):
    placeholder = st.empty()
    for i in range(seconds, 0, -1):
        placeholder.markdown(f"Starting in {i} seconds…")
        time.sleep(1)
    placeholder.empty()

#  Custom CSS loader
def local_css(file_name="style.css"):
    if os.path.exists(file_name):
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css()

st.set_page_config(layout="centered")
uploaded = st.file_uploader("Upload CSV or XLSX file with Facebook URLs", type=["csv", "xlsx"])
if not uploaded:
    st.info("Please upload a file to proceed.")
    st.stop()

try:
    df = pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded)
    url_col = st.selectbox("Select the column with Facebook URLs", df.columns)
    urls = df[url_col].dropna().unique().tolist()
except Exception as e:
    st.error(f"Error loading file: {e}")
    st.stop()

if not st.button("Start Scraping"):
    st.stop()

countdown(5)

# Estimate download time helper
def estimate_time(bytes_size, mbps=5):
    return bytes_size / (mbps * 1_000_000 / 8)  # returns seconds

# Setup WebDriver via webdriver_manager
with st.spinner("Setting up Selenium WebDriver..."):
    driver_path = ChromeDriverManager().install()

# UI placeholders
progress_bar = st.progress(0)
status = st.empty()
table = st.empty()

# Scrape logic synchronously
results = []
start_time = time.time()

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
service = Service(driver_path)
driver = webdriver.Chrome(service=service, options=options)

for idx, url in enumerate(urls, 1):
    try:
        target = url.rstrip("/") + "/about"
        driver.get(target)
        time.sleep(1)  # minor wait for page load
        html = driver.page_source
        emails = list(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html)))
        row_results = [{"URL": url, "Email": email} for email in emails] or [{"URL": url, "Email": "No email found"}]
    except Exception:
        row_results = [{"URL": url, "Email": "Error"}]
    results.extend(row_results)

    elapsed = time.time() - start_time
    eta = round((elapsed / idx) * (len(urls) - idx) / 60, 1)
    progress_bar.progress(idx / len(urls))
    status.markdown(f"Scraped {idx}/{len(urls)} — Emails: {sum(1 for r in results if '@' in r['Email'])} — ETA: {eta} min")
    table.dataframe(pd.DataFrame(results))

driver.quit()
total = round(time.time() - start_time, 2)
st.success(f"Scraping done in {total} sec!")

df_emails = pd.DataFrame(results).drop_duplicates()
merged = df.merge(df_emails, left_on=url_col, right_on="URL", how="left").drop(columns=["URL"])
st.download_button("Download Results", merged.to_csv(index=False).encode("utf-8"), "scraped_emails.csv", "text/csv")
