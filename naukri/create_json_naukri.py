import sys
sys.path.append('E:/JOB.ai/JOB.ai')  # Use forward slashes for path
# from genrativeai.response_llama import parse_job_data_llama, parse_job_data_gemini  # Note: genrative not generative
from llama.hugging_face_main_api import parse_job_data_llama
import json
from dotenv import load_dotenv
import os
import pandas as pd  # Import pandas for Excel file creation
import time
load_dotenv()
import logging

# API = os.getenv('GROQ_API_KEY')

naukri = r"E:\JOB.ai\JOB.ai\naukri\naukri_job_listings.json"
logging.basicConfig(filename=r'E:\JOB.ai\JOB.ai\log_data\create_data_naukri.log', level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')


# Read and parse the JSON file
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

output_data = []  # Change to list instead of dict
# job_data=job_data[0:50]
start_time = time.time()
for idx, job in enumerate(job_data['job_listings'], start=1):
    json1_llama = parse_job_data_llama(job)  # Parse with llama
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
output_file = "E:/JOB.ai/JOB.ai/result_of_all_web_scraper/naukri.json"
# Ensure the directory exists
os.makedirs(os.path.dirname(output_file), exist_ok=True)
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=4, ensure_ascii=False)

print(f"Data has been saved to {output_file}")
