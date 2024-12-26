import sys
sys.path.append('E:/JOB.ai/JOB.ai')  # Use forward slashes for path
from genrativeai.response_llama import parse_job_data_llama, parse_job_data_gemini  # Note: genrative not generative

import json
from dotenv import load_dotenv
import os
import pandas as pd  # Import pandas for Excel file creation

load_dotenv()
API = os.getenv('GROQ_API_KEY')


cuevete = r"E:\JOB.ai\JOB.ai\cuvete\finale_jobs.csv"

# Convert CSV to JSON
csv_file_path = cuevete  # Path to the CSV file
json_file_path = r"E:\JOB.ai\JOB.ai\cuvete\finale_jobs.json"  # Specify the output JSON file path

# Read the CSV file
try:
    df = pd.read_csv(cuevete)  # Load the CSV data into a DataFrame
    job_data_from_csv = df.to_dict(orient='records') # Convert DataFrame to JSON
    job_data=(job_data_from_csv)
    print(f"Successfully converted {csv_file_path} to {json_file_path}.")
except FileNotFoundError:
    print(f"Error: The file {csv_file_path} was not found.")
except pd.errors.EmptyDataError:
    print(f"Error: The file {csv_file_path} is empty.")
except Exception as e:
    print(f"An error occurred: {e}") 


output_data = []  
for job in job_data:
    json1_llama = parse_job_data_llama(job,API)  # Parse with llama
    output_data.append(json1_llama)

output_file = "cuevete_parsed_jobs.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=4, ensure_ascii=False)

print(f"Data has been saved to {output_file}")
