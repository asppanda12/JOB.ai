import json
from dotenv import load_dotenv
import os
from langchain_core.prompts import PromptTemplate
from langchain_huggingface import HuggingFaceEndpoint
from langchain_core.output_parsers import JsonOutputParser

load_dotenv()

# Initialize components ONCE (outside the function)
# ==================================================
api_token = os.getenv('HUGGINGFACE_TOKEN')

# 1. Define the prompt template (static parts)
prompt_template = PromptTemplate.from_template(
    "Act as a highly efficient job assistant. Return a JSON object with the following structure:\n\n"
    "{{\n"
    "  \"Job Title\": \"<Job Title>\",\n"
    "  \"Job Link\": \"<Job Link>\",\n"
    "  \"Company Name\": \"<Company Name>\",\n"
    "  \"Experience\": \"<Experience>\",\n"
    "  \"Salary\": \"<Salary>\",\n"
    "  \"Location\": \"<Location>\",\n"
    "  \"Job Description\": \"<Job Description>\",\n"
    "  \"Skills\": [\"<Skill1>\", \"<Skill2>\", ...],\n"
    "  \"Job Type\": \"<Job Type>\"\n"
    "}}\n\n"
    "Rules:\n"
    "- No extra text/explanations\n"
    "- Fill ALL keys; omit empty ones as \"\"\n"
    "- Extract skills from the description\n"
    "- Categorize Job Type\n\n"
    "Input JSON:\n{job_data_str}\n\nOutput JSON:"
)

# 2. Initialize the model ONCE
llm = HuggingFaceEndpoint(
    huggingfacehub_api_token="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",
    endpoint_url="https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-3B-Instruct",
    temperature=0.1,  # Lower for more consistency
    max_tokens=1024
)

# 3. Chain components ONCE
chain = prompt_template | llm | JsonOutputParser()

# Processing Function
# ===================
def parse_job_data_llama(job_data):
    """Process job data using the pre-initialized chain."""
    try:
        # Convert input to string
        job_data_str = json.dumps(job_data, indent=2)
        # Invoke the pre-built chain
        return chain.invoke({"job_data_str": job_data_str})
    except Exception as e:
        print(f"Error processing job data: {e}")
        return None

# Usage Example
if __name__ == "__main__":
    job_data = {
        "title": "Senior Data Scientist",
        "company": "TechCorp",
        "location": "Remote",
        "link": "https://example.com/jobs/123",
        "description": "Looking for a data scientist with Python, SQL, and ML experience..."
    }

    # First call (initializes everything)
    result1 = parse_job_data_llama(job_data)
    
    # Subsequent calls reuse the initialized components
    print(result1)