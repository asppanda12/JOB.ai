import sys
sys.path.append('E:/JOB.ai/JOB.ai')  # Use forward slashes for path
from genrativeai.response_llama import parse_job_data_llama, parse_job_data_gemini  # Note: genrative not generative

import json
from dotenv import load_dotenv
import os
import pandas as pd  # Import pandas for Excel file creation

load_dotenv()
API = os.getenv('GROQ_API_KEY')

linkedin = r"E:\JOB.ai\JOB.ai\Linkedin\Google_Software Engineer_India_linkedin_jobs.json"

# Read and parse the JSON file
try:
    with open(linkedin, 'r') as file:
        job_data = json.load(file)  # Load the JSON data
except json.JSONDecodeError:
    print(f"Error: The file {linkedin} is not a valid JSON file or is empty.")
    job_data = []  # Set job_data to an empty list to avoid further errors
except FileNotFoundError:
    print(f"Error: The file {linkedin} was not found.")
    job_data = []  # Set job_data to an empty list to avoid further errors

output_data = []  # Change to list instead of dict
for job in job_data:
    json1_llama = parse_job_data_llama(job,API)  # Parse with llama
    output_data.append(json1_llama)

# Write to JSON file
output_file = "linkedin_parsed_jobs.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=4, ensure_ascii=False)

print(f"Data has been saved to {output_file}")
