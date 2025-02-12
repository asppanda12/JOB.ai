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

    def scroll_down_slowly(self):
        driver = self.driver
        driver.execute_script("window.scrollBy(0, 300);")  # Scroll down a small amount (300px)
        time.sleep(2)  # Small delay to let page load

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

    def is_element_present(self, driver, xpath):
        elements = driver.find_elements(By.XPATH, xpath)
        return len(elements) > 0

    def scrape_jobs(self):
        
        driver = self.driver
        self.scroll_to_bottom(wait_time=10)
        driver.execute_script("window.scrollTo(0, 0);")
        job_list_xpath = "/html/body/div[1]/div[5]/div[2]/div[1]/div/div/div[2]/div/div/div"
        job_list_container = driver.find_element(By.XPATH, job_list_xpath)
        job_cards = job_list_container.find_elements(By.XPATH, "./div")
        html_content = job_list_container.get_attribute('outerHTML')
        soup = BeautifulSoup(html_content, 'html.parser')
        print(len(job_cards))
        with open("output.txt", "w", encoding="utf-8") as file:
            file.write(soup.prettify())
        time.sleep(10)
        job_data = []
        original_window = driver.current_window_handle
        idx = 1

        while True:
            job_cards = job_list_container.find_elements(By.XPATH, "./div")  # Get the updated list of job cards
            for index, card in enumerate(job_cards, start=1):
                try:
                    if "OtherJobsCard_externalCard__3y31d" in card.get_attribute("class"):
                        # Full absolute XPath for Apply button with dynamic index
                        card_html = card.get_attribute("outerHTML")
                        print(f"Job Card {index} HTML Content:")
                        with open(f"output_{index}.txt", "w", encoding="utf-8") as file:
                            file.write(card_html)
                        
                        apply_button_xpath = f"/html/body/div[1]/div[5]/div[2]/div[1]/div/div/div[2]/div/div/div/div[{idx}]/div[1]/div[2]/button"                        
                        try:
                            apply_button = driver.find_element(By.XPATH, apply_button_xpath)
                            time.sleep(7)
                            apply_button.click()
                            time.sleep(2)
                            
                            # Wait for new window and switch
                            WebDriverWait(driver, 10).until(EC.number_of_windows_to_be(2))
                            new_window = [window for window in driver.window_handles if window != original_window][0]
                            driver.switch_to.window(new_window)
                            
                            # Get URL from new tab
                            job_url = driver.current_url
                            job_data.append({
                                "job_index": index,
                                "apply_url": job_url
                            })
                            idx += 1
                            # Close new tab and return
                            driver.close()
                            driver.switch_to.window(original_window)                    
                        except Exception as e:
                            print(f"Apply button not found for job {apply_button_xpath}, continuing to scroll...")
                            self.scroll_down_slowly()
                            time.sleep(8)  # Small delay after scrolling before checking again
                    else:
                        print(f"Skipping job {index} as it doesn't have the desired class.")
                        continue
                    
                except Exception as e:
                    print(f"Error processing job {index}: {e}")
                    continue

            # Scroll down slowly after each loop
            self.scroll_down_slowly()
           
            # After scrolling, check if the page height has changed to determine if we've reached the bottom
            new_height = driver.execute_script("return document.body.scrollHeight")
            time.sleep(20)
            if new_height == driver.execute_script("return document.body.scrollHeight"):
                print("End of page reached, stopping scraping.")
                break

        return job_data

    def quit_driver(self):
        self.driver.quit()

if __name__ == "__main__":
    scraper = JobScraper("sameerpandausa@gmail.com", "Ganesh12345678@")
    jobs = scraper.scrape_jobs()
    
    with open('job_links.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Job Index', 'Apply URL'])
        for job in jobs:
            writer.writerow([job['job_index'], job['apply_url']])
    
    scraper.quit_driver()
