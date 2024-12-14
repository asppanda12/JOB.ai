from dotenv import load_dotenv
import os
load_dotenv()
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_community.document_loaders import WebBaseLoader
API = os.getenv('GROQ_API_KEY')

os.environ['USER_AGENT'] = 'YourAppName/1.0'  # Replace with your app name and version

# llm = ChatGroq(temperature=0, groq_api_key=API, model_name="llama3-8b-8192")
loader = WebBaseLoader("https://jobs.nike.com/job/R-47107?from=job%20search%20funnel")
page_data=loader.load().pop().page_content

print(page_data)
# response=llm.invoke("What is the shape of earth")
# print(response)

