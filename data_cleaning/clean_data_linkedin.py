import re
import logging
import json
import pandas as pd
import time
import os
from datetime import datetime
def extract_yoe(experience_str):
    patterns = [
        
        (r"(\d+)\s*-\s*(\d+) (Years|years|Yrs)", lambda m: (int(m.group(1)), int(m.group(2)))),
    (r"(\d+)-(\d+) (Years|years|Yrs)", lambda m: (int(m.group(1)), int(m.group(2)))),  # Range of years
    (r"(\d+\.\d+) to (\d+\.\d+) (Years|years|Yrs)", lambda m: (float(m.group(1)), float(m.group(2)))),  # Decimal range
    (r"(\d+)\+ (Years|years|Yrs)", lambda m: (int(m.group(1)),  int(60))),  # Plus range
    (r"less than (\d+) (Years|year|years|Yrs)", lambda m: (0, int(m.group(1)))),  # Less than range
    (r"greater than (\d+) (Years|years|Yrs)", lambda m: (int(m.group(1)),  int(60))),  # Greater than range
    (r"(\d+) to (\d+) (Years|years|Yrs)", lambda m: (int(m.group(1)), int(m.group(2)))),  # "to" range for integers
    (r"(\d+\.\d+) to (\d+\.\d+) (Years|years|Yrs)", lambda m: (float(m.group(1)), float(m.group(2)))),  # "to" range for decimals
    (r"(\d+)-(\d+) (Years|Yrs|years)", lambda m: (int(m.group(1)), int(m.group(2)))),  # Format with "Yrs"
    (r"(\d+) (Years|years|Yrs)", lambda m: (int(m.group(1)), int(m.group(1)))),  # Single number experience
    (r"(\d+)-(\d+)", lambda m: (int(m.group(1)), int(m.group(2)))),
    (r"(\d+)", lambda m: (int(m.group(1)), int(60))),  # Handle standalone number
]

    
    for pattern, func in patterns:
        match = re.search(pattern, experience_str)
        if match:
            return func(match)
    
    return (0,60)  # If no match is found

def clean_company_name(text, company_name):
    # Remove everything after '\n' (newline)
    cleaned_name = company_name
    # Replace special characters with a space, including punctuation and brackets
    cleaned_name = re.sub(r'[^a-zA-Z0-9\s]', ' ', cleaned_name)
    # Replace multiple spaces with a single space
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
    return cleaned_name

def rename_key(data, old_key, new_key):
    if old_key in data:
        data[new_key] = data.pop(old_key)
    return data

logging.basicConfig(filename=r'E:\JOB.ai\JOB.ai\log_data\clean_linkedin.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
linkedin = r"E:\JOB.ai\JOB.ai\Linkedin\linkedin_parsed_jobs.json"

try:
    with open(linkedin, 'r', encoding='utf-8') as file:
        job_data = json.load(file)  # Load the JSON data
        print(len(job_data))
except json.JSONDecodeError:
    print(f"Error: The file {linkedin} is not a valid JSON file or is empty.")
    job_data = []  # Set job_data to an empty list to avoid further errors
except FileNotFoundError:
    print(f"Error: The file {linkedin} was not found.")
    job_data = []  # Set job_data to an empty list to avoid further errors
except UnicodeDecodeError:
    print(f"Error: Unable to read the file {linkedin} due to encoding issues. Ensure it's saved in UTF-8.")
    job_data = []

unique_data = job_data

# Renaming keys
# print(job_data[0])
for index,job in enumerate(unique_data):
    try:
        job = rename_key(job, 'Job Title', 'job_title')
        job = rename_key(job, 'Company Name', 'company_name')
        job = rename_key(job, 'Job Link', 'job_link')
        job = rename_key(job, 'Location', 'location')
        job = rename_key(job, 'Experience', 'experience')
        job = rename_key(job, 'Job Description', 'job_description')
        job = rename_key(job, 'Skills', 'skills')
    except Exception as e:  # Catch any exception
        print(f"Error processing job at index {index}: {e}")  # Print the error message
        unique_data.remove(job)  # Remove the job from unique_data

# Clean and add additional fields
start_time = time.time()
for job in unique_data[:]:  # Iterate over a copy of the list to modify it while looping
    if "job_description" in job:
        job['job_title'] = clean_company_name("job_title", job['job_title'])
        job['location'] = clean_company_name("location", job['location'])
        job['company_name'] = clean_company_name("company_name", job['company_name'])
        job['job_description'] = clean_company_name("job_description", job['job_description'])
        
        if "skills" in job:
            if isinstance(job["skills"], list):
                job["skills"] = tuple(job["skills"])  # Convert list to tuple
                job['skills'] = " ".join(job['skills'])  # Join the skills as a string
        
        job['id'] = f"{job['job_title']} {job['company_name']} {job['experience']} {job['location']}"
        job['text'] = f"{job['job_title']} {job['company_name']} {job['job_description']} {job['location']}"
        job['Posted_date'] = datetime.now().strftime('%Y-%m-%d')
        job['yoe']=extract_yoe(job['experience'])
    else:
        unique_data.remove(job)  # Remove job if "job_description" is not present

end_time = time.time()
execution_time = end_time - start_time
logging.info(f"Data processing completed. Total time taken: {execution_time:.2f} seconds.")

output_file = "E:/JOB.ai/JOB.ai/cleaned/linkedin.json"
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
