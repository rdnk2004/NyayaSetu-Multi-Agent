"""
Case Law Retrieval function

Given a plain-language query, returns the top-k most relevant case law entries
from the dedicated 'case_law' vector store collection. Follows the exact same
interface and return shape as retrieve.py for consistency across agents.
"""

from config import (
    CASE_LAW_COLLECTION_NAME,
    LANDMARK_CASE_TOP_K,
)
from pii_redaction import redact_pii
from retrieve import retrieve


def retrieve_case_law(query: str, top_k: int = LANDMARK_CASE_TOP_K) -> list[dict]:
    """Return the top_k case law entries most relevant to the query, with metadata."""
    return retrieve(query, collection_name=CASE_LAW_COLLECTION_NAME, top_k=top_k)


if __name__ == "__main__":
    test_queries = [
        "liability of automobile manufacturer and dealer for manufacturing defect",
        "consumer forum jurisdiction over electricity assessment under section 126",
        "is expert opinion mandatory to prove defect in goods",
        "flight cancellation or delay compensation by airlines",
    ]

    for q in test_queries:
        results = retrieve_case_law(q, top_k=3)
        print(f"\nQuery: {redact_pii(q)}")
        for r in results:
            print(f"  -> {r['metadata']['case_title']} "
                  f"({r['metadata']['court']}, {r['metadata']['date']}), distance={r['distance']:.4f}")
