from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import os
import time

def scrape_instahyre_jobs():
    driver = webdriver.Chrome()
    job_data = []
    current_page = 1
    
    try:
        # Navigate to the initial page
        url = "https://www.instahyre.com/search-jobs?companies=Zeta,PhonePe,Zomato,Tiger+Analytics,Porter,Zepto,Shiprocket,PhysicsWallah,Purplle,Xpressbees,Darwinbox,Livspace.com,Yubi,Arcesium,Codenatives&company_size=0&isLandingPage=true&job_functions=%2Fapi%2Fv1%2Fjob_category%2F1,%2Fapi%2Fv1%2Fjob_function%2F10,%2Fapi%2Fv1%2Fjob_function%2F17&job_type=0&offset=0&search=true"
        driver.get(url)
        time.sleep(5)
        
        while True:
            print(f"Processing page {current_page}")
            
            # Process jobs on current page
            try:
                job_container = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, '//*[@id="job-function-page"]/div[2]/div/div[1]/div[1]'))
                )
                
                # Find all job blocks
                job_blocks = job_container.find_elements(By.CLASS_NAME, "employer-block")
                
                if not job_blocks:
                    print("No job blocks found on this page")
                    break
                
                # Process each job on the page
                for job_block in job_blocks:
                    try:
                        # Get job link and position
                        job_link = job_block.find_element(By.ID, "employer-profile-opportunity").get_attribute("href")
                        position = job_block.find_element(By.CLASS_NAME, "company-name").text
                        
                        # Open job in new tab
                        driver.execute_script(f"window.open('{job_link}', '_blank')")
                        time.sleep(2)
                        driver.switch_to.window(driver.window_handles[-1])
                        time.sleep(3)
                        
                        try:
                            # Extract job details
                            job_title = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.TAG_NAME, "h1"))
                            ).text
                            
                            company_name = driver.find_element(By.CLASS_NAME, "company-name").text
                            
                            # Extract location and experience
                            job_locations_div = driver.find_element(By.CLASS_NAME, "job-locations")
                            location = job_locations_div.find_element(By.XPATH, ".//span[1]").text.replace("", "").strip()
                            experience = job_locations_div.find_element(By.CLASS_NAME, "experience").text.replace("", "").strip()
                            
                            # Extract job description
                            job_desc = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.CLASS_NAME, "job-description"))
                            ).text.strip()
                            
                            # Extract skills if available
                            skills = []
                            try:
                                skills_container = driver.find_element(By.CLASS_NAME, "skills-container")
                                skills = [skill.text for skill in skills_container.find_elements(By.TAG_NAME, "li")]
                            except:
                                pass
                            
                            # Create job info dictionary
                            job_info = {
                                'job_title': job_title,
                                'company_name': company_name,
                                'job_link': job_link,
                                'location': location,
                                'experience': experience,
                                'job_description': job_desc,
                                'skills': skills
                            }
                            
                            job_data.append(job_info)
                            print(f"Successfully scraped: {job_title} at {company_name}")
                            
                        except Exception as e:
                            print(f"Error extracting job details: {e}")
                        
                        # Close current tab and switch back to main window
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                        time.sleep(2)
                        
                    except Exception as e:
                        print(f"Error processing job block: {e}")
                        if len(driver.window_handles) > 1:
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                        continue
                
                # After processing all jobs on current page, navigate to next page
                try:
                    # Wait for pagination to be present
                    pagination = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "pagination"))
                    )
                    
                    # Find all page numbers
                    page_numbers = pagination.find_elements(By.XPATH, ".//li[contains(@class, 'ng-binding')]")
                    max_page = max([int(page.text) for page in page_numbers if page.text.isdigit()])
                    
                    if current_page >= max_page:
                        print(f"Reached last page ({max_page})")
                        break
                    
                    # Click the next page number
                    next_page_number = str(current_page + 1)
                    next_page_element = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, f"//li[contains(@class, 'ng-binding') and text()='{next_page_number}']"))
                    )
                    driver.execute_script("arguments[0].click();", next_page_element)
                    
                    current_page += 1
                    print(f"Clicked and moving to page {current_page}")
                    time.sleep(5)  # Wait for new page to load
                    
                except Exception as e:
                    print(f"Error navigating to next page: {e}")
                    break
                
            except Exception as e:
                print(f"Error processing page: {e}")
                break
        
        # Save the data
        file_path = r"E:\JOB.ai\JOB.ai\result_of_all_web_scraper\instahyre_jobs_1.json"
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(job_data, f, indent=4, ensure_ascii=False)
            
        print(f"Successfully scraped {len(job_data)} jobs and saved to {file_path}")
        
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        driver.quit()

if __name__ == "__main__":
    scrape_instahyre_jobs()
