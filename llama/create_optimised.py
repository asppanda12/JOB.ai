import sys
sys.path.append('E:/JOB.ai/JOB.ai')
from llama.query_generator import Extract_json
import json
from dotenv import load_dotenv
import os

def truncate_text(text, max_length=1500):
    """Truncate text to a maximum length while trying to keep important information"""
    if isinstance(text, dict):
        # If it's a dictionary, convert to string and truncate
        text = json.dumps(text)
    return text[:max_length] + ("..." if len(text) > max_length else "")

def process_jobs(job_data, batch_size=10):
    output_data = []
    
    # Process in smaller batches
    for i in range(0, len(job_data), batch_size):
        batch = job_data[i:i + batch_size]
        print(f"Processing batch {i//batch_size + 1}/{len(job_data)//batch_size + 1}")
        
        # Truncate each job's text before processing
        truncated_batch = [truncate_text(job) for job in batch]
        
        try:
            # Process the truncated batch
            results = Extract_json(truncated_batch)
            if results:
                if isinstance(results, list):
                    output_data.extend(results)
                else:
                    output_data.append(results)
        except Exception as e:
            print(f"Error processing batch: {e}")
    
    return output_data

# Main execution
linkedin = r"E:\JOB.ai\JOB.ai\Linkedin\_Software Engineer_India_linkedin_jobs.json"

try:
    with open(linkedin, 'r', encoding='utf-8') as file:
        job_data = json.load(file)
except Exception as e:
    print(f"Error reading file: {e}")
    job_data = []

if job_data:
    print(f"Total jobs to process: {len(job_data)}")
    
    # Process all jobs in batches
    output_data = process_jobs(job_data, batch_size=5)
    
    # Save results
    output_file = r"E:\JOB.ai\JOB.ai\result_of_all_web_scraper\linkedin_parsed_jobs.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=4, ensure_ascii=False)
    
    print(f"Successfully processed {len(output_data)} jobs")
    print(f"Data saved to {output_file}")
else:
    print("No jobs to process")
