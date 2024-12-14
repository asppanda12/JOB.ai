from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, ElementClickInterceptedException
import json
import time
import logging

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
            title_element = job.find_element(By.CSS_SELECTOR, "[class*='title']")
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

def scrape_naukri():
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')  # Uncomment this line if you want to run in headless mode
    options.add_argument('--start-maximized')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    base_url = "https://www.naukri.com/software-development-software-engineering-software-engineer-data-analyst-data-scientist-ml-data-associate-ml-engineer-jobs"

    all_job_listings = []

    try:
        for page in range(1, 11):  # Scrape 10 pages
            url = f"{base_url}-{page}" if page > 1 else base_url
            driver.get(url)
            logger.info(f"Page {page} loaded")

            wait_for_element(driver, By.TAG_NAME, "body")
            logger.info("Body found")

            # Click on the sort dropdown
            try:
                sort_button = wait_for_clickable(driver, By.ID, "filter-sort")
                sort_button.click()
                logger.info("Clicked sort dropdown")
                time.sleep(2)  # Wait for dropdown to appear

                # Click on the "Date" option
                date_option = wait_for_clickable(driver, By.CSS_SELECTOR, "li[title='Date'] a")
                date_option.click()
                logger.info("Selected 'Date' sorting option")
                time.sleep(5)  # Wait for page to reload with new sorting
            except (NoSuchElementException, ElementClickInterceptedException) as e:
                logger.error(f"Failed to sort by date: {str(e)}")
                driver.save_screenshot(f"sort_error_page_{page}.png")
                logger.info(f"Screenshot saved as 'sort_error_page_{page}.png'")

            # Scroll to load more jobs
            for i in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                logger.info(f"Scrolled {i+1} times")
                time.sleep(2)

            page_job_listings = scrape_page(driver)
            all_job_listings.extend(page_job_listings)

            logger.info(f"Scraped {len(page_job_listings)} jobs from page {page}")

        # Create the final structure
        output = {"job_listings": all_job_listings}

        # Write to JSON file
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
    scrape_naukri()