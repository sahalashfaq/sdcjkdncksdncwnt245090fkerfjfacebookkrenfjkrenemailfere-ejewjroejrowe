import streamlit as st
import pandas as pd
import re
import time

# ----------------- Set Page Config First --------------------
st.set_page_config(layout="centered")

# ----------------- Custom CSS Loader --------------------
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass  # optional style.css

local_css("style.css")

# ----------------- Scraper Logic --------------------
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def init_driver():
    chrome_options = Options()
    chrome_options.binary_location = "/usr/bin/chromium"  # ✅ Correct path on Streamlit Cloud
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920x1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    return driver



def scrape_emails_from_url(url):
    try:
        driver = init_driver()
        driver.get(url)
        time.sleep(2)
        html = driver.page_source
        driver.quit()

        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html)
        emails = list(set(emails))
        return (
            [{"URL": url, "Email": email} for email in emails]
            if emails else [{"URL": url, "Email": "No email found"}]
        )
    except Exception as e:
        return [{"URL": url, "Email": f"Error: {str(e)}"}]

# ----------------- Streamlit UI --------------------
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
        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        table_placeholder = st.empty()
        all_results = []

        total = len(urls)
        start_time = time.time()

        for i, url in enumerate(urls):
            row_result = scrape_emails_from_url(url)
            all_results.extend(row_result)

            elapsed = time.time() - start_time
            remaining = total - (i + 1)
            est_seconds = (elapsed / (i + 1)) * remaining
            est_minutes = round(est_seconds / 60, 1)

            progress_bar.progress((i + 1) / total)
            status_placeholder.markdown(f"""
                **Progress:** {i + 1} / {total}  
                **Emails Found:** {len([e for e in all_results if "@" in e["Email"]])}  
                **Estimated Time Left:** {est_minutes} min
            """)
            table_placeholder.dataframe(pd.DataFrame(all_results))

        st.success("Scraping completed successfully!")

        # Merge and prepare CSV
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


