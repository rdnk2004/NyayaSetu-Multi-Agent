"""
Unit tests for shared retrieval functionality in src/retrieve.py and src/retrieve_case_law.py.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import retrieve
from retrieve import retrieve as retrieve_statutes
from retrieve_case_law import retrieve_case_law


def test_retrieve_statutes_default_parameters():
    mock_model = MagicMock()
    mock_model.encode.return_value.tolist.return_value = [[0.1, 0.2, 0.3]]

    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "ids": [["chunk_1"]],
        "documents": [["Statutory text for section 35"]],
        "metadatas": [[{"section": "35", "title": "Filing"}]],
        "distances": [[0.12]],
    }

    with patch("retrieve._get_model", return_value=mock_model), \
         patch("retrieve._get_collection", return_value=mock_collection) as mock_get_col:
        hits = retrieve_statutes("filing complaint", top_k=5)

    mock_get_col.assert_called_once_with("legal_chunks")
    assert len(hits) == 1
    assert hits[0]["id"] == "chunk_1"
    assert hits[0]["metadata"]["section"] == "35"
    assert hits[0]["distance"] == 0.12


def test_retrieve_case_law_delegates_to_shared_retrieve():
    mock_hits = [
        {
            "id": "case_1",
            "text": "Judgment text...",
            "metadata": {"case_title": "Consumer v Seller"},
            "distance": 0.22,
        }
    ]

    with patch("retrieve_case_law.retrieve", return_value=mock_hits) as mock_shared_retrieve:
        hits = retrieve_case_law("vehicle defect", top_k=3)

    mock_shared_retrieve.assert_called_once_with(
        "vehicle defect",
        collection_name="case_law",
        top_k=3,
    )
    assert len(hits) == 1
    assert hits[0]["metadata"]["case_title"] == "Consumer v Seller"


def test_positional_top_k_defensive_handling():
    mock_model = MagicMock()
    mock_model.encode.return_value.tolist.return_value = [[0.1, 0.2]]

    mock_collection = MagicMock()
    mock_collection.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    with patch("retrieve._get_model", return_value=mock_model), \
         patch("retrieve._get_collection", return_value=mock_collection) as mock_get_col:
        # User or legacy code calls retrieve(query, 7) positionally
        retrieve_statutes("test query", 7)

    mock_get_col.assert_called_once_with("legal_chunks")
    mock_collection.query.assert_called_once_with(
        query_embeddings=[[0.1, 0.2]],
        n_results=7,
    )
