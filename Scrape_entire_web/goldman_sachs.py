from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import time
import os

def get_section_text(driver, section_titles):
    combined_text = []
    
    for title in section_titles:
        try:
            # Try to find section with exact title
            section = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((
                    By.XPATH, 
                    f"//div[contains(translate(text(), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{title}')]//following-sibling::div"
                ))
            )
            section_text = section.text.strip()
            if section_text:
                combined_text.append(section_text)
        except:
            continue
    
    return '\n\n'.join(combined_text) if combined_text else "Not available"

def scrape_goldman_jobs():
    driver = webdriver.Chrome()
    job_data = []
    page = 1
    has_next_page = True
    
    try:
        while has_next_page:
            # Navigate to the page
            url = f"https://higher.gs.com/results?JOB_FUNCTION=Data%20Analytics|Data%20Engineering|Product%20Engineering|Software%20Engineering|Systems%20Engineering|UI%20Engineering&page={page}&sort=RELEVANCE"
            driver.get(url)
            time.sleep(5)  # Wait for page load
            
            # Wait for job listings container
            jobs_container = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/main/div/div[2]/div/div/div/div[2]/div/div[2]/div/div/div[2]'))
            )
            
            # Find all job listings
            job_listings = jobs_container.find_elements(By.CLASS_NAME, 'border-bottom')
            
            if not job_listings:
                has_next_page = False
                continue
                
            for job in job_listings:
                try:
                    # Extract basic job information
                    job_link_element = job.find_element(By.TAG_NAME, 'a')
                    job_link = job_link_element.get_attribute('href')
                    job_title = job.find_element(By.CLASS_NAME, 'gs-uitk-c-nv7fiq--text-root').text
                    
                    # Extract location
                    location_element = job.find_element(By.XPATH, './/div[@data-testid="location"]')
                    location = location_element.text
                    
                    # Check if it's a software engineering role
                    try:
                        job_type = job.find_element(By.CLASS_NAME, 'gs-tag__button').text
                    except:
                        job_type = "Not specified"
                    
                    # Open job in new tab
                    driver.execute_script(f"window.open('{job_link}', '_blank')")
                    time.sleep(2)
                    driver.switch_to.window(driver.window_handles[-1])
                    time.sleep(3)
                    
                    # Define possible section titles
                    skills_sections = [
                        'SKILLS AND EXPERIENCE',
                        'EXPERIENCE/SKILLS',
                        'SKILLS AND EXPERIENCE WE ARE LOOKING FOR',
                        'PREFERRED QUALIFICATIONS',
                        'BASIC QUALIFICATIONS',
                        'QUALIFICATIONS',
                        'TECHNOLOGIES',
                        'REQUIRED QUALIFICATIONS',
                        'QUALIFICATIONS, SKILLS & APTITUDE',
                        'TECHNICAL SKILLS & QUALIFICATIONS',
                        'SKLLS AND EXPERIENCE WE ARE LOOKING FOR'
                    ]
                    
                    # Get combined text from all relevant sections
                    desc2 = get_section_text(driver, skills_sections)
                    
                    # Get responsibilities section if it exists
                    responsibilities_sections = [
                        'RESPONSIBILITIES AND QUALIFICATIONS',
                        'RESPONSIBILITIES',
                        'JOB RESPONSIBILITIES',
                        'KEY RESPONSIBILITIES',
                        'WHAT YOU WILL DO'
                    ]
                    
                    desc1 = get_section_text(driver, responsibilities_sections)
                    
                    # Create job info dictionary
                    job_info = {
                        'job_title': job_title,
                        'job_link': job_link,
                        'location': location,
                        'job_type': job_type,
                        'responsibilities': desc1,
                        'technical_skills': desc2
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
            
            # Check for next page
            try:
                next_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Next')]")
                if not next_button.is_enabled():
                    has_next_page = False
                else:
                    page += 1
            except:
                has_next_page = False
        
        # Define the file path
        file_path = r"E:\JOB.ai\JOB.ai\result_of_all_web_scraper\goldman_sachs.json"
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        try:
            # Save the data to JSON file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(job_data, f, indent=4, ensure_ascii=False)
            
            print(f"Successfully saved {len(job_data)} jobs to {file_path}")
            
        except Exception as e:
            print(f"Error saving data to file: {e}")
            print(f"Current working directory: {os.getcwd()}")
        
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        driver.quit()

if __name__ == "__main__":
    scrape_goldman_jobs() 