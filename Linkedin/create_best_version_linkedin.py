import sys
sys.path.append('E:/JOB.ai/JOB.ai')  # Use forward slashes for path
# from genrativeai.response_llama import parse_job_data_llama, parse_job_data_gemini  # Note: genrative not generative
from llama.parse_job_data_llama import parse_job_data_llama
import json
from dotenv import load_dotenv
import os
import pandas as pd  # Import pandas for Excel file creation
import time
load_dotenv()
import logging

# API = os.getenv('GROQ_API_KEY')

linkedin = r"E:\JOB.ai\JOB.ai\Linkedin\linkedin_parsed_jobs.json"
logging.basicConfig(filename=r'E:\JOB.ai\JOB.ai\log_data\create_best_version_linkedin.log', level=logging.INFO)

# Read and parse the JSON file
try:
    with open(linkedin, 'r', encoding='utf-8') as file:
        job_data = json.load(file)  # Load the JSON data
except json.JSONDecodeError:
    print(f"Error: The file {linkedin} is not a valid JSON file or is empty.")
    job_data = []  # Set job_data to an empty list to avoid further errors
except FileNotFoundError:
    print(f"Error: The file {linkedin} was not found.")
    job_data = []  # Set job_data to an empty list to avoid further errors
except UnicodeDecodeError:
    print(f"Error: Unable to read the file {linkedin} due to encoding issues. Ensure it's saved in UTF-8.")
    job_data = []

output_data = []  # Change to list instead of dict
# job_data=job_data[0:50]
start_time = time.time()
for idx, job in enumerate(job_data, start=1):
    if('Job Description'in job and 'Skills' in job):
        val = parse_job_data_llama(job['Job Description'])  # Parse with llama
        val = val.replace('\n', '').split()  # This will create a list of words
        if idx < len(job_data):
            job_data[idx]['Skills'] = val
        else:
            print(f"Index {idx} is out of range for job_data with length {len(job_data)}.")
        print(f"Job {idx} processed.")
        # Log progress
        logging.info(f"Job {idx} processed.")

end_time = time.time()

# Log total time taken
execution_time = end_time - start_time
logging.info(f"Data processing completed. Total time taken: {execution_time:.2f} seconds.")
print(f"Data processing completed. Total time taken: {execution_time:.2f} seconds.")

print()
# Write to JSON file
output_file = r"E:\JOB.ai\JOB.ai\result_of_all_web_scraper\linkedin_parsed_jobs.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(job_data, f, indent=4, ensure_ascii=False)

print(f"Data has been saved to {output_file}")
