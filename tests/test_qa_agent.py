"""
Unit tests for the QA Agent (src/qa_agent.py).
Mocks retrieve and call_llm_structured to verify:
  (1) A normal case returns an answer citing a real section
  (2) A case with no relevant retrieved chunks returns status 'unclear'
  (3) Malformed LLM JSON output is handled fail-safe without crashing

Run: PYTHONPATH=src python tests/test_qa_agent.py
     or: PYTHONPATH=src pytest
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure src is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from qa_agent import answer_question


def test_normal_case_returns_answer_with_citations():
    case_brief = {
        "domain": "Consumer Protection",
        "facts": {
            "what_was_bought_or_hired": "Washing machine",
            "what_went_wrong": "Arrived with a broken drum and seller refused replacement",
            "amount_paid": "25000 INR",
            "seller_or_provider": "ABC Appliances",
        },
        "ready": True,
    }

    mock_chunks = [
        {
            "id": "chunk_0010",
            "text": "Deficiency means any fault, imperfection, shortcoming or inadequacy in the quality...",
            "metadata": {
                "section": "2(11)",
                "title": "Deficiency in service",
                "source_act": "Consumer Protection Act, 2019",
            },
            "distance": 0.15,
        },
        {
            "id": "chunk_0035",
            "text": "A complaint in relation to any goods sold or delivered... may be filed with a District Commission.",
            "metadata": {
                "section": "35",
                "title": "Manner in which complaint shall be made",
                "source_act": "Consumer Protection Act, 2019",
            },
            "distance": 0.28,
        },
    ]

    llm_payload = {
        "answer": "Under Section 2(11) of the Consumer Protection Act, 2019, receiving defective goods constitutes a deficiency. You can file a formal complaint before the District Commission under Section 35.",
        "cited_sections": ["Section 2(11)", "Section 35"],
        "status": "answered",
    }

    with patch("qa_agent.retrieve", return_value=mock_chunks) as mock_retrieve, \
         patch("qa_agent.call_llm_structured", return_value=json.dumps(llm_payload)) as mock_llm:
        result = answer_question(case_brief)

    assert result["status"] == "answered", f"Expected status 'answered', got {result['status']}"
    assert "2(11)" in result["cited_sections"]
    assert "35" in result["cited_sections"]
    assert len(result["answer"]) > 0
    assert mock_retrieve.called
    assert mock_retrieve.call_args[1]["top_k"] == 5
    assert mock_llm.called
    print("  Normal case test passed: Successfully answered with valid citations.")


def test_no_relevant_retrieved_chunks_returns_unclear():
    case_brief = {
        "domain": "Consumer Protection",
        "facts": {
            "what_was_bought_or_hired": "Cryptocurrency investment advice",
            "what_went_wrong": "Lost money on volatile coin trading",
        },
        "ready": True,
    }

    # Case A: Irrelevant chunks retrieved, LLM flags unclear
    mock_chunks = [
        {
            "id": "chunk_0090",
            "text": "The Central Authority may establish a Central Consumer Protection Council...",
            "metadata": {
                "section": "3",
                "title": "Central Consumer Protection Council",
                "source_act": "Consumer Protection Act, 2019",
            },
            "distance": 0.92,
        }
    ]

    llm_payload = {
        "answer": "The retrieved provisions do not address cryptocurrency trading or investment risk under this Act.",
        "cited_sections": [],
        "status": "unclear",
    }

    with patch("qa_agent.retrieve", return_value=mock_chunks), \
         patch("qa_agent.call_llm_structured", return_value=json.dumps(llm_payload)):
        result = answer_question(case_brief)

    assert result["status"] == "unclear", f"Expected status 'unclear', got {result['status']}"
    assert result["cited_sections"] == []

    # Case B: Retrieval returns empty list of chunks
    with patch("qa_agent.retrieve", return_value=[]):
        empty_res = answer_question(case_brief)

    assert empty_res["status"] == "unclear"
    assert empty_res["cited_sections"] == []
    print("  No relevant chunks test passed: Correctly returned 'unclear' status.")


def test_malformed_llm_json_handled_without_crashing():
    case_brief = {
        "domain": "Consumer Protection",
        "facts": {
            "what_was_bought_or_hired": "Smartphone",
            "what_went_wrong": "Screen defective on delivery",
        },
        "ready": True,
    }

    mock_chunks = [
        {
            "id": "chunk_0010",
            "text": "Deficiency in service provisions...",
            "metadata": {"section": "2(11)", "title": "Deficiency"},
            "distance": 0.1,
        }
    ]

    malformed_outputs = [
        "This is not JSON at all and would crash a naive json.loads call",
        "{malformed_json: missing_quotes,",
        "```json\n{\"answer\": \"incomplete json\"\n",
        "",
        "None",
        json.dumps(["not a dict", "list instead"]),
    ]

    for bad_output in malformed_outputs:
        with patch("qa_agent.retrieve", return_value=mock_chunks), \
             patch("qa_agent.call_llm_structured", return_value=bad_output):
            result = answer_question(case_brief)

        assert isinstance(result, dict), "Result must always be a dict"
        assert result["status"] == "unclear", f"Malformed output should result in status 'unclear', got {result['status']}"
        assert result["cited_sections"] == []
        assert isinstance(result["answer"], str)

    print("  Malformed JSON test passed: Handled corrupt outputs fail-safe without crashing.")


def test_empty_or_invalid_case_brief():
    # Defensive handling of invalid inputs
    res_none = answer_question(None)
    assert res_none["status"] == "unclear"

    res_empty = answer_question({})
    assert res_empty["status"] == "unclear"

    res_no_facts = answer_question({"domain": "Consumer Protection", "facts": {}})
    assert res_no_facts["status"] == "unclear"
    print("  Invalid input edge cases passed.")


if __name__ == "__main__":
    tests = [
        test_normal_case_returns_answer_with_citations,
        test_no_relevant_retrieved_chunks_returns_unclear,
        test_malformed_llm_json_handled_without_crashing,
        test_empty_or_invalid_case_brief,
    ]
    print("\nRunning QA Agent Unit Tests:")
    for t in tests:
        print(f"\n{t.__name__}:")
        t()
    print("\nAll QA Agent tests passed successfully!")
