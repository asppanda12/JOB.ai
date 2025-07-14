import sys
sys.path.append('E:/JOB.ai/JOB.ai')  # Use forward slashes for path
from genrativeai.response_llama import parse_job_data_llama, parse_job_data_gemini  # Note: genrative not generative
from llama.query_generator import Extract_json
import json
from dotenv import load_dotenv
import os
import pandas as pd  # Import pandas for Excel file creation


linkedin = r"E:\JOB.ai\JOB.ai\Linkedin\test.json"

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
print(len(job_data))

for job in job_data:
    print("job sequence going")
    print(job)
    # json1_llama = Extract_json(job)  # Parse with llama
    # output_data.append(json1_llama)
# Write to JSON file
output_file = r"E:\JOB.ai\JOB.ai\result_of_all_web_scraper\linkedin_parsed_jobs.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=4, ensure_ascii=False)

print(f"Data has been saved to {output_file}")
