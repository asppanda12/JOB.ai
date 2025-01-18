import sys
sys.path.append('E:/JOB.ai/JOB.ai')  # Use forward slashes for path
from genrativeai.response_llama import parse_job_data_llama, parse_job_data_gemini  # Note: genrative not generative

import json
from dotenv import load_dotenv
import os
import pandas as pd  # Import pandas for Excel file creation

# Load environment variables from .env
load_dotenv()
API = os.getenv('GROQ_API_KEY')

# Path to the LinkedIn job data JSON file
linkedin = r"E:\JOB.ai\JOB.ai\database\all_jobs.json"

# Read and parse the JSON file
try:
    with open(linkedin, 'r', encoding='utf-8') as file:  # Specify utf-8 encoding
        job_data = json.load(file)  # Load the JSON data
except json.JSONDecodeError:
    print(f"Error: The file {linkedin} is not a valid JSON file or is empty.")
    job_data = []  # Set job_data to an empty list to avoid further errors
except FileNotFoundError:
    print(f"Error: The file {linkedin} was not found.")
    job_data = []  # Set job_data to an empty list to avoid further errors
except UnicodeDecodeError as e:
    print(f"Error: Unicode decode error while reading {linkedin}: {e}")
    job_data = []  # Set job_data to an empty list to avoid further errors

# If job_data is empty, handle this scenario
if not job_data:
    print(f"Warning: No job data available in {linkedin}")
else:
    output_data = []  # List to store the parsed job data

    for job in job_data:
        try:
            json1_llama = parse_job_data_llama(job, API)  # Parse with llama
            output_data.append(json1_llama)
        except Exception as e:
            print(f"Error parsing job data: {e}")  # Log parsing errors for individual jobs

    # Write the parsed data to a new JSON file
    output_file = "parsed_jobs.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=4, ensure_ascii=False)

    print(f"Data has been saved to {output_file}")
