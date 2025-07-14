from dotenv import load_dotenv
import os
import json
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langchain_core.output_parsers import JsonOutputParser

# Load environment variables
load_dotenv()

def parse_job_data_llama(job_data, groq_api_key):
    """
    Function to parse job data JSON and extract relevant information using LangChain.

    Parameters:
    - job_data (dict): The job data in JSON format.
    - groq_api_key (str): The API key for Groq LLM.

    Returns:
    - dict: The parsed job data in a clean JSON format.
    """
    # Convert the job data to a properly formatted string
    job_data_str = json.dumps(job_data, indent=2)

    # Prepare the prompt
    prompt = (
        # "Extract relevant job information from the following JSON file, returning a clean and formatted JSON output containing "
        # "the following fields: job title, job link, company name, experience, salary, location, job description, years of experience and skills.If some information is missing try to extract it from description or link provided.\n\n"
        # "Do not include any additional text or explanation in your response. Return the output strictly as a JSON object."
        "Extract relevant job information from the following JSON file, returning a clean and formatted JSON output containing "
"the following fields: job title, job link, company name, experience, salary, location, job description, years of experience, skills, and job type (software developer, front-end engineer, back-end engineer, data scientist, etc.). "
"If some information is missing, try to extract it from the description or link provided. The job type field should categorize the role based on the job title or description. For example, 'software developer', 'front-end engineer', 'back-end engineer', or 'data scientist'.The value of the each key should be in string format.\n\n"
"Do not include any additional text or explanation in your response. Return the output strictly as a JSON object."

        f"Input JSON:\n{job_data_str}"
    )

    # Create a prompt template
    prompt_template = PromptTemplate.from_template("{prompt}")

    # Initialize the LLM with the provided API key
    llm = ChatGroq(
        model_name="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key=groq_api_key
    )

    # Chain the prompt and LLM
    chat = prompt_template | llm

    # Invoke the chat model with the formatted prompt
    response = chat.invoke({"prompt": prompt})

    # Parse the response content as JSON using JsonOutputParser
    json_parser = JsonOutputParser()
    parsed_response = json_parser.parse(response.content)

    return parsed_response

def parse_job_data_gemini(job_data, groq_api_key):
    """
    Function to parse job data JSON and extract relevant information using LangChain.

    Parameters:
    - job_data (dict): The job data in JSON format.
    - groq_api_key (str): The API key for Groq LLM.

    Returns:
    - dict: The parsed job data in a clean JSON format.
    """
    # Convert the job data to a properly formatted string
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

    # Initialize the LLM with the provided API key
    llm = ChatGroq(
        model_name="gemma2-9b-it",
        temperature=0,
        groq_api_key=groq_api_key
    )

    # Chain the prompt and LLM
    chat = prompt_template | llm

    # Invoke the chat model with the formatted prompt
    response = chat.invoke({"prompt": prompt})

    # Parse the response content as JSON using JsonOutputParser
    json_parser = JsonOutputParser()
    parsed_response = json_parser.parse(response.content)

    return parsed_response
# Example usage of the function:
if __name__ == "__main__":
    # Get the API key
    API = os.getenv('GROQ_API_KEY')

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
    job_data1={
        "title": "Embedded Software Engineer, Silicon Validation Software",
        "company": "Google",
        "location": "Bengaluru, Karnataka, India",
        "link": "https://in.linkedin.com/jobs/view/embedded-software-engineer-silicon-validation-software-at-google-4105496373?position=1&pageNum=0&refId=bdvkORUSMoiJ5d%2Bsi101jQ%3D%3D&trackingId=1pau%2BUqk859%2FdRynjCEKNg%3D%3D",
        "description": "Minimum qualifications:\nBachelor's degree in Electrical Engineering, Electronics Engineering or Computer Science, or equivalent practical experience.\n2 years of experience with software development in one or more programming languages, or 1 year of experience with an advanced degree.\nExperience with embedded programming in C/C++.\nPreferred qualifications:\nMaster's degree in Electrical Engineering, Electronics Engineering or Computer Science.\nExperience working closely with hardware designers and reading schematics.\nExperience in performance analysis and optimization.\nExperience working with hardware designers and reading schematics.\nKnowledge of embedded systems development, Real-Time Operating System (RTOS) concepts, device drivers and hardware/software integration.\nAbout The Job\nBe part of a diverse team that pushes boundaries, developing custom silicon solutions that power the future of Google's direct-to-consumer products. You'll contribute to the innovation behind products loved by millions worldwide. Your expertise will shape the next generation of hardware experiences, delivering unparalleled performance, efficiency, and integration.\nGoogle's mission is to organize the world's information and make it universally accessible and useful. Our team combines the best of Google AI, Software, and Hardware to create radically helpful experiences. We research, design, and develop new technologies and hardware to make computing faster, seamless, and more powerful. We aim to make people's lives better through technology.\nResponsibilities\nLead the development of end-to-end hardware and software solutions.\nWork to enable device drivers for applications on devices.\nDevelop new software, hardware, and system architecture to support future applications.\nDesign, development, and testing of embedded software drivers for the next generation smart devices.\nGoogle is proud to be an equal opportunity workplace and is an affirmative action employer. We are committed to equal employment opportunity regardless of race, color, ancestry, religion, sex, national origin, sexual orientation, age, citizenship, marital status, disability, gender identity or Veteran status. We also consider qualified applicants regardless of criminal histories, consistent with legal requirements. See also Google's EEO Policy and EEO is the Law. If you have a disability or special need that requires accommodation, please let us know by completing our Accommodations for Applicants form ."
    }
    # Call the function with the job data and API key
    parsed_job_data_llama = parse_job_data_llama(job_data1, API)

    # Print the parsed response
    parsed_job_data_gemini=parse_job_data_gemini(job_data1, API)
    print(parsed_job_data_llama)
    print(parsed_job_data_gemini)