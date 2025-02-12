from dotenv import load_dotenv
import os
import sys
sys.path.append('E:/JOB.ai/JOB.ai')  
from Data_base.faiss_db_v2 import JobSearchEngine
chat_id=1777168886
vector_path=r'E:\JOB.ai\JOB.ai\vector_store'
search_engine = JobSearchEngine(vector_store_path=vector_path)
search_engine.query(chat_id)