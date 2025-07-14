from dotenv import load_dotenv
import os
import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Load environment variables
load_dotenv()

# Get API keys and user agent
API = os.getenv('GROQ_API_KEY')
os.environ['USER_AGENT'] = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
)

# Print user agent to confirm setup
user_agent = os.getenv('USER_AGENT')
print(f"Using User Agent: {user_agent}")

# Job data JSON
job_data = {
    "Job Title": "Data Scientist & Experimentation Analyst",
    "Job Link": "https://www.naukri.com/job-listings-data-scientist-experimentation-analyst-encora-bengaluru-0-to-5-years-241224504875",
    "Company Name": "Encora\n3.8\n665 Reviews",
    "Experience": "0-5 Yrs",
    "Salary": "Not disclosed",
    "Location": "Bengaluru",
    "Job Description": "Experience with data visualization platforms (e.g., Tableau, Power BI, Matplotlib, or S...",
    "Skills": [
        "Product engineering",
        "Data analysis",
        "Statistical modeling",
        "Senior Analyst",
        "Cloud Services",
        "Machine learning",
        "Quality engineering",
        "Data analytics"
    ]
}

# Convert the JSON to a properly formatted string
job_data_str = json.dumps(job_data, indent=2)

# Prepare the prompt
prompt = (
    "Extract relevant job information from the following JSON file, returning a clean and formatted JSON output containing "
    "the following fields: job title, job link, company name, experience, salary, location, job description, and skills.\n\n"
    "Do not include any additional text or explanation in your response. Return the output strictly as a JSON object."
    f"Input JSON:\n{job_data_str}"
)

# Create a prompt template
prompt_template = PromptTemplate.from_template("{prompt}")

# Initialize the LLM
llm = ChatGroq(
    model_name="llama-3.3-70b-versatile",
    temperature=0,
    groq_api_key=API
)

# Chain the prompt and LLM
chat = prompt_template | llm

# Invoke the chat model with the formatted prompt
response = chat.invoke({"prompt": prompt})
json_parser = JsonOutputParser()
parsed_response = json_parser.parse(response.content)

print(parsed_response)
