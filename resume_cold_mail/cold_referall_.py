import os
import sys
sys.path.append('E:/JOB.ai/JOB.ai')  
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
import sys
from dotenv import load_dotenv
import os
import json

from resume_cold_mail.pdf_data_extractor import extract_pdf_text
from Data_base.mongodb import create_a_database, create_a_job_database_specific_user
from Data_base.schema_for_mongo_db import User
from Data_base.faiss_db_v2 import JobSearchEngine
API = os.getenv('GROQ_API_KEY')
mongo_uri=os.getenv('MONGO_DB_URI')

def get_resume_data(chat_id):
    db=create_a_database(mongo_uri)
    document=db.find_one({'chat_id': int(chat_id)})
    return document['resume_json']
    
def get_job_data(chat_id, job_id):
    db = create_a_job_database_specific_user(mongo_uri)
    
    # Debug prints
   
    
    # Find document with the job recommendation
    document = db.find_one({
        "chat_id": int(chat_id),
        "job_recommendation": {
            "$elemMatch": {
                "metadata.job_indx": int(job_id)
            }
        }
    })
    
    print(f"Found document: {document}")
    
    if document is None:
        raise ValueError(f"No job data found for chat_id: {chat_id} and job_id: {job_id}")
    
    # Extract the specific job recommendation
    for job in document.get('job_recommendation', []):
        if job.get('metadata', {}).get('job_indx') == int(job_id):
            return job
            
    raise ValueError(f"Job with id {job_id} not found in recommendations")
    
sys.path.append('E:/JOB.ai/JOB.ai')  # Use forward slashes for path



def create_cold_mail(chat_id,job_id):
    resume_json=get_resume_data(chat_id)
    job_json=get_job_data(chat_id,job_id)
    


    prompt = (
       f"Analyze the following resume information provided in JSON format. "
f"Your task is to: Extract the most relevant details from my skills, experience, education, and "
f"accomplishments that align with the role of {job_json}. Use this information to craft a professional and engaging cold email "
f"tailored to an HR representative. The cold email should: Begin with a polite and personalized greeting. "
f"Clearly state the purpose of the email (to express interest in the {job_json} role). Highlight my key qualifications and "
f"accomplishments that make me a strong candidate for this role. Mention how my skills and experiences align with the company's "
f"goals or the job requirements. Conclude with a call to action, such as requesting a meeting or interview, and include a polite closing. "
f"Focus on making the cold email concise, compelling, and tailored specifically to the {job_json} role. Use a professional tone while "
f"keeping the message engaging and impactful. Output Format: Return the result in plain text format as a professional cold email, "
f"without any additional text or explanation. Resume JSON: {resume_json}"
f"Note: The generated cover letter email should not exceed 4096 characters."
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

    

    return cold_email


def create_referral_mail(chat_id,job_id):
    print(f'{chat_id} {job_id}')
    resume_json=get_resume_data(chat_id)
    job_json=get_job_data(chat_id,job_id)
    prompt = (
    f"Analyze the following resume information provided in JSON format. "
f"Your task is to: Extract the most relevant details from my skills, experience, education, and "
f"accomplishments that align with the role of {job_json} . Use this information to craft a concise and professional "
f"LinkedIn message requesting a referral from a current employee. The message should: "
f"Start with a polite and personalized greeting. Briefly introduce myself and my background. Clearly express my interest in the {job_json} role "
f"and highlight why I am a great fit. Politely ask if they would be open to referring me for the role. "
f"Keep the message concise, professional, and appreciative of their time. Output Format: Return the result in plain text format as a LinkedIn message, "
f"without any additional text or explanation. Resume JSON: {resume_json}"
f"Note: The generated cover letter email should not exceed 4096 characters."
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
    referall_email = response.content if hasattr(response, 'content') else str(response)

   
    return referall_email

def create_cover_letter_mail(chat_id,job_id):
    resume_json=get_resume_data(chat_id)
    job_desc=get_job_data(chat_id,job_id)
    
    prompt =  (
    f"Analyze the following resume information provided in JSON format. "
    f"Your task is to extract the most relevant details from my skills, experience, education, and "
    f"accomplishments that align with the {job_desc} . "
    f"Use this information to draft a compelling and professional cover letter email that:\n\n"
    f"- Starts with a personalized greeting.\n"
    f"- Clearly expresses my enthusiasm for the {job_desc} role.\n"
    f"- Highlights my key qualifications, achievements, and past work experience that make me an excellent fit.\n"
    f"- Demonstrates how my skills align with the company goals and job requirements.\n"
    f"- Ends with a strong closing, including a request for an interview or further discussion.\n\n"
    f"The tone should be formal yet engaging, and the email should be well-structured, concise, and impactful.\n\n"
    f"**Note: The generated cover letter email should not exceed 4096 characters.**\n\n"
    f"Output Format:\n"
    f"Return the result in plain text format as a professional cover letter email, without any additional text or explanation.\n\n"
    f"Resume JSON: {resume_json}"
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
    cover_letter = response.content if hasattr(response, 'content') else str(response)

    # Append the cold email to mails["cold_mails"]
    
    return cover_letter

