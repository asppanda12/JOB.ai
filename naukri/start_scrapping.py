import os
import zipfile
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import time
import json
import urllib.parse
import logging
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, ElementClickInterceptedException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
def load_proxies(file_path):
    proxies = []
    with open(file_path, 'r') as file:
        for line in file:
            parts = line.strip().split(':')
            if len(parts) == 4:
                proxies.append({
                    'ip': parts[0],
                    'port': parts[1],
                    'username': parts[2],
                    'password': parts[3]
                })
    return proxies

def get_random_proxy(proxies):
    return random.choice(proxies)

def create_proxy_extension(proxy):
    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """

    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
              singleProxy: {
                scheme: "http",
                host: "%s",
                port: parseInt(%s)
              },
              bypassList: ["localhost"]
            }
          };

    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }

    chrome.webRequest.onAuthRequired.addListener(
                callbackFn,
                {urls: ["<all_urls>"]},
                ['blocking']
    );
    """ % (proxy['ip'], proxy['port'], proxy['username'], proxy['password'])

    extension = 'proxy_auth.zip'
    with zipfile.ZipFile(extension, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)
    
    return extension

def setup_driver(proxy):
    extension = create_proxy_extension(proxy)
    
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_extension(extension)
    
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver
def scrape_page(driver):
    job_listings = []
    possible_job_classes = ["jobTuple", "cust-job-tuple", "job-tuple"]
    
    for class_name in possible_job_classes:
        job_tuples = driver.find_elements(By.CLASS_NAME, class_name)
        if job_tuples:
            logger.info(f"Found {len(job_tuples)} job tuples with class '{class_name}'")
            break
    else:
        logger.error("Could not find job listings with any known class names")
        driver.save_screenshot("no_jobs_found.png")
        logger.info("Screenshot saved as 'no_jobs_found.png'")
        return []

    for job in job_tuples:
        try:
            title_element = WebDriverWait(job, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='title']"))
            )
            title = title_element.text
            link = title_element.get_attribute('href')
            company = job.find_element(By.CSS_SELECTOR, "[class*='comp']").text
            experience = job.find_element(By.CSS_SELECTOR, "[class*='exp']").text
            location = job.find_element(By.CSS_SELECTOR, "[class*='loc']").text
            
            try:
                salary = job.find_element(By.CSS_SELECTOR, "[class*='sal']").text
            except NoSuchElementException:
                salary = "Not specified"
            
            job_description = job.find_element(By.CSS_SELECTOR, "[class*='desc']").text
            skills = [skill.text for skill in job.find_elements(By.CSS_SELECTOR, "[class*='tag']")]

            job_dict = {
                "Job Title": title,
                "Job Link": link,
                "Company Name": company,
                "Experience": experience,
                "Salary": salary,
                "Location": location,
                "Job Description": job_description,
                "Skills": skills
            }

            job_listings.append(job_dict)
            logger.info(f"Scraped job: {title}")

        except (NoSuchElementException, StaleElementReferenceException) as e:
            logger.error(f"Error scraping job: {str(e)}")

    return job_listings
def scrape_naukri(link):
    proxies = load_proxies('E:/JOB.ai/JOB.ai/naukri/proxy.txt')
    jobs = []
    
    # Load existing job listings from the JSON file
    try:
        with open('naukri_job_listings.json', 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
            all_job_listings = existing_data.get("job_listings", [])  # Get existing listings or empty list
    except FileNotFoundError:
        all_job_listings = []  # If the file doesn't exist, start with an empty list

    try:
        base_url = link
        proxy = get_random_proxy(proxies)
        driver = setup_driver(proxy)
        try:
            print(f"Using proxy: {proxy['ip']}:{proxy['port']}")
            driver.get(base_url)
            time.sleep(5)  # Wait for the page to load completely
            logger.info("Page source loaded.")
            logger.debug(driver.page_source)  # Log the page source for debugging
            all_job_listings.extend(scrape_page(driver))  # Append new listings to existing data
        except (NoSuchElementException, StaleElementReferenceException) as e:
            logger.error(f"Error scraping job: {str(e)}")
        output = {"job_listings": all_job_listings}
        with open('naukri_job_listings.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=4)
        logger.info(f"Scraped a total of {len(all_job_listings)} job listings. Data saved to 'naukri_job_listings.json'")

    except TimeoutException:
        logger.error("Timed out waiting for page to load")
        driver.save_screenshot("timeout.png")
        logger.info("Screenshot saved as 'timeout.png'")
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        driver.save_screenshot("error.png")
        logger.info("Screenshot saved as 'error.png'")
    finally:
        driver.quit()
if __name__ == "__main__":
    base_url = "https://www.naukri.com/software-development-software-engineering-software-engineer-data-analyst-data-scientist-ml-data-associate-ml-engineer-jobs"

    for page in range(1, 11):  # Scrape 10 pages
            url = f"{base_url}-{page}" if page > 1 else base_url
            scrape_naukri(url)