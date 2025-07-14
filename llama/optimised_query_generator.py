from llama_cpp import Llama
import json
from dotenv import load_dotenv
import os
import concurrent.futures

load_dotenv()

class LlamaQuery:
    def __init__(self):
        self.model_path = r"E:\JOB.ai\JOB.ai\llama\models\tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
        # Optimize model loading parameters
        self.llm = Llama(
            model_path=self.model_path,
            n_ctx=2048,          # Reduced context window
            n_threads=8,        # Increased threads (adjust based on your CPU)
            n_gpu_layers=0,     # Use GPU if available
            n_batch=512,        # Increased batch size
            verbose=False       # Reduce logging
        )

    def parse_job_description(self, job_data_str):
        try:
            if isinstance(job_data_str, dict):
                job_data_str = json.dumps(job_data_str)

            # Simplified and focused prompt
            prompt = f"""
            Parse job data into JSON with keys:
            job_title,job_link,company_name,experience,salary,location,job_description,years_of_experience,skills,job_type
            Data: {job_data_str}
            JSON only.
            """

            response = self.llm(
                prompt,
                max_tokens=200,      # Reduced max tokens
                temperature=0.5,     # Lower temperature for faster responses
                top_p=0.9,
                repeat_penalty=1.1,
                top_k=40,
                echo=False          # Don't echo prompt in response
            )

            text_response = response['choices'][0]['text']
            return json.loads(text_response)

        except json.JSONDecodeError:
            return {"error": "Invalid JSON response", "raw_text": text_response}
        except Exception as e:
            print(f"Error: {e}")
            return None

def process_batch(jobs, batch_size=5):
    llama = LlamaQuery()
    results = []
    
    # Process jobs in smaller batches
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        for job in batch:
            result = llama.parse_job_description(job)
            results.append(result)
    return results

def Extract_json(jobs):
    # Handle single job or list of jobs
    if not isinstance(jobs, list):
        jobs = [jobs]
    
    # Use process pooling for parallel processing
    with concurrent.futures.ProcessPoolExecutor() as executor:
        # Split jobs into batches
        batch_size = 3
        batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]
        
        # Process batches in parallel
        results = list(executor.map(process_batch, batches))
        
        # Flatten results
        flattened_results = [item for sublist in results for item in sublist]
        
        return flattened_results[0] if len(jobs) == 1 else flattened_results

if __name__ == "__main__":
    # Test with sample data
    sample_jobs = [
        {
            "title": "Software Engineer",
            "company": "Example Corp",
            "description": "Python developer"
        },
        {
            "title": "Data Scientist",
            "company": "Tech Co",
            "description": "ML expert"
        }
    ]
    
    results = Extract_json(sample_jobs)
    print(json.dumps(results, indent=2))