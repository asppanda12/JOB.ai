from langchain_huggingface import HuggingFaceEmbeddings
import json
import pandas as pd
import math
from uuid import uuid4
import faiss
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS

from langchain_core.documents import Document


embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")


index = faiss.IndexFlatL2(len(embeddings.embed_query("hello world")))

vector_store = FAISS(
    embedding_function=embeddings,
    index=index,
    docstore=InMemoryDocstore(),
    index_to_docstore_id={},
)


import json

# Path to your JSON file
file_path = r"E:\JOB.ai\JOB.ai\combined_single_data\concatenated_jobs.json"

# Reading the JSON file
with open(file_path, "r") as file:
    Job_data = json.load(file)




for job in Job_data:
    yoe = job.get('yoe')  # Safely get 'yoe' key
    if yoe is None or (isinstance(yoe, float) and math.isnan(yoe)):  # Check for None or NaN
        job['yoe'] = "0,60"  # Default range
    elif isinstance(yoe, (list, tuple)) and len(yoe) == 2:  # Ensure it's a list/tuple with two values
        job['yoe'] = ",".join(map(str, yoe))  # Convert list/tuple to a string


file_path_1 = r"E:\JOB.ai\JOB.ai\resume_cold_mail\Ruddhis_job.json"


with open(file_path_1, "r") as file:
    resume_data = json.load(file)

print(resume_data)
query_data=(" ").join(resume_data['area_of_expertise'])+" "+(" ").join(resume_data['Skills'])+" "+"Hyderabad"

print(query_data)

documents=[]
for data in Job_data:
  document_1 = Document(
    page_content=data['text'],
    metadata=data,
    id=data['id'],)
  documents.append(document_1)
uuids = [str(uuid4()) for _ in range(len(documents))]


vector_store.add_documents(documents=documents, ids=uuids)

results = vector_store.similarity_search(query=query_data, k=500)

# List to store the results in JSON format
# json_data = []

# # Loop through the results and collect metadata and score
# for res, score in results:
#     json_data.append({
#         "metadata": res.metadata,  # Add metadata directly
#         "score": score             # Add the score
#     })

# # Sort the results by score in descending order
# json_data.sort(key=lambda x: x["score"], reverse=True)
import json
yoe_mera=1.5
filtered_results = []
for document in results:
    metadata = document.metadata
    yoe = metadata.get("yoe", None)

    if yoe:
        try:
            yoe_min, yoe_max = map(float, yoe.split(","))
            if yoe_min <= yoe_mera <= yoe_max:
                # Convert Document to a serializable dictionary
                filtered_results.append({
                    "page_content": document.page_content,
                    "metadata": document.metadata,
                })
        except ValueError:
            print("Error in parsing 'yoe' value")

# Write the results to a JSON file
with open("search_results_ruddhi.json", "w") as json_file:
    json.dump(filtered_results, json_file, indent=4)  # Pretty print the results
