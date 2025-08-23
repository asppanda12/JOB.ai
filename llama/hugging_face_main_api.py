import json
from dotenv import load_dotenv
import os
from langchain_core.prompts import PromptTemplate
from langchain_huggingface import HuggingFaceEndpoint
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv
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
    job_data_str = json.dumps(job_data, indent=2)
    output_example = {
    "Job Title": "Software Engineer - Machine Learning",
    "Job Link": "https://in.linkedin.com/jobs/view/software-engineer-machine-learning-at-linkedin-4102540455?position=4&pageNum=0&refId=W2HqTz8GkIVLZz6sKVyfVw%3D%3D&trackingId=q4%2Bz27ppZ8Iqwjjjucnmxg%3D%3D",
    "Company Name": "LinkedIn",
    "Experience": "2+ years",
    "Salary": "Not specified",
    "Location": "India",
    "Job Description": "LinkedIn is seeking a research engineer/scientist to develop state-of-the-art NLP and vision algorithms to understand member-posted content meaningfully. Responsibilities include developing next-gen algorithms for text, image, video, and graph classification, as well as scaling models to millions of contents and members. The role involves end-to-end model development, mentoring junior engineers, and representing LinkedIn in academic and industry forums. The role is hybrid and based in India. Basic qualifications include a Master’s degree or a Bachelor’s with 2+ years of relevant experience. Preferred qualifications include hands-on experience in ML, DL, NLP, and related technologies.",
    "Skills": [
      "Machine Learning",
      "Deep Learning",
      "Natural Language Processing (NLP)",
      "Computer Vision",
      "Image Processing",
      "Statistical Modeling",
      "Data Mining",
      "Graph Learning",
      "Generative AI",
      "Large Language Models (LLMs)",
      "Geometric Deep Learning",
      "Supervised Learning",
      "Semi-Supervised Learning",
      "Python Programming",
      "Software Engineering Practices",
      "Mentoring",
      "Content Classification",
      "Model Deployment",
      "Communication",
      "Team Collaboration"
    ],
    "Job Type": "Machine Learning Engineer"
  }

    # Refined prompt for extracting and structuring the job data
    prompt = (
    "Act as a highly efficient job assistant who provide data in a perfect json format not leavig any commas while separating two keys. Do not provide any additional explanation or notes. "
    "Strictly return only a simple JSON object with all the required data with all the keys in the output format. "
    "Make sure to add all values in every key — do not leave any key empty . "
    "Make sure you dont ignore any key ."
    "The key 'Skills' should be included and should contain all the relevant skills from the job description, including technical and non-technical skills . "
    "The key 'Job Type' should categorize the role based on the job title or description — for example, 'Software Developer', 'Data Scientist', 'Frontend Engineer', etc.\n\n"
    "Return the output in the following format:\n\n"
    "{\n"
    "  \"Job Title\": \"<Job Title>\",\n"
    "  \"Job Link\": \"<Job Link>\",\n"
    "  \"Company Name\": \"<Company Name>\",\n"
    "  \"Experience\": \"<Experience>\",\n"
    "  \"Salary\": \"<Salary>\",\n"
    "  \"Location\": \"<Location>\",\n"
    "  \"Job Description\": \"<Job Description>\",\n"
    "  \"Skills\": [\n"
    "    \"<Skill1>\",\n"
    "    \"<Skill2>\",\n"
    "    \"<Skill3>\",\n"
    "    ...\n"
    "  ],\n"
    "  \"Job Type\": \"<Job Type>\"\n"
    "}\n"
    "Do not include any additional notes or explanations. Only return the strict output JSON with no omissions or modifications.\n"
    "Output Example:{output_example}\n\n"
    f"Input JSON:\n{job_data_str}\n\nOutput JSON:"
)


    # # Create a prompt template
    prompt_template = PromptTemplate.from_template("{prompt}")


    llm = ChatOpenAI(
    model="meta-llama/llama-3.1-8b-instruct",
    openai_api_key="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",
    openai_api_base=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
)

    # Chain the prompt and LLM
    chat = prompt_template | llm

    # Invoke the chat model with the formatted prompt
    response = chat.invoke({"prompt": prompt})

    # Ensure response is valid JSON
    json_parser = JsonOutputParser()
    
    parsed_response = json_parser.parse(response.content)
    

    return parsed_response

