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
chat_id=7748640302
data_base=create_a_job_database_specific_user(os.getenv('MONGO_DB_URI'))
document = data_base.find_one({'chat_id': chat_id})
import pandas as pd
print(f"Document for chat_id {chat_id}: {document}")
print(document)
if document:
    df = pd.DataFrame([doc['metadata'] for doc in document['job_recommendation']])

    df.to_csv(f"chat_id_{chat_id}_metadata.csv", index=False)