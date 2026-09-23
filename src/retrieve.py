"""
Day 1 - Step 3: Retrieval function

Given a plain-language query, returns the top-k most relevant chunks
from the vector store. This is the function every later agent
(QA agent, Citation Verification agent, etc.) will call.
"""

import json
import logging
from pathlib import Path
from typing import Any

from config import (
    CHROMA_DB_PATH,
    EMBEDDING_MODEL,
    STATUTE_COLLECTION_NAME,
    QA_RETRIEVAL_TOP_K,
)
from pii_redaction import redact_pii

logger = logging.getLogger(__name__)

# pyrefly: ignore [missing-import]
import chromadb
# pyrefly: ignore [missing-import]
from sentence_transformers import SentenceTransformer

DB_PATH = CHROMA_DB_PATH
COLLECTION_NAME = STATUTE_COLLECTION_NAME

_model = None
_client = None
_collections: dict[str, Any] = {}
_collection = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _get_collection(collection_name: str = STATUTE_COLLECTION_NAME):
    global _client, _collections, _collection
    if collection_name not in _collections:
        if _client is None:
            _client = chromadb.PersistentClient(path=str(DB_PATH))
        _collections[collection_name] = _client.get_collection(collection_name)
    if collection_name == STATUTE_COLLECTION_NAME:
        _collection = _collections[collection_name]
    return _collections[collection_name]


def retrieve(
    query: str,
    collection_name: str = STATUTE_COLLECTION_NAME,
    top_k: int = QA_RETRIEVAL_TOP_K,
) -> list[dict]:
    """Return the top_k chunks most relevant to the query from the specified Chroma collection."""
    # Defensive handling in case top_k is passed positionally as second argument
    if isinstance(collection_name, int):
        top_k = collection_name
        collection_name = STATUTE_COLLECTION_NAME

    model = _get_model()
    collection = _get_collection(collection_name)

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


_CORPUS_CHUNKS_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "chunks.json"
_SIBLINGS_BY_SECTION: dict[str, list[dict]] | None = None


def _load_sibling_map() -> dict[str, list[dict]]:
    """Load corpus chunks indexed by section string for fast sibling lookup."""
    global _SIBLINGS_BY_SECTION
    if _SIBLINGS_BY_SECTION is not None:
        return _SIBLINGS_BY_SECTION

    sibling_map: dict[str, list[dict]] = {}
    if _CORPUS_CHUNKS_PATH.exists():
        try:
            with open(_CORPUS_CHUNKS_PATH, "r", encoding="utf-8") as f:
                raw_chunks = json.load(f)
            for c in raw_chunks:
                sec = str(c.get("section", "")).strip()
                if not sec:
                    continue
                sibling_map.setdefault(sec, []).append(c)
            # Sort each section's siblings by id/part to guarantee correct reading order
            for sec, s_list in sibling_map.items():
                s_list.sort(key=lambda x: str(x.get("id", "")))
        except Exception as e:
            logger.warning("Could not load chunks.json for sibling stitching: %s", e)

    _SIBLINGS_BY_SECTION = sibling_map
    return _SIBLINGS_BY_SECTION


def stitch_sibling_chunks(chunks: list[dict]) -> list[dict]:
    """
    Given a list of retrieved chunks, if any chunk's statutory section is split into
    multiple parts in the corpus (e.g. Section 2(47), 18, 38(2), 39(1), 101, 102),
    stitch all sibling parts together into a unified chunk so sub-clauses are not missed.
    Deduplicates sections so a stitched section appears once at its best retrieved rank.
    """
    if not chunks:
        return []

    sibling_map = _load_sibling_map()
    if not sibling_map:
        return chunks

    stitched_results: list[dict] = []
    seen_sections: set[str] = set()

    for chunk in chunks:
        meta = chunk.get("metadata") or {}
        sec = str(meta.get("section", "")).strip()
        if not sec:
            stitched_results.append(chunk)
            continue

        if sec in seen_sections:
            # Sibling already stitched and added at higher rank
            continue

        siblings = sibling_map.get(sec, [])
        if len(siblings) > 1:
            full_text = "\n\n".join(ch.get("text", "").strip() for ch in siblings if ch.get("text"))
            stitched_chunk = dict(chunk)
            stitched_chunk["text"] = full_text
            stitched_meta = dict(meta)
            stitched_meta["part"] = f"1/1 (stitched from {len(siblings)} parts)"
            stitched_chunk["metadata"] = stitched_meta
            stitched_results.append(stitched_chunk)
            seen_sections.add(sec)
        else:
            stitched_results.append(chunk)
            seen_sections.add(sec)

    return stitched_results


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
        print(f"\nQuery: {redact_pii(q)}")
        for r in results:
            print(f"  -> Section {r['metadata']['section']} "
                  f"({r['metadata']['title']}), distance={r['distance']:.4f}")
