
import os
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def setup_driver():
    """Set up the Selenium WebDriver."""
    return webdriver.Chrome()  # Replace with appropriate driver for your browser


def save_to_json(data, file_path):
    """Save job data to a JSON file."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, indent=4, ensure_ascii=False)


def apply_filters(driver):
    """Apply filters to the job listing."""
    dropdown = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "button-basic"))
    )
    dropdown.click()

    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.XPATH, "//div[@class='dropdown-menu show']"))
    )
    driver.find_element(By.XPATH, "//label[contains(text(), 'Data Science')]").click()
    driver.find_element(By.XPATH, "//label[contains(text(), 'Technology -  Jify')]").click()

    search_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'db-btn') and contains(@class, 'jobs-btn')]"))
    )
    search_button.click()


def extract_job_details(job_row):
    """Extract details from a single job row."""
    job_title = job_row.find_element(By.CSS_SELECTOR, "td[data-th='Job title'] a").text.strip()
    department = job_row.find_element(By.CSS_SELECTOR, "td[data-th='department'] span.tooltip-custom").text.strip()
    location = job_row.find_element(By.CSS_SELECTOR, "td[data-th='Location'] span.tooltip-custom").text.strip()
    emp_type = job_row.find_element(By.CSS_SELECTOR, "td[data-th='emp_type'] span.tooltip-custom").text.strip()
    job_posted_on = job_row.find_element(By.CSS_SELECTOR, "td[data-th='Job posted on'] span").text.strip()
    job_link = job_row.find_element(By.CSS_SELECTOR, "td[data-th='Job title'] a").get_attribute('href')
    return {
        'job_title': job_title,
        'department': department,
        'location': location,
        'emp_type': emp_type,
        'job_posted_on': job_posted_on,
        'job_link': job_link,
    }


def extract_additional_details(driver):
    """Extract additional details (experience range and job description) from the job page."""
    try:
        experience_range = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'experience-range')]//p[contains(@class, 'smaller-header-bold')]"))
        ).text.strip()
    except:
        experience_range = "Not specified"

    try:
        job_description = []
        job_summary = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "job-summary"))
        )
        paragraphs = job_summary.find_elements(By.TAG_NAME, "p")
        mandate_skills_found = False

        for p in paragraphs:
            text = p.text.strip()
            if "Job Description" in text and "Mandate Skills" in text:
                mandate_skills_found = True
                continue
            if "Ideal Candidate" in text:
                mandate_skills_found = True
                continue
            if mandate_skills_found and "Responsibilities:" in text:
                break
            if mandate_skills_found and text:
                job_description.append(text)

        job_description = '\n'.join(job_description) if job_description else "Not available"
    except:
        job_description = "Not available"

    return {
        'experience_range': experience_range,
        'job_description': job_description,
    }


def process_job_rows(driver, job_rows):
    """Process all job rows and extract job details."""
    job_data = []
    for job_row in job_rows:
        try:
            # Extract basic job details
            job_details = extract_job_details(job_row)

            # Open job link in a new tab
            driver.execute_script(f"window.open('{job_details['job_link']}', '_blank')")
            time.sleep(5)
            driver.switch_to.window(driver.window_handles[-1])
            time.sleep(5)

            # Extract additional job details
            additional_details = extract_additional_details(driver)
            job_details.update(additional_details)

            # Add job details to the list
            job_data.append(job_details)

            # Close the current tab and switch back to the main tab
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        except Exception as e:
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
            continue
    return job_data


def main():
    url = "https://moneyview.darwinbox.in/ms/candidate/careers"
    file_path = r"E:\JOB.ai\JOB.ai\result_of_all_web_scraper\money_view_data.json"
    
    driver = setup_driver()
    driver.get(url)

    try:
        apply_filters(driver)

        # Wait for the job results to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "/html/body/app-root/div/app-user-views/div[2]/app-jobs-wrapper/app-jobs/div/div[3]/div/div[3]/app-jobs-list/app-custom-table/table"))
        )

        # Locate and process job rows
        table = driver.find_element(By.XPATH, "/html/body/app-root/div/app-user-views/div[2]/app-jobs-wrapper/app-jobs/div/div[3]/div/div[3]/app-jobs-list/app-custom-table/table")
        tbody = table.find_element(By.TAG_NAME, "tbody")
        job_rows = tbody.find_elements(By.TAG_NAME, "tr")
        job_data = process_job_rows(driver, job_rows)

        # Save the extracted data to a JSON file
        save_to_json(job_data, file_path)
    except Exception as e:
        print(f"Error encountered: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()


# import requests
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# import json
# import os
# from bs4 import BeautifulSoup
# import time
# import re
# # Set up the Selenium WebDriver (make sure to specify the correct path to your driver)
# driver = webdriver.Chrome()  # or webdriver.Firefox() for Firefox

# # Open the URL
# url = "https://moneyview.darwinbox.in/ms/candidate/careers"
# driver.get(url)

# job_data = []  # List to hold job details

# # Define the file path
# file_path = r"E:\JOB.ai\JOB.ai\result_of_all_web_scraper\money_view_data.json"

# # Ensure directory exists
# os.makedirs(os.path.dirname(file_path), exist_ok=True)

# try:
#     # Wait for the dropdown to be clickable and click it
#     dropdown = WebDriverWait(driver, 10).until(
#         EC.element_to_be_clickable((By.ID, "button-basic"))  # Adjust the selector as needed
#     )
#     dropdown.click()

#     # Wait for the dropdown options to be visible
#     WebDriverWait(driver, 10).until(
#         EC.visibility_of_element_located((By.XPATH, "//div[@class='dropdown-menu show']"))
#     )

#     # Select "Data Science"
#     data_science_option = driver.find_element(By.XPATH, "//label[contains(text(), 'Data Science')]")
#     data_science_option.click()

#     # Select "Technology - Jify"
#     technology_option = driver.find_element(By.XPATH, "//label[contains(text(), 'Technology -  Jify')]")
#     technology_option.click()

#     # Click the search button
#     search_button = WebDriverWait(driver, 10).until(
#         EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'db-btn') and contains(@class, 'jobs-btn')]"))
#     )
#     search_button.click()

#     # Wait for the job results to load
#     WebDriverWait(driver, 10).until(
#         EC.presence_of_element_located((By.XPATH, "/html/body/app-root/div/app-user-views/div[2]/app-jobs-wrapper/app-jobs/div/div[3]/div/div[3]/app-jobs-list/app-custom-table/table"))  # Wait for the table to be present
#     )

#     # Locate the table using the provided XPath
#     table = driver.find_element(By.XPATH, "/html/body/app-root/div/app-user-views/div[2]/app-jobs-wrapper/app-jobs/div/div[3]/div/div[3]/app-jobs-list/app-custom-table/table")

#     # Locate the tbody within the table
#     tbody = table.find_element(By.TAG_NAME, "tbody")

#     # Extract all rows from the tbody
#     job_rows = tbody.find_elements(By.TAG_NAME, "tr")  # Get all job rows

#     for job_row in job_rows:
#         try:
#             # Wait and get job title
#             job_title_element = WebDriverWait(job_row, 2).until(
#                 EC.presence_of_element_located((By.CSS_SELECTOR, "td[data-th='Job title'] a"))
#             )
#             job_title = job_title_element.text.strip()

#             # Wait and get department
#             department_element = WebDriverWait(job_row, 2).until(
#                 EC.presence_of_element_located((By.CSS_SELECTOR, "td[data-th='department'] span.tooltip-custom"))
#             )
#             department = department_element.text.strip()

#             # Wait and get location
#             location_element = WebDriverWait(job_row, 2).until(
#                 EC.presence_of_element_located((By.CSS_SELECTOR, "td[data-th='Location'] span.tooltip-custom"))
#             )
#             location = location_element.text.strip()

#             # Wait and get employment type
#             emp_type_element = WebDriverWait(job_row, 2).until(
#                 EC.presence_of_element_located((By.CSS_SELECTOR, "td[data-th='emp_type'] span.tooltip-custom"))
#             )
#             emp_type = emp_type_element.text.strip()

#             # Wait and get posting date
#             job_posted_element = WebDriverWait(job_row, 2).until(
#                 EC.presence_of_element_located((By.CSS_SELECTOR, "td[data-th='Job posted on'] span"))
#             )
#             job_posted_on = job_posted_element.text.strip()

#             # Get the job link
#             job_link = job_title_element.get_attribute('href')
#             print(job_link)
#             # Open new tab with the job link
#             time.sleep(20)
#             driver.execute_script(f"window.open('{job_link}', '_blank')")
#             time.sleep(15)  # Wait for new tab to open
            
#             # Switch to the new tab
#             driver.switch_to.window(driver.window_handles[-1])
#             time.sleep(15)  # Wait for page to load
            
#             try:
#                 # Find Experience Range
#                 experience_range = "Not specified"
#                 exp_element = WebDriverWait(driver, 10).until(
#                     EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'experience-range')]//p[contains(@class, 'smaller-header-bold')]"))
#                 )
#                 if exp_element:
#                     experience_range = exp_element.text.strip()
                
#             except Exception as e:
#                 print(f"Error extracting experience range: {e}")
#                 experience_range = "Not specified"

#             try:
#                 # Find Job Description
#                 job_description = []
#                 job_summary = WebDriverWait(driver, 10).until(
#                     EC.presence_of_element_located((By.CLASS_NAME, "job-summary"))
#                 )
            
#                 if job_summary:
#                     paragraphs = job_summary.find_elements(By.TAG_NAME, "p")
#                     mandate_skills_found = False
                    
#                     for p in paragraphs:
#                         text = p.text.strip()
                        
#                         # Start collecting after finding "Job Description: (Mandate Skills)"
#                         if "Job Description" in text and "Mandate Skills" in text:
#                             mandate_skills_found = True
#                             continue
#                         if "Ideal Candidate" in text:
#                             mandate_skills_found = True
#                             continue
#                         # Stop collecting when we hit "Responsibilities"
#                         if mandate_skills_found and "Responsibilities:" in text:
#                             break
                        
#                         # Collect text between Mandate Skills and Responsibilities
#                         if mandate_skills_found and text:
#                             job_description.append(text)
                
#                 job_description = '\n'.join(job_description) if job_description else "Not available"
                
#             except Exception as e:
#                 print(f"Error extracting job description: {e}")
#                 job_description = "Not available"

#             # Create a job dictionary with additional information
#             job_info = {
#                 'job_title': job_title,
#                 'job_link': job_link,
#                 'department': department,
#                 'location': location,
#                 'emp_type': emp_type,
#                 'job_posted_on': job_posted_on,
#                 'job_description': job_description,
#                 'experience_range': experience_range
#             }

#             print(f"Successfully extracted job: {job_title}")
#             print(f"Experience Range: {experience_range}")
#             print(f"Job Description Length: {len(job_description)}")
#             job_data.append(job_info)

#             # Close the current tab and switch back to the main tab
#             driver.close()
#             driver.switch_to.window(driver.window_handles[0])

#         except Exception as e:
#             print(f"Error processing row: {e}")
#             # Make sure to close the tab and switch back if there's an error
#             if len(driver.window_handles) > 1:
#                 driver.close()
#                 driver.switch_to.window(driver.window_handles[0])
#             continue

# except Exception as e:
#     print(f"Error: {e}")

# # Save the data
# try:
#     print(f"Attempting to save to: {file_path}")
#     with open(file_path, 'w', encoding='utf-8') as json_file:
#         json.dump(job_data, json_file, indent=4, ensure_ascii=False)
#     print(f"Data saved successfully! Total jobs saved: {len(job_data)}")
# except Exception as e:
#     print(f"Error saving data to file: {e}")

# finally:
#     # Close the driver
#     driver.quit()
