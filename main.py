import streamlit as st
import pandas as pd
import re
import asyncio
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException
from concurrent.futures import ThreadPoolExecutor, as_completed

# ----------------- Custom CSS Loader --------------------
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning(f"CSS file '{file_name}' not found. Using default styles.")

# ----------------- Scraper Logic --------------------
def scrape_emails_from_url(driver, url):
    about_url = url.rstrip("/") + "/about"
    try:
        driver.get(about_url)
        time.sleep(2)  # Add small delay to allow page to load
        html = driver.page_source
        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html)
        emails = list(set(emails))
        return [{"URL": url, "Email": email} for email in emails] if emails else [{"URL": url, "Email": "No email found"}]
    except WebDriverException as e:
        st.error(f"Error scraping {url}: {str(e)}")
        return [{"URL": url, "Email": "Error fetching"}]
    except Exception as e:
        st.error(f"Unexpected error with {url}: {str(e)}")
        return [{"URL": url, "Email": "Error fetching"}]

async def run_scraper_async(urls, driver_path, spinner_placeholder):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    service = None
    driver = None
    try:
        service = Service(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)  # Set timeout to 30 seconds

        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=3)

        start_time = time.time()
        results = []
        total = len(urls)

        futures = []
        for url in urls:
            futures.append(loop.run_in_executor(executor, scrape_emails_from_url, driver, url))

        for i, future in enumerate(as_completed(futures)):
            row_result = await future
            results.extend(row_result)

            elapsed = time.time() - start_time
            remaining = total - (i + 1)
            est_seconds = (elapsed / (i + 1)) * remaining if (i + 1) > 0 else 0
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

    finally:
        if driver:
            driver.quit()
        if service:
            service.stop()

# ----------------- Streamlit UI --------------------
def main():
    st.set_page_config(layout="centered", page_title="Facebook Email Scraper")
    local_css("style.css")

    st.title("Facebook Email Scraper")
    st.write("Upload a CSV or Excel file containing Facebook profile URLs to scrape emails from their About pages")

    uploaded_file = st.file_uploader("Upload CSV or XLSX file", type=["csv", "xlsx"], 
                                   help="File should contain a column with Facebook profile URLs")

    if uploaded_file:
        try:
            if uploaded_file.name.endswith(".csv"):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            url_column = st.selectbox("Select the column containing Facebook URLs", df.columns,
                                     help="Choose the column that contains the Facebook profile URLs")
            
            urls = df[url_column].dropna().unique().tolist()
            urls = [url for url in urls if isinstance(url, str) and "facebook.com" in url.lower()]
            
            if not urls:
                st.error("No valid Facebook URLs found in the selected column.")
                return

            st.success(f"Found {len(urls)} unique URLs to process")

        except Exception as e:
            st.error(f"Failed to process file: {str(e)}")
            st.stop()

        if st.button("Start Scraping", help="Click to begin scraping emails from Facebook profiles"):
            # First Spinner
            first_spinner_placeholder = st.empty()
            countdown = 5
            for i in range(countdown, 0, -1):
                first_spinner_placeholder.markdown(
                    f"""
                    <div style="display:flex;align-items:center;gap:10px;margin:10px 0;">
                        <div class="loader"></div>
                        <p style="margin:0;">Initializing scraper... Starting in {i} seconds</p>
                    </div>
                    <style>
                    .loader {{
                        border: 6px solid white;
                        border-top: 6px solid #3498db;
                        border-radius: 50%;
                        width: 30px;
                        height: 30px;
                        animation: spin 1s linear infinite;
                    }}
                    @keyframes spin {{
                        0% {{ transform: rotate(0deg); }}
                        100% {{ transform: rotate(360deg); }}
                    }}
                    </style>
                    """, unsafe_allow_html=True
                )
                time.sleep(1)

            # Second Spinner + Progress Bar
            second_spinner_placeholder = st.empty()
            progress_bar = st.progress(0)
            status_placeholder = st.empty()
            table_placeholder = st.empty()

            # Run Scraper
            async def scrape_and_display():
                start_scrape_time = time.time()
                all_results = []
                
                try:
                    async for update in run_scraper_async(urls, "/usr/bin/chromedriver", first_spinner_placeholder):
                        progress_bar.progress(update["progress"])
                        status_placeholder.markdown(
                            f"**Progress:** {update['scraped']} / {len(urls)}  \n"
                            f"**Emails Found:** {update['emails_found']}  \n"
                            f"**Estimated Time Left:** {update['estimated_time']}"
                        )
                        table_placeholder.dataframe(pd.DataFrame(update["current_data"]))
                        all_results = update["current_data"]

                    total_scrape_time = round(time.time() - start_scrape_time, 2)
                    second_spinner_placeholder.empty()
                    st.success(f"Scraping completed in {total_scrape_time} seconds!")
                    
                    if all_results:
                        emails_df = pd.DataFrame(all_results).drop_duplicates()
                        merged_df = df.merge(emails_df, left_on=url_column, right_on="URL", how="left").drop(columns=["URL"])
                        csv_data = merged_df.to_csv(index=False).encode("utf-8")

                        st.download_button(
                            "Download Scraped Emails",
                            csv_data,
                            "facebook_emails.csv",
                            "text/csv",
                            help="Download the results as a CSV file"
                        )
                    else:
                        st.warning("No results were collected during scraping.")
                        
                except Exception as e:
                    st.error(f"An error occurred during scraping: {str(e)}")

            asyncio.run(scrape_and_display())

if __name__ == "__main__":
    main()
