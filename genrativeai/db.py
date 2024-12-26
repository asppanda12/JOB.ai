import chromadb
chroma_client = chromadb.Client()

# switch `create_collection` to `get_or_create_collection` to avoid creating a new collection every time
collection = chroma_client.get_or_create_collection(name="my_collection")

# switch `add` to `upsert` to avoid adding the same documents every time
collection.upsert(
    documents=[
        "This is a document about Delhi",
        "This is a document about New York"
    ],
    ids=["id1", "id2"]
)

results = collection.query(
    query_texts=["This is a query document about usa"], # Chroma will embed this for you
    n_results=2 # how many results to return
)

print(results)
