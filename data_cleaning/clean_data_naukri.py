import re
import logging
import json
import pandas as pd
import time
import os
from datetime import datetime
def clean_company_name(text, company_name):
    # Remove everything after '\n'
    if text == 'company_name':
        cleaned_name = company_name.split('\n')[0]
    else:
        cleaned_name = company_name
    # Replace special characters with a space
    cleaned_name = re.sub(r'[^a-zA-Z0-9]', ' ', cleaned_name)
    # Remove extra spaces
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
    return cleaned_name

def rename_key(data, old_key, new_key):
    if old_key in data:
        data[new_key] = data.pop(old_key)
    return data
def extract_yoe(experience_str):
    patterns = [
    (r"(\d+)-(\d+) (years|Yrs)", lambda m: (int(m.group(1)), int(m.group(2)))),  # Range of years
    (r"(\d+\.\d+) to (\d+\.\d+) (years|Yrs)", lambda m: (float(m.group(1)), float(m.group(2)))),  # Decimal range
    (r"(\d+)\+ (years|Yrs)", lambda m: (int(m.group(1)), float('inf'))),  # Plus range
    (r"less than (\d+) (year|years|Yrs)", lambda m: (0, int(m.group(1)))),  # Less than range
    (r"greater than (\d+) (years|Yrs)", lambda m: (int(m.group(1)), float('inf'))),  # Greater than range
    (r"(\d+) to (\d+) (years|Yrs)", lambda m: (int(m.group(1)), int(m.group(2)))),  # "to" range for integers
    (r"(\d+\.\d+) to (\d+\.\d+) (years|Yrs)", lambda m: (float(m.group(1)), float(m.group(2)))),  # "to" range for decimals
    (r"(\d+)-(\d+) (Yrs|years)", lambda m: (int(m.group(1)), int(m.group(2)))),  # Format with "Yrs"
    (r"(\d+) (years|Yrs)", lambda m: (int(m.group(1)), int(m.group(1))))  # Single number experience
]

    
    for pattern, func in patterns:
        match = re.search(pattern, experience_str)
        if match:
            return func(match)
    
    return None  # If no match is found

logging.basicConfig(filename=r'E:\JOB.ai\JOB.ai\log_data\clean_naukridata.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
naukri = r"E:\JOB.ai\JOB.ai\naukri\naukri_job_listings.json"

try:
    with open(naukri, 'r', encoding='utf-8') as file:
        job_data = json.load(file)  # Load the JSON data
except json.JSONDecodeError:
    print(f"Error: The file {naukri} is not a valid JSON file or is empty.")
    job_data = []  # Set job_data to an empty list to avoid further errors
except FileNotFoundError:
    print(f"Error: The file {naukri} was not found.")
    job_data = []  # Set job_data to an empty list to avoid further errors
except UnicodeDecodeError:
    print(f"Error: Unable to read the file {naukri} due to encoding issues. Ensure it's saved in UTF-8.")
    job_data = []

if 'job_listings' in job_data:
    print(len(job_data['job_listings']))
    for job in job_data["job_listings"]:
        if "Skills" in job and isinstance(job["Skills"], list):
            job["Skills"] = tuple(job["Skills"])

    unique_data = [dict(t) for t in {tuple(d.items()) for d in job_data['job_listings']}]

    # Renaming keys
    for job in unique_data:
        job = rename_key(job, 'Job Title', 'job_title')
        job = rename_key(job, 'Company Name', 'company_name')
        job = rename_key(job, 'Job Link', 'job_link')
        job = rename_key(job, 'Location', 'location')
        job = rename_key(job, 'Experience', 'experience')
        job = rename_key(job, 'Job Description', 'job_description')
        job = rename_key(job, 'Skills', 'skills')
    print(unique_data[0])
    # Clean and add additional fields
    start_time = time.time()
    for job in unique_data:
        job['job_title'] = clean_company_name("job_title", job['job_title'])
        job['company_name'] = clean_company_name("company_name", job['company_name'])
        job['job_description'] = clean_company_name("job_description", job['job_description'])
        job['skills'] = " ".join(job['skills'])
        job['id'] = f"{job['job_title']} {job['company_name']} {job['experience']} {job['location']}"
        job['text'] = f"{job['job_title']} {job['company_name']} {job['job_description']} {job['location']}"
        job['Posted_date']=datetime.now().strftime('%Y-%m-%d')
        job['Source']='naukri'
        job['yoe']=extract_yoe(job['experience'])
    end_time = time.time()
    execution_time = end_time - start_time
    logging.info(f"Data processing completed. Total time taken: {execution_time:.2f} seconds.")

    output_file = "E:/JOB.ai/JOB.ai/cleaned/naukri.json"
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
    print("Duplicates removed and data saved.")
else:
    print("No 'job_listings' found.")
