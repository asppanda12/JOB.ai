from response_llama import parse_job_data_llama,parse_job_data_gemini  # Since both files are in same directory

import json
from dotenv import load_dotenv
import os
import pandas as pd  # Import pandas for Excel file creation

load_dotenv()
API = os.getenv('GROQ_API_KEY')

naukri = r"E:\JOB.ai\JOB.ai\naukri\naukri_job_listings.json"
linkedin = r"E:\JOB.ai\JOB.ai\Linkedin\Google_Software Engineer_India_linkedin_jobs.json"
cuevete = r"E:\JOB.ai\JOB.ai\cuvete\finale_jobs.csv"

# Read and parse the JSON file
try:
    with open(linkedin, 'r') as file:
        job_data = json.load(file)  # Load the JSON data
except json.JSONDecodeError:
    print(f"Error: The file {naukri} is not a valid JSON file or is empty.")
    job_data = []  # Set job_data to an empty list to avoid further errors
except FileNotFoundError:
    print(f"Error: The file {naukri} was not found.")
    job_data = []  # Set job_data to an empty list to avoid further errors

jobs = []
llama_data = []
gemini_data = []

for job in job_data:
    json1_llama = parse_job_data_llama(job,API)  # Parse with llama
    json1_gemini = parse_job_data_gemini(job,API)  # Parse with gemini
    jobs.append(job)  # Assuming job is a string or can be represented as such
    llama_data.append(json1_llama)
    gemini_data.append(json1_gemini)

df = pd.DataFrame({
    'Job': jobs,
    'LLAMA': llama_data,
    'Gemini': gemini_data
})


df.to_csv('job_data_linkedin.csv', index=False) 

# # Convert CSV to JSON
# csv_file_path = cuevete  # Path to the CSV file
# json_file_path = r"E:\JOB.ai\JOB.ai\cuvete\finale_jobs.json"  # Specify the output JSON file path

# # Read the CSV file
# try:
#     df = pd.read_csv(cuevete)  # Load the CSV data into a DataFrame
#     job_data_from_csv = df.to_dict(orient='records') # Convert DataFrame to JSON
#     job_data=(job_data_from_csv)
#     print(f"Successfully converted {csv_file_path} to {json_file_path}.")
# except FileNotFoundError:
#     print(f"Error: The file {csv_file_path} was not found.")
# except pd.errors.EmptyDataError:
#     print(f"Error: The file {csv_file_path} is empty.")
# except Exception as e:
#     print(f"An error occurred: {e}") 

# jobs = []
# llama_data = []
# gemini_data = []

# for job in job_data:
#     json1_llama = parse_job_data_llama(job,API)  # Parse with llama
#     json1_gemini = parse_job_data_gemini(job,API)  # Parse with gemini
#     jobs.append(job)  # Assuming job is a string or can be represented as such
#     llama_data.append(json1_llama)
#     gemini_data.append(json1_gemini)

# df = pd.DataFrame({
#     'Job': jobs,
#     'LLAMA': llama_data,
#     'Gemini': gemini_data
# })


# df.to_csv('job_data.csv', index=False) 

