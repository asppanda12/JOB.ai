import re
import logging
import json
import pandas as pd
import time
import os
from datetime import datetime

def clean_company_name(text, company_name):
    # Remove everything after '\n' (newline)
    cleaned_name = company_name
    # Replace special characters with a space, including punctuation and brackets
    cleaned_name = re.sub(r'[^a-zA-Z0-9\s]', ' ', cleaned_name)

    # Replace multiple spaces with a single space
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
    return cleaned_name
def extract_yoe(experience_str):
    patterns = [
    (r"(\d+)-(\d+) (Years|years|Yrs)", lambda m: (int(m.group(1)), int(m.group(2)))),  # Range of years
    (r"(\d+\.\d+) to (\d+\.\d+) (Years|years|Yrs)", lambda m: (float(m.group(1)), float(m.group(2)))),  # Decimal range
    (r"(\d+)\+ (Years|years|Yrs)", lambda m: (int(m.group(1)), float('inf'))),  # Plus range
    (r"less than (\d+) (Years|year|years|Yrs)", lambda m: (0, int(m.group(1)))),  # Less than range
    (r"greater than (\d+) (Years|years|Yrs)", lambda m: (int(m.group(1)), float('inf'))),  # Greater than range
    (r"(\d+) to (\d+) (Years|years|Yrs)", lambda m: (int(m.group(1)), int(m.group(2)))),  # "to" range for integers
    (r"(\d+\.\d+) to (\d+\.\d+) (Years|years|Yrs)", lambda m: (float(m.group(1)), float(m.group(2)))),  # "to" range for decimals
    (r"(\d+)-(\d+) (Years|Yrs|years)", lambda m: (int(m.group(1)), int(m.group(2)))),  # Format with "Yrs"
    (r"(\d+) (Years|years|Yrs)", lambda m: (int(m.group(1)), int(m.group(1))))  # Single number experience
]

    
    for pattern, func in patterns:
        match = re.search(pattern, experience_str)
        if match:
            return func(match)
    
    return None  # If no match is found
def rename_key(data, old_key, new_key):
    if old_key in data:
        data[new_key] = data.pop(old_key)
    return data

# Setup logging
logging.basicConfig(filename=r'E:\JOB.ai\JOB.ai\log_data\clean_cuvete.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# List of file paths to process
lst = [
    "E:/JOB.ai/JOB.ai/result_of_all_web_scraper/instahyre_jobs_1.json",
    "E:/JOB.ai/JOB.ai/result_of_all_web_scraper/instahyre_jobs_2.json",
    "E:/JOB.ai/JOB.ai/result_of_all_web_scraper/instahyre_jobs_3.json",
    "E:/JOB.ai/JOB.ai/result_of_all_web_scraper/instahyre_jobs.json"
]

# Function to process each file
def process_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            job_data = json.load(file)  # Load the JSON data
            print(f"Processing file: {file_path} | Total jobs: {len(job_data)}")
    except json.JSONDecodeError:
        print(f"Error: The file {file_path} is not a valid JSON file or is empty.")
        job_data = []  # Set job_data to an empty list to avoid further errors
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        job_data = []  # Set job_data to an empty list to avoid further errors
    except UnicodeDecodeError:
        print(f"Error: Unable to read the file {file_path} due to encoding issues. Ensure it's saved in UTF-8.")
        job_data = []

    unique_data = job_data

    # Renaming keys
    for job in unique_data:
        job = rename_key(job, 'Job Title', 'job_title')
        job = rename_key(job, 'Company Name', 'company_name')
        job = rename_key(job, 'Job Link', 'job_link')
        job = rename_key(job, 'Location', 'location')
        job = rename_key(job, 'Experience', 'experience')
        job = rename_key(job, 'Job Description', 'job_description')
        job = rename_key(job, 'Skills', 'skills')

    # Clean and add additional fields
    start_time = time.time()
    for job in unique_data[:]:  # Iterate over a copy of the list to modify it while looping
        if "job_description" in job:
            job['job_title'] = clean_company_name("job_title", job['job_title'])
            job['location'] = clean_company_name("location", job['location'])
            job['company_name'] = clean_company_name("company_name", job['company_name'])
            job['job_description'] = clean_company_name("job_description", job['job_description'])
            job['skills']=(" ").join(job['skills'])
            job['id'] = f"{job['job_title']} {job['company_name']} {job['experience']} {job['location']}"
            job['text'] = f"{job['job_title']} {job['company_name']} {job['skills']} {job['location']}"
            job['Posted_date'] = datetime.now().strftime('%Y-%m-%d')
            job['Source']='instahyre'
            job['yoe']=extract_yoe(job['experience'])
        else:
            unique_data.remove(job)  # Remove job if "job_description" is not present

    end_time = time.time()
    execution_time = end_time - start_time
    logging.info(f"Data processing completed for {file_path}. Total time taken: {execution_time:.2f} seconds.")

    # Save cleaned data
    output_file = f"E:/JOB.ai/JOB.ai/cleaned/{os.path.basename(file_path)}"
    # Ensure the directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(unique_data, f, indent=4, ensure_ascii=False)

    print(f"Data has been saved to {output_file}")

    # Optionally, use pandas to drop duplicates
    df = pd.DataFrame(unique_data)
    print(df.count())
    df.drop_duplicates(inplace=True)
    print(df.count())
    unique_data = df.to_dict(orient='records')

    # Save the updated data
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(unique_data, f, indent=4, ensure_ascii=False)
    print(f"Duplicates removed and data saved to {output_file}")

# Process all files in the list
for file_path in lst:
    process_file(file_path)
