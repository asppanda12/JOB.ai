# {
#     type:["cold_mail","referall_mail","linkedin_mail"],
#     resume_json:[{}],
    
# }
# app.py
from flask import Flask, jsonify, request
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
import sys
from dotenv import load_dotenv
import os
import json
load_dotenv()
API = os.getenv('GROQ_API_KEY')

sys.path.append('E:/JOB.ai/JOB.ai')  # Use forward slashes for path
from pdf_data_extractor import extract_pdf_text
app = Flask(__name__)

# In-memory storage for mails and resumes
mails = {
    "cold_mails": [],
    "referral_mails": [],
    "linkedin_mails": []
}

@app.route('/cold_mail', methods=['POST'])
def create_cold_mail():
    data = request.json
    id = data['id']
    file_path = f'E:/JOB.ai/JOB.ai/resume_cold_mail/{id}.json'   
    job_desc = data['job']
    
    # Open and load the JSON file
    with open(file_path, 'r') as file:
        resume_json = json.load(file)

    # print(resume_json)
    

    prompt = (
        f"Analyze the following resume information provided in JSON format. "
        f"Your task is to: Extract the most relevant details from my skills, experience, education, and "
        f"accomplishments that align with the role of {job_desc}. Use this information to craft a professional and engaging cold email "
        f"tailored to an HR representative. The cold email should: Begin with a polite and personalized greeting. "
        f"Clearly state the purpose of the email (to express interest in the {job_desc} role). Highlight my key qualifications and "
        f"accomplishments that make me a strong candidate for this role. Mention how my skills and experiences align with the company’s "
        f"goals or the job requirements. Conclude with a call to action, such as requesting a meeting or interview, and include a polite closing. "
        f"Focus on making the cold email concise, compelling, and tailored specifically to the job role. Use a professional tone while "
        f"keeping the message engaging and impactful. Output Format: Return the result in plain text format as a professional cold email, "
        f"without any additional text or explanation. Resume JSON: {resume_json}"
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

    # Assuming the response is an object with a 'message' field or directly returning text
    cold_email = response.content if hasattr(response, 'content') else str(response)

    # Append the cold email to mails["cold_mails"]
    mails["cold_mails"].append(cold_email)

    return jsonify({"message": "Cold mail created", "data": mails}), 201


@app.route('/referral_mail', methods=['POST'])
def create_referral_mail():
    data = request.json
    id = data['id']
    file_path = f'E:/JOB.ai/JOB.ai/resume_cold_mail/{id}.json'   
    job_desc = data['job']
    with open(file_path, 'r') as file:
        resume_json = json.load(file)
    prompt = (
    f"Analyze the following resume information provided in JSON format. "
    f"Your task is to: Extract the most relevant details from my skills, experience, education, and "
    f"accomplishments that align with the role of {job_desc}. Use this information to craft a professional and engaging cold email "
    f"that I can send to a person requesting a referral for the {job_desc} role. The email should: Begin with a polite and personalized greeting, "
    f"mention the person’s name, company, and the role you're interested in. Clearly state the purpose of the email (to request a referral for the {job_desc} role). "
    f"Highlight my key qualifications and accomplishments that make me a strong candidate for this role. Mention how my skills and experiences align with the company’s "
    f"goals or the job requirements, explaining why I would be a good fit. Conclude with a polite request for the person's help in referring me to the hiring manager or HR representative. "
    f"Focus on making the cold email concise, compelling, and tailored specifically to the job role and referral request. "
    f"Use a professional tone while keeping the message engaging and impactful. Output Format: Return the result in plain text format as a professional cold email, "
    f"without any additional text or explanation. Resume JSON: {resume_json}"
)
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

    # Assuming the response is an object with a 'message' field or directly returning text
    cold_email = response.content if hasattr(response, 'content') else str(response)

    # Append the cold email to mails["cold_mails"]
    mails["referral_mails"].append(cold_email)

    
    mails["referral_mails"].append(data)
    return jsonify({"message": "Referral mail created", "mail": mails["referral_mails"]}), 201

@app.route('/linkedin_mail', methods=['POST'])
def create_linkedin_mail():
    data = request.json
    data = request.json
    id = data['id']
    file_path = f'E:/JOB.ai/JOB.ai/resume_cold_mail/{id}.json'   
    job_desc = data['job']
    with open(file_path, 'r') as file:
        resume_json = json.load(file)
    prompt = (
    f"Analyze the following resume information provided in JSON format. "
    f"Your task is to: Extract the most relevant details from my skills, experience, education, and "
    f"accomplishments that align with the role of {job_desc}. Use this information to craft a professional and engaging LinkedIn message "
    f"that I can send to a person requesting a referral for the {job_desc} role. The LinkedIn message should: Begin with a polite and personalized greeting, "
    f"mention the person’s name, company, and the role you're interested in. Clearly state the purpose of the message (to request a referral for the {job_desc} role). "
    f"Highlight my key qualifications and accomplishments that make me a strong candidate for this role. Mention how my skills and experiences align with the company’s "
    f"goals or the job requirements, explaining why I would be a good fit. Conclude with a polite request for the person's help in referring me to the hiring manager or HR representative. "
    f"Focus on making the message concise, compelling, and tailored specifically to the job role and referral request. "
    f"Use a professional tone while keeping the message engaging and impactful. The message should have a random variation in phrasing, "
    f"making it sound natural and less scripted. Output Format: Return the result in plain text format as a professional LinkedIn message, "
    f"without any additional text or explanation. Resume JSON: {resume_json}"
)
    prompt_template = PromptTemplate.from_template("{prompt}")

    # Initialize the LLM with the provided API key
    llm = ChatGroq(
        model_name="llama-3.3-70b-versatile",
        temperature=0.7,
        groq_api_key=API
    )

    # Chain the prompt and LLM
    chat = prompt_template | llm

    # Invoke the chat model with the formatted prompt
    response = chat.invoke({"prompt": prompt})

    # Assuming the response is an object with a 'message' field or directly returning text
    cold_email = response.content if hasattr(response, 'content') else str(response)

    # Append the cold email to mails["cold_mails"]
    mails["linkedin_mails"].append(cold_email)

    
    mails["linkedin_mails"].append(data)
    return jsonify({"message": "Referral mail created", "mail": mails["linkedin_mails"]}), 201

if __name__ == '__main__':
    app.run(debug=True)