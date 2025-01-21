import sys
sys.path.append('E:/JOB.ai/JOB.ai')  # Use forward slashes for path
# from genrativeai.response_llama import parse_job_data_llama, parse_job_data_gemini  # Note: genrative not generative
from genrativeai.response_llama import parse_job_data_llama
import time
import json
from dotenv import load_dotenv
import os
import pandas as pd  # Import pandas for Excel file creation
import logging

load_dotenv()
API = os.getenv('GROQ_API_KEY')


cuevete = r"E:\JOB.ai\JOB.ai\cuvete\finale_jobs.csv"
logging.basicConfig(filename=r'E:\JOB.ai\JOB.ai\log_data\create_data_cuvete.log', level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')


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
# for job in job_data:
#     json1_llama = parse_job_data_llama(job,API)  # Parse with llama
#     output_data.append(json1_llama)

# output_file = "cuevete_parsed_jobs.json"
# with open(output_file, 'w', encoding='utf-8') as f:
#     json.dump(output_data, f, indent=4, ensure_ascii=False)

# print(f"Data has been saved to {output_file}")
output_data = []  # Change to list instead of dict
# job_data=job_data[0:50]
start_time = time.time()
for idx, job in enumerate(job_data, start=1):
    json1_llama = parse_job_data_llama(job,API)  # Parse with llama
    output_data.append(json1_llama)
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
output_file = "E:/JOB.ai/JOB.ai/result_of_all_web_scraper/cuvette.json"
# Ensure the directory exists
os.makedirs(os.path.dirname(output_file), exist_ok=True)
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=4, ensure_ascii=False)

print(f"Data has been saved to {output_file}")
