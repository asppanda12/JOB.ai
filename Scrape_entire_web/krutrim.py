from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import os
import time

def scrape_krutrim_jobs():
    driver = webdriver.Chrome()
    job_data = []
    
    try:
        # Navigate to the page
        driver.get("https://www.instahyre.com/jobs-at-krutrim/")
        time.sleep(5)  # Wait for initial load
        
        # Find the sidebar block
        sidebar = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "sidebar-block"))
        )
        
        # Find all similar job elements
        similar_jobs = sidebar.find_elements(By.CLASS_NAME, "similar-job")
        
        for job in similar_jobs:
            try:
                # Extract job link and title
                job_link_element = job.find_element(By.TAG_NAME, "a")
                job_link = "https://www.instahyre.com" + job_link_element.get_attribute("href")
                job_title = job.find_element(By.TAG_NAME, "strong").text
                
                # Open job in new tab
                driver.execute_script(f"window.open('{job_link}', '_blank')")
                time.sleep(2)
                driver.switch_to.window(driver.window_handles[-1])
                time.sleep(3)
                
                # Extract job description
                try:
                    job_desc_element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "job-description"))
                    )
                    job_description = job_desc_element.text.strip()
                except Exception as e:
                    print(f"Error extracting job description: {e}")
                    job_description = "Not available"
                
                # Extract experience
                try:
                    experience_element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "experience"))
                    )
                    experience = experience_element.text.replace("", "").strip()
                except Exception as e:
                    print(f"Error extracting experience: {e}")
                    experience = "Not specified"
                
                # Extract skills
                try:
                    skills = []
                    skills_container = driver.find_element(By.CLASS_NAME, "skills-container")
                    skill_elements = skills_container.find_elements(By.TAG_NAME, "li")
                    skills = [skill.text for skill in skill_elements]
                except Exception as e:
                    print(f"Error extracting skills: {e}")
                    skills = []
                
                # Create job info dictionary
                job_info = {
                    'job_title': job_title,
                    'job_link': job_link,
                    'job_description': job_description,
                    'experience': experience,
                    'skills': skills
                }
                
                job_data.append(job_info)
                print(f"Successfully scraped: {job_title}")
                
                # Close current tab and switch back to main window
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
                time.sleep(2)
                
            except Exception as e:
                print(f"Error processing job: {e}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                continue
        
        # Define the file path
        file_path = r"E:\JOB.ai\JOB.ai\result_of_all_web_scraper\krutrim_jobs.json"
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Save the data to JSON file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(job_data, f, indent=4, ensure_ascii=False)
            
        print(f"Successfully scraped {len(job_data)} jobs and saved to {file_path}")
        
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        driver.quit()

if __name__ == "__main__":
    scrape_krutrim_jobs() 