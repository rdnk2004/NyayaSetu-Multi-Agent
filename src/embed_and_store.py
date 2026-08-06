"""
Day 1 - Step 2: Embed chunks and load them into a vector store

Reads data/processed/chunks.json (produced by chunk_text.py) and:
  1. Turns each chunk's text into an embedding (a list of numbers
     representing its meaning) using a local, free model.
  2. Stores the embedding + text + metadata in Chroma, a local vector
     database, so we can later search "which chunks mean something
     similar to this query" instead of just keyword-matching.
"""

import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

CHUNKS_PATH = Path(__file__).parent.parent / "data" / "processed" / "chunks.json"
DB_PATH = Path(__file__).parent.parent / "data" / "chroma_db"


# Swap this later if retrieval quality is weak on real legal language.
EMBEDDING_MODEL = "multi-qa-mpnet-base-dot-v1"
COLLECTION_NAME = "legal_chunks"


def build_vector_store():
    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(chunks)} chunks from {CHUNKS_PATH}")

    print(f"Loading embedding model: {EMBEDDING_MODEL} (first run downloads it)...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    client = chromadb.PersistentClient(path=str(DB_PATH))

    # Start fresh each run during dev, so re-running this script doesn't
    # duplicate chunks in the store.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "ip"})

    texts = [c["text"] for c in chunks]
    ids = [c["id"] for c in chunks]
    metadatas = [
        {
            "source_act": c["source_act"],
            "section": c["section"],
            "title": c["title"],
            "as_of_date": c["as_of_date"],
        }
        for c in chunks
    ]

    print("Generating embeddings...")
    embeddings = model.encode(texts, show_progress_bar=False).tolist()

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    print(f"Stored {collection.count()} chunks in Chroma at {DB_PATH}")


if __name__ == "__main__":
    build_vector_store()
