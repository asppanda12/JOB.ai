import logging
from datetime import datetime
import json
import pandas as pd
import re
import chromadb
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from uuid import uuid4
import math

# Configure logging
logging.basicConfig(
    filename=r"E:\JOB.ai\JOB.ai\log_data\job_ai_log.log", 
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

try:
    logging.info("Script started.")

    # Initialize embeddings
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")
    logging.info("HuggingFace embeddings model initialized.")

    # Load Job data
    file_path = r"E:\JOB.ai\JOB.ai\combined_single_data\concatenated_jobs.json"
    yoe_mera = 1.5
    with open(file_path, "r") as file:
        Job_data = json.load(file)
    logging.info(f"Loaded job data from {file_path}.")

    # Clean up job experience (yoe) data
    for job in Job_data:
        if job['yoe'] == float('nan') or job['yoe'] != job['yoe']:  # Check for NaN
            job['yoe'] = (0, 60)
    logging.info("Processed job 'yoe' data for NaN values.")

    # Load resume data
    file_path_resume = r'E:\JOB.ai\JOB.ai\resume_cold_mail\j210250.json'
    with open(file_path_resume, "r") as file:
        resume_data = json.load(file)
    logging.info(f"Loaded resume data from {file_path_resume}.")

    query_data = (
        " ".join(resume_data['area_of_expertise']) + " " +
        " ".join(resume_data['Skills']) + 
        " Hyderabad"
    )
    logging.info("Query data prepared from resume.")

    # Initialize Chroma and filter jobs
    persistent_client = chromadb.PersistentClient()
    collection = persistent_client.get_or_create_collection("JOB_AI")
    vector_store_from_client = Chroma(
        client=persistent_client,
        collection_name="JOB_AI",
        embedding_function=embeddings,
    )
    logging.info("Chroma vector store initialized.")
#     persistent_client = chromadb.PersistentClient(path=r"E:\JOB.ai\JOB.ai\Data_base\chroma")

# # Load or Create Collection
#     collection_name = "JOB_AI"
#     vector_store_from_client = persistent_client.get_or_create_collection(collection_name)
#     logging.info(f"Chroma collection '{collection_name}' initialized.")


    # filtered_jobs = [
    # job for job in Job_data
    # if job['yoe'] is not None and job['yoe'][0] <= yoe_mera <= job['yoe'][1]
    # ]
    # logging.info(f"Filtered jobs based on 'yoe': {len(filtered_jobs)} jobs found.")


    # Convert filtered job 'yoe' to strings and prepare documents
    for job in Job_data:
        yoe = job.get('yoe')  # Safely get 'yoe' key
        if yoe is None or (isinstance(yoe, float) and math.isnan(yoe)):  # Check for None or NaN
            job['yoe'] = "0,60"  # Default range
        elif isinstance(yoe, (list, tuple)) and len(yoe) == 2:  # Ensure it's a list/tuple with two values
            job['yoe'] = ",".join(map(str, yoe))  # Convert list/tuple to a string
    documents = []
    for data in Job_data:
        document_1 = Document(
            page_content=data['text'],
            metadata=data,
            id=data['id'],
        )
        documents.append(document_1)
    uuids = [str(uuid4()) for _ in range(len(documents))]
    logging.info("Prepared documents for vector store.")

    # Add documents to the vector store
    vector_store_from_client.add_documents(documents=documents, ids=uuids)
    logging.info("Added documents to the vector store.")
    yoe_mera
    # Perform similarity search
    results = vector_store_from_client.similarity_search_with_score(query=query_data, k=500)
    json_data = []
    logging.info(f"Performed similarity search. Found {len(results)} results.")
    for res, score in results:
        json_data.append({
            "metadata": res.metadata,  # Add metadata directly
            "score": score             # Add the score
        })
    json_data.sort(key=lambda x: x["score"], reverse=True)
    filtered_json_data = []
    for item in json_data:
        metadata = item.get("metadata", {})
        yoe = metadata.get("yoe", None)  # Safely fetch 'yoe' from metadata
        if yoe is not None and isinstance(yoe, str):  # Ensure 'yoe' is a string
            try:
                # Split 'yoe' into min and max values and convert them to floats
                yoe_min, yoe_max = map(float, yoe.split(","))
                # Check if 'yoe_mera' falls within the range
                if yoe_min <= yoe_mera <= yoe_max:
                    filtered_json_data.append(item)
            except ValueError:
                continue



    logging.info(f"Filtered jobs based on 'yoe': {len(results)} jobs found.")


    # Prepare and save JSON results
    
    output_path = r"E:\JOB.ai\JOB.ai\result\search_results1.json"
    with open(output_path, "w") as json_file:
        json.dump(filtered_json_data, json_file, indent=4)
    logging.info(f"Search results saved to {output_path}.")

    # Print results to console
    for res, score in results:
        print(f"* [SIM={score:3f}] {res.page_content} [{res.metadata}]")

    logging.info("Script execution completed successfully.")

except Exception as e:
    logging.error(f"An error occurred: {e}")
    raise
