# ... existing imports ...
import fitz  # PyMuPDF
import sys
sys.path.append('E:/JOB.ai/JOB.ai')  # Use forward slashes for path
from genrativeai.response_llama import parse_job_data_llama, parse_job_data_gemini  # Note: genrative not generative
import json
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langchain_core.output_parsers import JsonOutputParser
import json
from dotenv import load_dotenv
import os
import pandas as pd  # Import pandas for Excel file creation

load_dotenv()
API = os.getenv('GROQ_API_KEY')


def entity_search(job,API):
    prompt = (
        "Extract relevant resume information from the following string, returning a clean and formatted JSON output containing "
        "the following fields: area_of_expertise,Name,Phone_number,Skills,professional experience,Achievements,Education.\n\n"
        "Do not include any additional text or explanation in your response. Return the output strictly as a JSON object."
        f"Input JSON:\n{job}"
    )

    # Create a prompt template
    prompt_template = PromptTemplate.from_template("{prompt}")

    # Initialize the LLM with the provided API key
    llm = ChatGroq(
        model_name="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key=API
    )

    # Chain the prompt and LLM
    chat = prompt_template | llm

    # Invoke the chat model with the formatted prompt
    response = chat.invoke({"prompt": prompt})

    # Parse the response content as JSON using JsonOutputParser
    json_parser = JsonOutputParser()
    parsed_response = json_parser.parse(response.content)
    return parsed_response
# New function to extract text from PDF using PyMuPDF
def extract_pdf_text(pdf_path):
    
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        if not text:
            raise ValueError("No text extracted from the PDF.")
        
    except FileNotFoundError as e:
        print("File not found:", e)
    except ValueError as ve:
        print("Value error:", ve)
    except Exception as e:
        print("An error occurred:", e)

    # Example usage
    ans=entity_search(text,API)
    output_file = "j210250.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ans, f, indent=4, ensure_ascii=False)
    return ans

if __name__ == "__main__":
    pdf_path = r'E:\JOB.ai\JOB.ai\job_resume\Sameer_Panda_M_Updated_Resume___1_.pdf'
    pdf_text_1 = extract_pdf_text(pdf_path)
    print(pdf_text_1)