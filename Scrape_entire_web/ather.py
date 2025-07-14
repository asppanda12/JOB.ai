from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import time

def scrape_ather_jobs():
    driver = webdriver.Chrome()
    job_data = []
    
    try:
        # Navigate to the website
        driver.get("https://careers.atherenergy.com/jobs")
        
        # Wait for initial load
        time.sleep(5)
        
        # Click on the specified division
        division_element = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, '/html/body/div[1]/div[4]/div[2]/div[2]/div/div/div/div[1]/div[1]/div/div[5]/div'))
        )
        division_element.click()
        
        # Wait for jobs to load
        time.sleep(5)
        
        # Wait for the job cards container
        job_cards_container = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[4]/div[3]/div/div/div/div[2]/div'))
        )
        
        # Find all job cards
        job_cards = job_cards_container.find_elements(By.CLASS_NAME, 'card-style-job')
        
        # Process each job card
        for card in job_cards:
            try:
                # Extract basic information
                job_title = card.find_element(By.CLASS_NAME, 'style__JobTitle-sc-1idaqdx-2').text
                location = card.find_element(By.CLASS_NAME, 'style__JobContent-sc-1idaqdx-3').text
                
                # Click on the card to open details in new tab
                card.click()
                time.sleep(2)
                
                # Switch to the new tab
                driver.switch_to.window(driver.window_handles[-1])
                time.sleep(3)
                
                # Wait for and extract descriptions
                description = ""
                description1 = ""
                description2 = ""
                
                try:
                    desc_element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, '//*[@id="__next"]/div[3]/div/div[2]/div[1]/div/div/ul[2]'))
                    )
                    description = desc_element.text
                except:
                    print(f"Could not find description for {job_title}")
                
                try:
                    desc1_element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[3]/div/div[2]/div[1]/div/div/ul[4]'))
                    )
                    description1 = desc1_element.text
                except:
                    print(f"Could not find description1 for {job_title}")
                
                try:
                    desc2_element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[3]/div/div[2]/div[1]/div/div/ul[5]'))
                    )
                    description2 = desc2_element.text
                except:
                    print(f"Could not find description2 for {job_title}")
                
                # Create job info dictionary
                job_info = {
                    'job_title': job_title,
                    'location': location,
                    'description': description,
                    'description1': description1,
                    'description2': description2
                }
                
                job_data.append(job_info)
                print(f"Successfully scraped: {job_title}")
                
                # Close current tab and switch back to main window
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
                time.sleep(2)
                
            except Exception as e:
                print(f"Error processing job card: {e}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                continue
        
        # Save the data to JSON file
        with open('ather_jobs.json', 'w', encoding='utf-8') as f:
            json.dump(job_data, f, indent=4, ensure_ascii=False)
            
        print(f"Successfully scraped {len(job_data)} jobs")
        
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        driver.quit()

if __name__ == "__main__":
    scrape_ather_jobs()
