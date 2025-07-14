from llama_cpp import Llama
import json
from dotenv import load_dotenv
import os
import re
load_dotenv()

class LlamaQuery:
    def __init__(self):
        self.model_path = r"E:\JOB.ai\JOB.ai\llama\models\tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
        self.llm = Llama(
            model_path=self.model_path,
            n_ctx=2048,
            n_threads=4,
            n_gpu_layers=0
        )

    def parse_job_description(self, job_data_str):
        # try:
    
        try:
            print(job_data_str)
            # job_data = json.loads(job_data_str)  # Convert JSON string to dictionary
            job_data=job_data_str
        except json.JSONDecodeError:
            raise ValueError("Input string is not valid JSON")
        

            # Clean the data
        
            # More explicit prompt with example format
        prompt = ("Extract relevant job information from the following JSON file, returning a clean and formatted JSON output containing "
"the following fields: job title, job link, company name, experience, salary, location, job description, years of experience, skills, and job type (software developer, front-end engineer, back-end engineer, data scientist, etc.). "
"If some information is missing, try to extract it from the description or link provided. The job type field should categorize the role based on the job title or description. For example, 'software developer', 'front-end engineer', 'back-end engineer', or 'data scientist'.The value of the each key should be in string format.\n\n"
"Do not include any additional text or explanation in your response. Return the output strictly as a JSON object."

        f"Input JSON:\n{job_data_str}"
    )

        response = self.llm(
            prompt,
            max_tokens=1500,      
            temperature=0.0,     # Set to 0 for deterministic output
            top_p=1.0,
            repeat_penalty=1.2,
            top_k=50,
            echo=False          
        )

        text_response = response['choices'][0]['text'].strip()
        print(text_response)
        # Clean the response to ensure it's valid JSON
        text_response = text_response.replace('\n', ' ').strip()
        if not text_response.startswith('{'): 
            text_response = text_response[text_response.find('{'):]
        if not text_response.endswith('}'):
            text_response = text_response[:text_response.rfind('}')+1]
        
        return json.loads(text_response)

def Extract_json(job):
    try:
        llama = LlamaQuery()
        return llama.parse_job_description(job)
    except Exception as e:
        print(f"Error in Extract_json: {e}")
        return None
if __name__ == "__main__":
    file_path = r"E:\JOB.ai\JOB.ai\Linkedin\test.json"

    # Load the data from the JSON file
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)  # Load JSON data into a Python list

    print("Data loaded successfully.")

    # Check if data is a list
    if isinstance(data, list):
        results = []
        llama = LlamaQuery()

        for job in data:
            try:
                # Convert the job dictionary to a JSON string for processing
                job_data_str = json.dumps(job)
                result = llama.parse_job_description(job_data_str)
                results.append(result)
            except Exception as e:
                print(f"Error processing job: {job.get('title', 'Unknown')}, Error: {e}")
                results.append({"error": str(e), "job_data": job})

        # Output all processed results
        print(json.dumps(results, indent=2))
    else:
        print("Error: The input file does not contain a list of job descriptions.")
