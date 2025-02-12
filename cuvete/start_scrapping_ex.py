from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import csv
from bs4 import BeautifulSoup

class JobScraper:
    def __init__(self, username, password):
        options = webdriver.ChromeOptions()
        options.add_argument('--disable-notifications')  # Blocks notification popups
        options.add_argument('--disable-popup-blocking')  # Allows controlled popups
        options.add_argument('disable-infobars')
        options.add_argument('start-maximized')
        options.add_argument('disable-dev-shm-usage')
        options.add_argument('no-sandbox')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_argument("disable-blink-feature=AutomationControlled")
        
        self.driver = webdriver.Chrome(options=options)
        
        # First, navigate to the login page
        self.driver.get("https://cuvette.tech/app/company/login")
        time.sleep(10)
        
        # Log in using absolute XPaths
        self.login(username, password)
        
        # Navigate to jobs page
        self.driver.get("https://cuvette.tech/app/other-jobs")
        time.sleep(15)

    def login(self, username, password):
        driver = self.driver
        try:
            # Absolute XPaths for login fields
            user_field = driver.find_element(
                By.XPATH, "/html/body/div[1]/div[4]/div[2]/div[2]/form/div[1]/div[2]/input"
            )
            user_field.send_keys(username)
            
            pass_field = driver.find_element(
                By.XPATH, "/html/body/div[1]/div[4]/div[2]/div[2]/form/div[2]/div/input"
            )
            pass_field.send_keys(password)

            login_button = driver.find_element(
                By.XPATH, "/html/body/div[1]/div[4]/div[2]/div[2]/form/div[4]/button"
            )
            login_button.click()
            time.sleep(5)
        except Exception as e:
            print("Login error:", e)
    
    def scroll_to_bottom(self, wait_time=3):
        driver = self.driver
        last_height = driver.execute_script("return document.body.scrollHeight")
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(wait_time)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    def scrape_jobs(self):
        driver = self.driver
        self.scroll_to_bottom(wait_time=10)
        job_data = []

        # Find all job cards
        job_cards = driver.find_elements(By.CLASS_NAME, 'OtherJobsCard_jobInformation__JdaAA')

        for index, card in enumerate(job_cards, start=1):
            try:
                # Extracting the job title
                job_title = card.find_element(By.CLASS_NAME, 'OtherJobsCard_darkText__356ok').text
                
                # Extracting the company name (assuming it's inside <h1>)
                company_name = card.find_element(By.CLASS_NAME, 'OtherJobsCard_darkText__356ok').text
                
                # Extracting the location
                location = card.find_element(By.CLASS_NAME, 'OtherJobsCard_lightText__12EQI').text
                
                # Extracting skills (these are in spans with class 'OtherJobsCard_label__26HcA')
                skills = [span.text for span in card.find_elements(By.CLASS_NAME, 'OtherJobsCard_label__26HcA')]
                
                # Extracting the job experience
                experience = card.find_element(By.CLASS_NAME, 'OtherJobsCard_lightText__12EQI').text
                
                # Extracting the salary range (if available)
                salary = card.find_elements(By.CLASS_NAME, 'OtherJobsCard_lightText__12EQI')[-2].text

                # Find and click the 'Apply' button
                apply_button = card.find_element(By.XPATH, ".//button[contains(text(), 'Apply')]")
                
                # Scroll the job card into view to ensure it's interactable
                driver.execute_script("arguments[0].scrollIntoView();", card)

                # Ensure that the Apply button is clickable
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable(apply_button))
                apply_button.click()
                time.sleep(2)
                
                # Switch to the new window and grab the URL
                original_window = driver.current_window_handle
                WebDriverWait(driver, 10).until(EC.number_of_windows_to_be(2))
                new_window = [window for window in driver.window_handles if window != original_window][0]
                driver.switch_to.window(new_window)

                job_url = driver.current_url

                # Close new tab and return
                driver.close()
                driver.switch_to.window(original_window)

                # Save data
                job_data.append({
                    "job_index": index,
                    "job_title": job_title,
                    "company": company_name,
                    "location": location,
                    "skills": ", ".join(skills),
                    "experience": experience,
                    "salary": salary,
                    "apply_url": job_url
                })
            
            except Exception as e:
                print(f"Error processing job {index}: {e}")
                continue

        return job_data
    
    def quit_driver(self):
        self.driver.quit()

if __name__ == "__main__":
    username = "sameerpandausa@gmail.com"
    password = "Ganesh12345678@"
    scraper = JobScraper(username, password)
    
    jobs = scraper.scrape_jobs()

    # Writing the collected job data to a CSV file
    with open('job_details.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["job_index", "job_title", "company", "location", "skills", "experience", "salary", "apply_url"])
        writer.writeheader()
        for job in jobs:
            writer.writerow(job)
    
    scraper.quit_driver()
