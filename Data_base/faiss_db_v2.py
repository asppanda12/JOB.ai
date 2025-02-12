import json
import math
from uuid import uuid4
import json
import os
import shutil

import sys
sys.path.append('E:/JOB.ai/JOB.ai')  
import faiss
from datetime import datetime
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from dotenv import load_dotenv
from Data_base.mongodb import create_a_job_database,create_a_database,create_a_job_database_specific_user
load_dotenv()
from pymongo import MongoClient
uri = os.getenv("MONGO_DB_URI")
class JobSearchEngine:
    def __init__(self, json_data=None, embeddings_model="sentence-transformers/all-mpnet-base-v2", vector_store_path=None):
        self.embeddings = HuggingFaceEmbeddings(model_name=embeddings_model)
        
        if vector_store_path:
            # Load the vector store from disk if a path is provided
            self.vector_store = self._load_vector_store(vector_store_path)
        else:
            # Initialize a new vector store and populate it with job data
            self.vector_store = self._initialize_vector_store()
            if json_data:
                self.job_data = self._load_and_preprocess_job_data(json_data)
                self._populate_vector_store()

    def _initialize_vector_store(self):
        index = faiss.IndexFlatL2(len(self.embeddings.embed_query("hello world")))
        return FAISS(
            embedding_function=self.embeddings,
            index=index,
            docstore=InMemoryDocstore(),
            index_to_docstore_id={},
        )

    def _load_and_preprocess_job_data(self, job_data):
        # with open(job_data_path, "r") as file:
        #     job_data = json.load(file)

        for job in job_data:
            yoe = job['yoe']
            if yoe is None or (isinstance(yoe, float) and math.isnan(yoe)):
                job['yoe'] = "0,60"
            elif isinstance(yoe, (list, tuple)) and len(yoe) == 2:
                job['yoe'] = ",".join(map(str, yoe))

        return job_data

    def _populate_vector_store(self):
        documents = []
        for data in self.job_data:
            document = Document(
                page_content=data['text'],
                metadata=data,
                id=data['id'],
            )
            documents.append(document)

        uuids = [str(uuid4()) for _ in range(len(documents))]
        self.vector_store.add_documents(documents=documents, ids=uuids)

    def save_vector_store(self, save_path):
        """Save the FAISS vector store to disk."""
        self.vector_store.save_local(save_path)

    def _load_vector_store(self, load_path):
        """Load the FAISS vector store from disk."""
        return FAISS.load_local(load_path, self.embeddings, allow_dangerous_deserialization=True)


    def query(self, chat_id, k=500):
        data_base=create_a_database(os.getenv('MONGO_DB_URI'))
        document = data_base.find_one({'chat_id': chat_id})
        resume_data=document['resume_json']
        yoe_mera=document['years_of_experience']
        query_data = (" ").join(resume_data['area_of_expertise']) + " " + (" ").join(resume_data['Skills']) + " " + "Hyderabad"
        results = self.vector_store.similarity_search(query=query_data, k=k)

        filtered_results = []
        for document in results:
            metadata = document.metadata
            yoe = metadata.get("yoe", None)

            if yoe:
                try:
                    yoe_min, yoe_max = map(float, yoe.split(","))
                    if yoe_min <= yoe_mera <= yoe_max:
                        filtered_results.append({
                            "page_content": document.page_content,
                            "metadata": document.metadata,
                        })
                except ValueError:
                    print("Error in parsing 'yoe' value")
        self.save_results_to_mongo_db(chat_id,filtered_results)
        print(f"All datas are inserted for {chat_id}")
    def delete_results_for_chat_id(self,data_base,chat_id):
        result = data_base.delete_many({"chat_id": chat_id})  # Delete all matching documents
        print(f"Deleted {result.deleted_count} documents for chat_id: {chat_id}")
    def save_results_to_json(self, results, output_path):
        with open(output_path, "w") as json_file:
            json.dump(results, json_file, indent=4)
    
    def save_results_to_mongo_db(self, chat_id, results):
        data_base = create_a_job_database_specific_user(os.getenv('MONGO_DB_URI'))
        self.delete_results_for_chat_id(data_base,chat_id)
        document = {
            "chat_id": chat_id,
            "job_recommendation": results
        }

        data_base.insert_one(document)  
def json_serializable(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()  # Convert datetime to ISO 8601 format string
    raise TypeError(f"Type {type(obj)} not serializable")

# Example usage
if __name__ == "__main__":
    db=create_a_job_database(uri)
    data = list(db.find({}, {"_id": 0}))
    json_data = data

    print(json_data[0])
    print("going to search for vector")
    # job_data_path = r"E:\JOB.ai\JOB.ai\combined_single_data\concatenated_jobs.json"
    # resume_data_path = r"E:\JOB.ai\JOB.ai\resume_cold_mail\Ruddhis_job.json"
    vector_store_path = r"E:\JOB.ai\JOB.ai\vector_store"  # Directory to save/load the vector store
    if os.path.exists(vector_store_path):
        shutil.rmtree(vector_store_path)  # Delete the directory and all its contents
        print(f"Deleted directory: {vector_store_path}")
    else:
        print("Directory does not exist.")
    if os.path.exists(vector_store_path) and os.path.isdir(vector_store_path):
        print("Vector store path exists. Proceeding with initialization.")
        search_engine = JobSearchEngine(json_data=json_data, vector_store_path=vector_store_path)
    else:
        print("Vector store path does not exist. Handle accordingly.")
        # You can create it if needed:
        
        search_engine = JobSearchEngine(json_data=json_data)
    # # Initialize the search engine

    # # Save the vector store to disk (only needed once)
    search_engine.save_vector_store(vector_store_path)

    # # Load the vector store from disk (for subsequent runs)
    # search_engine = JobSearchEngine(vector_store_path=vector_store_path)

    # # Query the vector store
    # with open(resume_data_path, "r") as file:
    #     resume_data = json.load(file)

    # yoe_mera = 1.5
    # results = search_engine.query(resume_data, yoe_mera)
    # search_engine.save_results_to_json(results, "search_results_ruddhi.json")