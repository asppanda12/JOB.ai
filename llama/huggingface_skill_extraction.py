import json
from dotenv import load_dotenv
import os
from langchain_core.prompts import PromptTemplate
from langchain_huggingface import HuggingFaceEndpoint
from langchain_core.output_parsers import JsonOutputParser

load_dotenv()

API = os.getenv('HUGGINGFACE_TOKEN')
api_token = API

def parse_job_data_llama(job_data):
    """
    Function to parse job data JSON and extract relevant information using LangChain and Llama model.

    Parameters:
    - job_data (dict): The job data in JSON format.

    Returns:
    - dict: The parsed job data in a clean JSON format.
    """
    # Convert the job data to a properly formatted string
    job_data_str = job_data
    # Refined prompt for extracting and structuring the job data
    prompt = (
    "You are an AI assistant whose job is to extract technical skills from job descriptions."
    "Focus only on identifying technical skills mentioned explicitly in the job description."
    "Strictly return only a simple, comma-separated list of technical skills without any additional text."
    f"Job Description:\n{job_data_str}\n\nTechnical Skills:"
)




    # Create a prompt template
    prompt_template = PromptTemplate.from_template("{prompt}")

    # Initialize the Hugging Face model endpoint
    llm = HuggingFaceEndpoint(
        huggingfacehub_api_token="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",
        endpoint_url="https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-3B-Instruct",
        temperature=0.5,
        max_tokens=2048
    )

    # Chain the prompt and LLM
    chat = prompt_template | llm

    # Invoke the chat model with the formatted prompt
    response = chat.invoke({"prompt": prompt})

    # Ensure response is valid JSON
    # json_parser = JsonOutputParser()
    
    # parsed_response = json_parser.parse(response)
    

    return response

# Test the function
if __name__ == "__main__":
    job_data =  {
  "Job Title": "Developer 1",
  "Job Link": "https://in.linkedin.com/jobs/view/developer-1-at-hyland-4119577209?position=19&pageNum=0&refId=7PbDUv7euL14mV5Zin0SwA%3D%3D&trackingId=6VwcTUm9JtsYmriKFRpyiQ%3D%3D",
  "Company Name": "Hyland",
  "Experience": "0-2 Yrs of experience",
  "Salary": "",
  "Location": "Kolkata, West Bengal, India",
  "Job Description": "Overview\nHyland Software is widely known as a great company to work for and a great company to do business with. Being a leader in providing software solution for managing content, processes and cases for organizations across the globe we enabled more than 20,000 organizations to digitalize their workplaces and transform their operations.\nCurrently we are looking for a Developer 1 Job Description\n0-2 Yrs of experience.\nThe Developer is responsible for the overall performance of the product through applying principles of software engineering to the design development maintenance testing and evaluation of the software. The Developer ensures timely delivery of high quality software within the release timelines and guidelines.\nWhat You Will Be Doing\nDevelop code based on functional specifications through understanding of product code\nTest code to verify it meets the technical specifications and is working as intended, before submitting to code review\nCreate and apply automated tests and test principles to software changes, including (but not limited to) unit tests\nFollow prescribed standards and processes as applicable to software development methodology, including planning, work estimation, solution demos, and reviews\nAssist and contribute to peer code reviews\nRead and understand basic software requirements\nAssist with the implementation of a delivery pipeline, including test automation, security, and performance\nAssist with team or product documentation\nAssist in troubleshooting and responding to production issues to ensure the stability of the application\nWhat Will Make You Successful\nBachelor's degree or equivalent experience\nWorking knowledge of data structures, algorithms, and software design\nKnowledge of software development life cycle\nSoftware development experience in one or more general purpose programming languages\nKnowledge of Windows/Linux development environment, working with open source tools/platforms\nKnowledge of build environments and delivery pipelines\nKnowledge of test automation and continuous integration tools\nBasic knowledge in software application testing tools, methodologies, and process framework\nOral and written communications skills that demonstrate a professional demeanor and the ability to interact with others with discretion and tact\nCollaboration skills, applied successfully within team\nCritical thinking and problem solving skills\nSelf-motivated with the ability to complete projects in a timely manner\nAbility to work independently and in a team environment\nAttention to detail\nDriven to learn and stay current professionally\nPassionate, competitive and intellectually curious\nSharp, fast learner with technology curiosity and aptitude\nUp to 10% travel time required\nHyland’s Offering\nWe’re proud of our culture and take employee engagement seriously. By listening to employees’ feedback, we’re able to provide meaningful benefits and programs to our workforce.\nLearning & Development - development budget (used for certifications, conferences ect.), tuition assistance program, 4,000+ self-paced online courses, instructor-led webinars, mentorship programs, structured on-boarding experience full of trainings, dedicated Learning & Development department supporting our employees\nR&D focus – cutting edge technologies, constant modernization efforts, dynamic and innovative environment, dedicated R&D Education Services department to help you grow\nWork-life balance culture – flexible work environment and working hours (we are working in task-based system!), possibility to work from home, we value trust and we believe efficiency does not depend on your actual location, however we would like to spend time together in the office!\nWell-being - private medical healthcare, life insurance, gym reimbursement, psychologist & dietician consultation, wellness manager care, constant wellbeing programs\nCommunity Engagement – Volunteer time off (12h/year), Hylanders for Hylanders relief found, Mission fit giving, Dolars-for-doers matching gift programs\nDiversity & Inclusion – employee resource groups, inclusion benefits and policies\nNiceties & Events – quarterly profit sharing, culture & outings budgets, snacks and beverages, employee referral program, Christmas, birthday, baby gifts, constant incentives and employee programs\nIf you would like to join the company where honesty, integrity and fairness lie in the bottom of values, where people are truly passionate about technology and dedicated to their work – connect with us! We are committed to a policy of Equal Employment Opportunity and will not discriminate against an applicant or employee on the basis of race, color, religion, creed, national origin or ancestry, sex, age, physical or mental disability, veteran or military status, genetic information, sexual orientation, marital status, gender identity, or any other legally recognized protected basis under federal, state or local laws, regulations or ordinances.",
}

    parsed_job_data_llama = parse_job_data_llama(job_data['Job Description'])
   

    with open("parsed_job_data_llama.json", 'w', encoding='utf-8') as f:
        json.dump(parsed_job_data_llama, f, indent=4, ensure_ascii=False)  # Write the data
