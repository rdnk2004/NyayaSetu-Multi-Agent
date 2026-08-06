"""
Day 1 - Step 3: Retrieval function

Given a plain-language query, returns the top-k most relevant chunks
from the vector store. This is the function every later agent
(QA agent, Citation Verification agent, etc.) will call.
"""

from pathlib import Path

# pyrefly: ignore [missing-import]
import chromadb
# pyrefly: ignore [missing-import]
from sentence_transformers import SentenceTransformer

DB_PATH = Path(__file__).parent.parent / "data" / "chroma_db"
EMBEDDING_MODEL = "multi-qa-mpnet-base-dot-v1"
COLLECTION_NAME = "legal_chunks"

_model = None
_collection = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(DB_PATH))
        _collection = client.get_collection(COLLECTION_NAME)
    return _collection


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Return the top_k chunks most relevant to the query, with metadata."""
    model = _get_model()
    collection = _get_collection()

    query_embedding = model.encode([query]).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k,
    )

    hits = []
    for i in range(len(results["ids"][0])):
        hits.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })
    return hits


if __name__ == "__main__":
    # Sanity-test queries - this is the shape of your formal gate test
    # tomorrow, just with fewer queries for a quick check today.
    test_queries = [
        "what counts as a deficiency in service",
        "how long do I have to file a consumer complaint",
        "which commission handles a complaint about a one lakh rupee product",
        "what remedies can the District Commission order",
        "who counts as a consumer under the Act",
    ]

    for q in test_queries:
        results = retrieve(q, top_k=5)
        print(f"\nQuery: {q}")
        for r in results:
            print(f"  -> Section {r['metadata']['section']} "
                  f"({r['metadata']['title']}), distance={r['distance']:.4f}")
