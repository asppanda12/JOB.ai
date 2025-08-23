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

    extension = f'proxy_auth_{proxy["ip"]}_{proxy["port"]}.zip'
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
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_extension(extension)
    
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def handle_signin_prompt(driver):
    try:
        # Try multiple variations of dismiss buttons
        dismiss_selectors = [
            "//button[contains(text(), 'Not now')]",
            "//button[contains(text(), 'Skip')]",
            "//button[contains(text(), 'Dismiss')]",
            "//button[@aria-label='Dismiss']",
            "//*[@data-tracking-control-name='guest_homepage-basic_nav-header-signin-dismiss']"
        ]
        
        for selector in dismiss_selectors:
            try:
                dismiss_button = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                dismiss_button.click()
                print("Dismissed sign-in prompt")
                time.sleep(1)
                return
            except:
                continue
                
    except Exception as e:
        print(f"No sign-in prompt found or unable to dismiss: {e}")

def scrape_job_description(driver, job_url):
    try:
        driver.get(job_url)
        wait = WebDriverWait(driver, 15)
        
        # Wait for job description to load
        description_selectors = [
            ".show-more-less-html__markup",
            ".jobs-description__content",
            ".jobs-box__html-content"
        ]
        
        description_element = None
        for selector in description_selectors:
            try:
                description_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                break
            except:
                continue
        
        if description_element:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            job_container = soup.select_one('.show-more-less-html__markup') or soup.select_one('.jobs-description__content') or soup.select_one('.jobs-box__html-content')
            
            if job_container:
                return job_container.get_text(separator='\n', strip=True)
        
        return "Job description not found"
        
    except Exception as e:
        print(f"Error scraping job description from {job_url}: {e}")
        return "Failed to load job description"

