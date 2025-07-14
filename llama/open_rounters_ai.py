from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

llm = ChatOpenAI(
    model="meta-llama/llama-3.1-8b-instruct",
    openai_api_key="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",
    openai_api_base=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
)

response = llm.invoke([
    HumanMessage(content="wh.")
])

print(response.content)
