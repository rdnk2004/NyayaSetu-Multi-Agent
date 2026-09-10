import chromadb
client = chromadb.PersistentClient(path="data/chroma_db")
collection = client.get_collection("legal_chunks")
all_data = collection.get(include=["metadatas"])
suspicious = [m for m in all_data["metadatas"] if m.get("source_act") != "Consumer Protection Act, 2019"]
print(f"Total entries in legal_chunks: {len(all_data['metadatas'])}")
print(f"Entries NOT matching expected source_act: {len(suspicious)}")
for s in suspicious[:5]:
    print(s)