from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
import logging
import pickle
import os
import zipfile
import random
from selenium.webdriver.chrome.options import Options

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def wait_for_element(driver, by, value, timeout=30):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )

def wait_for_clickable(driver, by, value, timeout=30):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )

def sign_in_glassdoor(driver, email, password):
    try:
        # Navigate to the sign-in page
        driver.get("https://www.glassdoor.co.in/profile/login_input.htm")
        
        # Wait for the email input field and enter the email
        email_input = wait_for_element(driver, By.ID, "inlineUserEmail")
        email_input.send_keys(email)
        
        # Click the "Continue with Email" button
        continue_button = wait_for_clickable(driver, By.XPATH, "//button[@data-test='email-form-button']")
        continue_button.click()
        
        # Wait for the password input field and enter the password
        password_input = wait_for_element(driver, By.ID, "inlineUserPassword")
        password_input.send_keys(password)
        
        # Click the "Sign In" button
        sign_in_button = wait_for_clickable(driver, By.XPATH, "//button[@type='submit' and contains(.,'Sign in')]")
        sign_in_button.click()
        
        # Wait for the sign-in process to complete
        time.sleep(5)
        
        logger.info("Successfully signed in to Glassdoor")
        
        # Save the cookies to a file
        pickle.dump(driver.get_cookies(), open("glassdoor_cookies.pkl", "wb"))
    except Exception as e:
        logger.error(f"Error during sign-in process: {str(e)}")
        raise

def load_cookies(driver):
    if os.path.exists("glassdoor_cookies.pkl"):
        cookies = pickle.load(open("glassdoor_cookies.pkl", "rb"))
        for cookie in cookies:
            driver.add_cookie(cookie)
        return True
    return False

def get_chrome_options(use_proxy=True):
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in background
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Get the directory of the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)  # JOB.ai directory

    if use_proxy:
        proxy_auth_path = os.path.join(parent_dir, 'proxy_auth.zip')
        proxy_txt_path = os.path.join(parent_dir, 'proxy.txt')

        # Check for proxy_auth.zip
        if os.path.exists(proxy_auth_path):
            with zipfile.ZipFile(proxy_auth_path) as proxy_zip:
                proxy_list = [line.decode('utf-8').strip() for line in proxy_zip.open('proxy_auth.txt').readlines()]
        # Check for proxy.txt if proxy_auth.zip is not found
        elif os.path.exists(proxy_txt_path):
            with open(proxy_txt_path, 'r') as proxy_file:
                proxy_list = [line.strip() for line in proxy_file]
        else:
            raise FileNotFoundError("Neither proxy_auth.zip nor proxy.txt found")

        if proxy_list:
            proxy = random.choice(proxy_list)
            chrome_options.add_argument(f'--proxy-server={proxy}')
        else:
            print("No proxies found in the files")

    # Add background.js if it exists
    background_js_path = os.path.join(parent_dir, 'background.js')
    if os.path.exists(background_js_path):
        chrome_options.add_extension(background_js_path)

    return chrome_options

def get_salary_range(driver, job_title, company_name):
    try:
        # Construct the search URL
        search_query = f"{job_title} at {company_name}"
        url = f"https://www.glassdoor.co.in/Salaries/india-{search_query.replace(' ', '-')}-salary-SRCH_IL.0,5_IN115_KO6,{6+len(search_query)}.htm"
        
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # Check for career progression information
        try:
            career_step = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test='occ-career-progress-0']"))
            )
            job_title_element = career_step.find_element(By.CSS_SELECTOR, ".CareerSteps_JobTitleLink__E28AD")
            salary_range_element = career_step.find_element(By.CSS_SELECTOR, "div > span")
            
            job_title = job_title_element.text
            salary_range = salary_range_element.text
            
            return f"Career progression (first step): {job_title} - {salary_range}"
        except (TimeoutException, NoSuchElementException) as e:
            logger.error(f"Error finding career progression: {str(e)}")
        
        # If career progression not found, try other salary elements
        salary_selectors = [
            ".TotalPayRange_StyledAverageBasePay__3rLBs",
            "[data-test='salaryEstimate']",
            ".css-1hbqxax",
            ".salaryEstimate"
        ]
        
        for selector in salary_selectors:
            try:
                salary_element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                return salary_element.text
            except (TimeoutException, NoSuchElementException):
                continue
        
        # If still no data found
        return "No salary or career progression data found"
    
    except Exception as e:
        logger.error(f"Error fetching salary data: {str(e)}")
        driver.save_screenshot(f"error_{job_title}_{company_name}.png")
        logger.info(f"Screenshot saved as 'error_{job_title}_{company_name}.png'")
        return f"Error fetching salary data: {str(e)}"

def scrape_glassdoor_salaries(job_listings, email, password):
    chrome_options = get_chrome_options()
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        driver.get("https://www.glassdoor.co.in")
        
        if not load_cookies(driver):
            sign_in_glassdoor(driver, email, password)
        else:
            logger.info("Loaded cookies from cache")
            driver.refresh()  # Refresh the page to apply the cookies
            time.sleep(5)  # Wait for the page to load
        
        for job in job_listings:
            job_title = job['Job Title']
            company_name = job['Company Name']
            
            logger.info(f"Searching Glassdoor salary for {job_title} at {company_name}")
            salary_range = get_salary_range(driver, job_title, company_name)
            job['Glassdoor Estimated Salary Range'] = salary_range
            
            # Add a delay to avoid overwhelming the server with requests
            time.sleep(5)
        
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
    finally:
        driver.quit()
    
    return job_listings

# Example usage
if __name__ == "__main__":
    import json
    
    # Load your job listings from the JSON file
    with open('naukri_job_listings.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    job_listings = data['job_listings']
    
    # Replace with your Glassdoor credentials
    email = "alternative0of0iiit@gmail.com"
    password = "Ganesh12345@"
    
    # Scrape salaries for the first 5 job listings (for demonstration)
    updated_listings = scrape_glassdoor_salaries(job_listings[:5], email, password)
    
    # Save the updated listings back to a JSON file
    output = {"job_listings": updated_listings}
    with open('naukri_job_listings_with_glassdoor_salaries.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    
    logger.info("Updated job listings saved to 'naukri_job_listings_with_glassdoor_salaries.json'")