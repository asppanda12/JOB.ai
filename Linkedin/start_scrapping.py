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

def handle_signin_prompt(driver):
    try:
        # Try to find and click the "Not now" button
        not_now_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[text()='Not now']"))
        )
        not_now_button.click()
        print("Clicked 'Not now' on sign-in prompt")
    except:
        print("No sign-in prompt found or unable to dismiss")

def scrape_job_description(driver, job_url):
    driver.get(job_url)
    try:
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "show-more-less-html__markup")))
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        job_container = soup.find('div', class_='show-more-less-html__markup')
        
        if job_container:
            return job_container.get_text(separator='\n', strip=True)
        else:
            return "Job description not found"
    except TimeoutException:
        print(f"Timeout while loading job description for {job_url}")
        return "Failed to load job description"

def scrape_linkedin_jobs(company_name, job_description, location, max_jobs=3):
    proxies = load_proxies('proxy.txt')
    jobs = []
    base_url = create_linkedin_job_search_url(company_name, job_description, location)

    page = 0
    while len(jobs) < max_jobs:
        proxy = get_random_proxy(proxies)
        driver = setup_driver(proxy)
        
        try:
            print(f"Using proxy: {proxy['ip']}:{proxy['port']}")
            url = f"{base_url}&start={page*25}"
            driver.get(url)
            
            handle_signin_prompt(driver)
            
            wait = WebDriverWait(driver, 20)
            job_list = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "jobs-search__results-list")))
            
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            job_listings = soup.find_all('div', class_='base-card')
            
            for job in job_listings:
                if len(jobs) >= max_jobs:
                    break
                
                try:
                    title = job.find('h3', class_='base-search-card__title').text.strip()
                    company = job.find('h4', class_='base-search-card__subtitle').text.strip()
                    job_location = job.find('span', class_='job-search-card__location').text.strip()
                    job_link = job.find('a', class_='base-card__full-link')['href']
                    
                    job_details = scrape_job_description(driver, job_link)
                    
                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": job_location,
                        "link": job_link,
                        "description": job_details
                    })
                    
                    print(f"Scraped job {len(jobs)}/{max_jobs}")
                    
                    time.sleep(random.uniform(1, 3))
                    
                except AttributeError:
                    continue
            
            if len(jobs) >= max_jobs:
                break
            
            print(f"Scraped page {page+1}")
            page += 1
            
            time.sleep(random.uniform(3, 7))
            
        except Exception as e:
            print(f"An error occurred with proxy {proxy['ip']}:{proxy['port']}: {str(e)}")
        
        finally:
            driver.quit()
    
    return jobs

def create_linkedin_job_search_url(company_name, job_description, location):
    base_url = "https://www.linkedin.com/jobs/search/?"
    params = {
        "keywords": f"{company_name} {job_description}",
        "location": location,
        "f_TPR": "r86400",  # Last 24 hours
        "position": "1",
        "pageNum": "0"
    }
    return base_url + urllib.parse.urlencode(params)

def main():
    company_name = "Google"
    job_description = "Software Engineer"
    location = "India"
    max_jobs = 30
    
    scraped_jobs = scrape_linkedin_jobs(company_name, job_description, location, max_jobs)
    
    with open(f'{company_name}_{job_description}_{location}_linkedin_jobs.json', 'w', encoding='utf-8') as f:
        json.dump(scraped_jobs, f, indent=4, ensure_ascii=False)
    
    print(f"Total jobs scraped: {len(scraped_jobs)}")
    print(f"Jobs saved to {company_name}_{job_description}_{location}_linkedin_jobs.json")

if __name__ == "__main__":
    main()

