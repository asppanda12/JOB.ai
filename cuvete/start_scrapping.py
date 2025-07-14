import os
import sys
sys.path.append('E:/JOB.ai/JOB.ai')  
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import json

def setup_driver():
    options = Options()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def scroll_to_bottom(driver, wait_time=3):
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(wait_time)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def scrape_cuvette_jobs():
    driver = setup_driver()
    all_jobs = []

    try:
        # Navigate to Cuvette jobs page
        driver.get("https://cuvette.tech/app/dashboard/other-jobs")
        time.sleep(15)  # Wait for initial load
        
        # Scroll to load all jobs
        scroll_to_bottom(driver, wait_time=10)
        
        # Find all job cards
        job_cards = driver.find_elements(By.CSS_SELECTOR, "div.OtherJobsCard_externalCard__3y31d")
        print(f"Found {len(job_cards)} job cards.")
    
        for card in job_cards:
            try:
                job_info = {}
                
                # Get company logo
                logo = card.find_element(By.CSS_SELECTOR, "img").get_attribute("src")
                job_info["company_logo"] = logo
                
                # Get job title and location
                title = card.find_element(By.CSS_SELECTOR, "h1.OtherJobsCard_darkText__356ok").text
                print(title)
                location = card.find_element(By.CSS_SELECTOR, "p.OtherJobsCard_lightText__12EQI").text
                job_info["title"] = title
                job_info["location"] = location
                
                # Get skills
                skills = card.find_elements(By.CSS_SELECTOR, "span.OtherJobsCard_label__26HcA")
                job_info["skills"] = [skill.text for skill in skills]
                
                # Get job type, salary and experience
                info_right = card.find_element(By.CSS_SELECTOR, "div.OtherJobsCard_infoTopRight__2bP2W")
                job_type = info_right.find_element(By.CSS_SELECTOR, "p.OtherJobsCard_blueText__1RSuY").text
                salary = info_right.find_elements(By.CSS_SELECTOR, "p.OtherJobsCard_lightText__12EQI")[0].text
                experience = info_right.find_elements(By.CSS_SELECTOR, "p.OtherJobsCard_lightText__12EQI")[1].text
                
                job_info["job_type"] = job_type
                job_info["salary"] = salary
                job_info["experience"] = experience
                
                # Get apply button URL if available
                try:
                    apply_button = card.find_element(By.CSS_SELECTOR, "button.OtherJobsCard_applyButton__AMr1O")
                    job_info["apply_url"] = apply_button.get_attribute("onclick")
                except:
                    job_info["apply_url"] = None
                
                all_jobs.append(job_info)
                
            except Exception as e:
                print(f"Error extracting job card info: {str(e)}")
                continue
                
        return all_jobs
        
    except Exception as e:
        print(f"Error scraping Cuvette jobs: {str(e)}")
        return []
        
    finally:
        driver.quit()

    # Save results to JSON file
    

if __name__ == "__main__":
    jobs = scrape_cuvette_jobs()
    output_file = "cuvette_jobs.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=4, ensure_ascii=False)

    print(f"Scraped {len(jobs)} total jobs. Saved to '{output_file}'")
