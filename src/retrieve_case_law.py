"""
Case Law Retrieval function

Given a plain-language query, returns the top-k most relevant case law entries
from the dedicated 'case_law' vector store collection. Follows the exact same
interface and return shape as retrieve.py for consistency across agents.
"""

from pathlib import Path

# pyrefly: ignore [missing-import]
import chromadb
# pyrefly: ignore [missing-import]
from sentence_transformers import SentenceTransformer

DB_PATH = Path(__file__).parent.parent / "data" / "chroma_db"
EMBEDDING_MODEL = "multi-qa-mpnet-base-dot-v1"
COLLECTION_NAME = "case_law"

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


def retrieve_case_law(query: str, top_k: int = 3) -> list[dict]:
    """Return the top_k case law entries most relevant to the query, with metadata."""
    model = _get_model()
    collection = _get_collection()

    query_embedding = model.encode([query]).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k,
    )

    hits = []
    if results and results.get("ids") and len(results["ids"]) > 0:
        for i in range(len(results["ids"][0])):
            hits.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
    return hits


if __name__ == "__main__":
    test_queries = [
        "liability of automobile manufacturer and dealer for manufacturing defect",
        "consumer forum jurisdiction over electricity assessment under section 126",
        "is expert opinion mandatory to prove defect in goods",
        "flight cancellation or delay compensation by airlines",
    ]

    for q in test_queries:
        results = retrieve_case_law(q, top_k=3)
        print(f"\nQuery: {q}")
        for r in results:
            print(f"  -> {r['metadata']['case_title']} "
                  f"({r['metadata']['court']}, {r['metadata']['date']}), distance={r['distance']:.4f}")