# Test the function
if __name__ == "__main__":
    job_data =      {
        "title": "   ,    ",
        "company": " ",
        "location": " ,  ,  ",
        "link": "https://in.linkedin.com/jobs/view/software-engineer-machine-learning-at-linkedin-4102540455?position=4&pageNum=0&refId=W2HqTz8GkIVLZz6sKVyfVw%3D%3D&trackingId=q4%2Bz27ppZ8Iqwjjjucnmxg%3D%3D",
        "description": "LinkedIn was built to help professionals achieve more in their careers, and every day millions of people use our products to make connections, discover opportunities, and gain insights. Our global reach means we get to make a direct impact on the world’s workforce in ways no other company can. We’re much more than a digital resume -- we transform lives through innovative products and technology.\nEvery day, millions of posts, videos, and articles course through the LinkedIn feed, generating tens of thousands of comments every hour — and tens of millions more shares and likes.\nWe are looking for a research engineer/scientist to develop state of art NLP & vision algorithms to understand member posted content meaningfully. You will be instrumental in improving the efficacy of communication and content exchange between millions of LinkedIn members by developing cutting edge content understanding and classification algorithms. The understanding is not only limited to extract features but to summarize, classify & cluster content. We own the end to end stack from idea creation, POC, design to product deployment.\nAs part of a new and fast growing team of top-notch scientists and engineers, you will experience all the excitement and dynamism of a startup along with the scale and technology of a world-class enterprise.\nAt LinkedIn, we trust each other to do our best work where it works best for us and our teams. This role offers a hybrid work option, meaning you can both work from home and commute to a LinkedIn office, depending on what’s best for you and when it is important for your team to be together.\nResponsibilities:\n- Develop next-gen algorithms to understand visual content and textual content and member interactions on LinkedIn\n- Develop state-of-art text/image/video/graph classification models scaling to millions of content and thousands of categories\n- Develop state-of-art supervised and semi-supervised models scaling to hundreds of millions of members and their content\n- Own end-to-end model development and deployment at LinkedIn scale\n- Mentor junior research engineers in utilizing advanced machine learning techniques for critical business problems\n- Represent LinkedIn in academic and industry circles by showcasing our innovation, data products and scientific expertise in bringing game-changing data products to market\nBasic Qualifications:\n- Master’s degree OR Bachelor’s degree with 2+ years of work experience\n- 2+ years of experience in at least one of the following areas: Computer vision, Image processing, Machine Learning, Statistical modeling/inference, Data mining, NLP, Graph/geometric deep learning, Large Language Models, Generative AI\nPreferred Qualifications:\n- 2+ years of hands-on experience working on machine learning, deep learning, NLP or related topics\n- Understanding of standard programming and software engineering practices\n- Ability and eagerness to program\nSuggested Skills:\n- Machine Learning\n- Deep Learning\n- Generative-AI\n- Large Language Models\nYou will Benefit from our Culture:\nWe strongly believe in the well-being of our employees and their families. That is why we offer generous health and wellness programs and time away for employees of all levels.\nIndia Disability Policy\nLinkedIn is an equal employment opportunity employer offering opportunities to all job seekers, including individuals with disabilities. For more information on our equal opportunity policy, please visit https://legal.linkedin.com/content/dam/legal/Policy_India_EqualOppPWD_9-12-2023.pdf\nGlobal Data Privacy Notice for Job Candidates\nThis document provides transparency around the way in which LinkedIn handles personal data of employees and job applicants: https://legal.linkedin.com/candidate-portal"
    }

    parsed_job_data_llama = parse_job_data_llama(job_data)
   

    with open("parsed_job_data_llama.json", 'w', encoding='utf-8') as f:
        json.dump(parsed_job_data_llama, f, indent=4, ensure_ascii=False)  # Write the data