def scrape_linkedin_jobs(company_name, job_description, location, max_jobs=3):
    proxies = load_proxies('E:/JOB.ai/JOB.ai/Linkedin/proxy.txt')
    jobs = []
    scraped_job_links = set()  # Track scraped job links to avoid duplicates
    base_url = create_linkedin_job_search_url(company_name, job_description, location)

    page = 0
    max_pages = 20  # Limit to prevent infinite loop
    
    while len(jobs) < max_jobs and page < max_pages:
        proxy = get_random_proxy(proxies)
        driver = None
        extension_file = None
        
        try:
            print(f"Scraping page {page + 1}, using proxy: {proxy['ip']}:{proxy['port']}")
            driver = setup_driver(proxy)
            extension_file = f'proxy_auth_{proxy["ip"]}_{proxy["port"]}.zip'
            
            # Construct URL with proper pagination
            url = f"{base_url}&start={page * 25}"
            print(f"URL: {url}")
            
            driver.get(url)
            time.sleep(random.uniform(3, 5))
            
            handle_signin_prompt(driver)
            
            # Wait for job results to load
            wait = WebDriverWait(driver, 20)
            
            # Try different selectors for job listings
            job_list_selectors = [
                ".jobs-search__results-list",
                ".jobs-search-results-list",
                "[data-testid='job-search-results-list']"
            ]
            
            job_list = None
            for selector in job_list_selectors:
                try:
                    job_list = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    break
                except:
                    continue
            
            if not job_list:
                print(f"No job listings found on page {page + 1}")
                break
            
            # Scroll to load all jobs on the page
            last_height = driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_scroll_attempts = 5
            
            while scroll_attempts < max_scroll_attempts:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(2, 4))
                
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                    
                last_height = new_height
                scroll_attempts += 1
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Try different selectors for job cards
            job_card_selectors = [
                'div.base-card',
                'div.job-search-card',
                '[data-testid="job-search-card"]',
                '.jobs-search-results__list-item'
            ]
            
            job_listings = []
            for selector in job_card_selectors:
                job_listings = soup.select(selector)
                if job_listings:
                    break
            
            print(f"Found {len(job_listings)} job listings on page {page + 1}")
            
            if not job_listings:
                print(f"No job listings found on page {page + 1}, breaking")
                break
            
            page_jobs_found = 0
            for job in job_listings:
                if len(jobs) >= max_jobs:
                    break
                
                try:
                    # Try multiple selectors for job title
                    title_element = (job.select_one('h3.base-search-card__title') or 
                                   job.select_one('.job-search-card__title') or
                                   job.select_one('a[data-tracking-control-name="public_jobs_jserp-result_search-card-title"]'))
                    
                    if not title_element:
                        continue
                        
                    title = title_element.get_text(strip=True)
                    
                    # Try multiple selectors for company
                    company_element = (job.select_one('h4.base-search-card__subtitle') or
                                     job.select_one('.job-search-card__subtitle') or
                                     job.select_one('a[data-tracking-control-name="public_jobs_jserp-result_job-search-card-subtitle"]'))
                    
                    company = company_element.get_text(strip=True) if company_element else "Unknown Company"
                    
                    # Try multiple selectors for location
                    location_element = (job.select_one('span.job-search-card__location') or
                                      job.select_one('.job-search-card__location'))
                    
                    job_location = location_element.get_text(strip=True) if location_element else "Unknown Location"
                    
                    # Try multiple selectors for job link
                    link_element = (job.select_one('a.base-card__full-link') or
                                  job.select_one('a[data-tracking-control-name="public_jobs_jserp-result_search-card-title"]'))
                    
                    if not link_element:
                        continue
                        
                    job_link = link_element.get('href')
                    
                    if not job_link or job_link in scraped_job_links:
                        continue
                    
                    scraped_job_links.add(job_link)
                    
                    print(f"Scraping job details for: {title} at {company}")
                    
                    # Get detailed job description
                    job_details = scrape_job_description(driver, job_link)
                    
                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": job_location,
                        "link": job_link,
                        "description": job_details
                    })
                    
                    page_jobs_found += 1
                    print(f"Successfully scraped job {len(jobs)}/{max_jobs}")
                    
                    # Random delay between job scraping
                    time.sleep(random.uniform(2, 4))
                    
                except Exception as e:
                    print(f"Error scraping individual job: {e}")
                    continue
            
            print(f"Found {page_jobs_found} new jobs on page {page + 1}")
            
            # If no new jobs found on this page, break
            if page_jobs_found == 0:
                print("No new jobs found on this page, stopping pagination")
                break
            
            page += 1
            
            # Longer delay between pages
            time.sleep(random.uniform(5, 10))
            
        except Exception as e:
            print(f"An error occurred with proxy {proxy['ip']}:{proxy['port']}: {str(e)}")
            # Continue to next page with different proxy
        
        finally:
            if driver:
                driver.quit()
            # Clean up extension file
            if extension_file and os.path.exists(extension_file):
                try:
                    os.remove(extension_file)
                except:
                    pass
    
    return jobs

def create_linkedin_job_search_url(company_name, job_description, location):
    base_url = "https://www.linkedin.com/jobs/search/?"
    
    # Build keywords - if company_name is empty, just use job_description
    if company_name.strip():
        keywords = f"{company_name} {job_description}"
    else:
        keywords = job_description
    
    params = {
        "keywords": keywords,
        "location": location,
        "f_TPR": "r86400",  # Last 24 hours
        "position": "1",
        "pageNum": "0",
        "sortBy": "R"  # Most recent
    }
    return base_url + urllib.parse.urlencode(params)

def main():
      # Leave empty to search all companies
    job_description_12 = ["Data Scientist", "Machine Learning Engineer", "AI Engineer", "Data Analyst", "Business Analyst", "Data Engineer","Software Engineer"]
    for job in job_description_12:
        job_description = job
        company_name = ""
        location = "India"
        max_jobs = 500
        
        print(f"Starting to scrape LinkedIn jobs...")
        print(f"Search criteria: {job_description} in {location}")
        if company_name:
            print(f"Company filter: {company_name}")
        
        scraped_jobs = scrape_linkedin_jobs(company_name, job_description, location, max_jobs)
        
        # Create filename
        company_part = company_name if company_name else "All_Companies"
        filename = f'{company_part}_{job_description}_{location}_linkedin_jobs.json'
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(scraped_jobs, f, indent=4, ensure_ascii=False)
        
        print(f"Total jobs scraped: {len(scraped_jobs)}")
        print(f"Jobs saved to {filename}")

if __name__ == "__main__":
    main()