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

    # Prompt to ensure consistent tuple output
    prompt_text = (
        'You are given a job level or experience label (e.g., "IC2", "L4", "SDE2", "Junior", etc.).\n'
        'Based only on this label and without making assumptions beyond what the label directly suggests, '
        'return the estimated range of experience in months as a Python tuple: (start_month, end_month).\n'
        'If the label is ambiguous or not clearly mapped to a duration, return ("unknown", "unknown").\n\n'
        'Only return the tuple. Do not write code, explanations, or formatting.\n\n'
        '1. Example: 2+ years development experience → (24, 500).\n'
        '2. Example: 0-2 years development experience → (0, 24).\n'
        '3. Example: 0-2+ years development experience → (0, 500).\n'
        '4. Example: 5+ yrs experience → (60, 500).\n\n'
        '5. Example: 2-3 years experience → (24, 36).\n\n'

        f'Input:\n"Experience": "{job_label}"\n\nOutput:'
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
