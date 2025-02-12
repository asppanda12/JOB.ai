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
    "Extract and format the following resume information into a JSON object with strict adherence to this schema:\n\n"
    "{\n"
    '    "area_of_expertise": [list of technical specializations],\n'
    '    "Name": "Full Name",\n'
    '    "Phone_number": "phone string with country code",\n'
    '    "Skills": [list of technical skills/tools],\n'
    '    "professional_experience": [\n'
    '        {\n'
    '            "company": "Company Name",\n'
    '            "position": "Job Title",\n'
    '            "duration": "MM/YYYY - MM/YYYY or present",\n'
    '            "achievements": [list of bullet points],\n'
    '            "technologies": [list of technologies used]\n'
    '        }\n'
    '    ],\n'
    '    "Achievements": [list of career/academic achievements],\n'
    '    "Education": [\n'
    '        {\n'
    '            "institution": "School Name",\n'
    '            "degree": "Degree Name",\n'
    '            "duration": "MM/YYYY - MM/YYYY",\n'
    '            "cgpa/percentage": "score"\n'
    '        }\n'
    '    ],\n'
    '    "Years_of_experience": total_years\n'
    "}\n\n"
    "Follow these rules strictly:\n"
    "1. Maintain exact field names and JSON structure\n"
    "2. Convert durations to years by calculating full months worked/12\n"
    "3. For education dates without month, use format 'Mar YYYY'\n"
    "4. Keep skill/technology lists lowercase unless proper nouns\n"
    "5. Include all numerical values as strings\n"
    "6. Preserve original achievement bullet points verbatim\n"
    "7. Format phone numbers with country code\n"
    "8. Omit null/empty fields\n\n"
    "Input resume text:\n"
    f"{job}\n\n"
    "Return ONLY the JSON object with no additional text or formatting. "
    "If any information is missing, omit the field or use 'N/A'."
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
    print(text)
    ans=entity_search(text,API)
    output_file = "Ruddhis_job.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ans, f, indent=4, ensure_ascii=False)
    return ans

if __name__ == "__main__":
    pdf_path = r'E:\JOB.ai\JOB.ai\job_resume\ruddhi_7748640302.pdf'
    pdf_text_1 = extract_pdf_text(pdf_path)
    # print(pdf_text_1)