import ast
from dotenv import load_dotenv
import os
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

# Load environment variables
load_dotenv()
API = os.getenv('HUGGINGFACE_TOKEN')

def parse_job_data_llama(job_label):
    """
    Given a job experience label, return the experience range in months as a tuple.

    Parameters:
    - job_label (str): The experience label, e.g., "IC2"

    Returns:
    - tuple: (start_month, end_month) or ("unknown", "unknown")
    """
    job_description = job_label.split("_")[-1] if "_" in job_label else ""
    job_experience = job_label.split("_")[0] if "_" in job_label else job_label
    # Prompt to ensure consistent tuple output
    prompt_text = (
        "You are an assistant that extracts estimated years of experience (YOE) from job postings.\n\n"
    "Rules:\n"
    "1. If an explicit job level or experience label is provided (e.g., 'IC2', 'L4', 'SDE2', 'Junior', "
    "'2-3 years experience', etc.), use only that label to return the estimated range in months as a Python tuple.\n"
    "   Example mappings:\n"
    "   - '2+ years development experience' → (24, 500)\n"
    "   - '0-2 years development experience' → (0, 24)\n"
    "   - '0-2+ years development experience' → (0, 500)\n"
    "   - '5+ yrs experience' → (60, 500)\n"
    "   - '2-3 years experience' → (24, 36)\n\n"
    "2. If no explicit experience label is provided, carefully read the job description and infer the likely range "
    "based on context, role seniority, or keywords (e.g., 'entry-level' → (0, 24), 'senior engineer' → (60, 120), "
    "'lead' → (96, 500), etc.).\n\n"
    "3. If it is impossible to infer, return ('unknown', 'unknown').\n\n"
    "Output only the tuple. Do not include explanations, text, or formatting.\n\n"
    f"Input:\nExperience: \"{job_experience}\"\n\nJob Description: \"{job_description}\"\n\nOutput:"
    )

    # Setup LLM
    llm = ChatOpenAI(
        model="meta-llama/llama-3.1-8b-instruct",
        openai_api_key="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",  # use env variable, not hardcoded
        openai_api_base=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )

    # Build prompt and chain
    prompt_template = PromptTemplate.from_template("{prompt}")
    chain = prompt_template | llm | StrOutputParser()

    # Get model response
    response = chain.invoke({"prompt": prompt_text})

    # Parse the tuple safely
    try:
        result = ast.literal_eval(response.strip())
        if isinstance(result, tuple) and len(result) == 2:
            return result
        else:
            return ("unknown", "unknown")
    except Exception:
        return ("unknown", "unknown")

# Test the function
if __name__ == "__main__":
    job_label = "5+ years"
    parsed_result = parse_job_data_llama(job_label)
    print(parsed_result)
