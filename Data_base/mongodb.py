
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi



def create_a_database(str_uri):
    uri = str_uri
    client = MongoClient(uri, server_api=ServerApi('1'))
    try:
        client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB!")
        db=client['USER']
        table=db['JOB_USER']
        return table
    except Exception as e:
        print(e)
    
def create_a_job_database(str_uri):
    uri = str_uri
    client = MongoClient(uri, server_api=ServerApi('1'),tls=True)
    try:
        client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB!")
        db=client['USER_1']
        table=db['JOB_Data']
        return table
    except Exception as e:
        print(e)
def create_a_job_database_specific_user(str_uri):
    uri = str_uri
    client = MongoClient(uri, server_api=ServerApi('1'),tls=True)
    try:
        client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB!")
        db=client['USER_1']
        table=db['Job_specific']
        print("Database and collection created successfully.")
        return table
    except Exception as e:
        print(e)
# create_a_job_database_specific_user = create_a_job_database_specific_user('mongodb+srv://sameerpandausa:5MC349oicChL7zXN@cluster0.ggine.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tls=true&tlsAllowInvalidCertificates=true')