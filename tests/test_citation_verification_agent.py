"""
Unit tests for Citation Verification Agent.
Verifies citation matching against retrieved chunks and LLM support validation.

Run:
  python tests/test_citation_verification_agent.py
or
  pytest tests/test_citation_verification_agent.py
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure src directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import citation_verification_agent
from citation_verification_agent import (
    verify_citations,
    UNVERIFIED_FALLBACK_ANSWER,
)


def test_all_citations_verified():
    """Test (1): All citations exist in retrieved chunks and are supported by LLM -> original answer passes through."""
    qa_result = {
        "answer": "Under Section 2(11), deficiency means any fault, imperfection, or shortcoming in quality or standard.",
        "cited_sections": ["2(11)"],
        "status": "answered",
    }
    retrieved_chunks = [
        {
            "id": "chunk_0010",
            "text": "deficiency means any fault, imperfection, shortcoming or inadequacy in the quality, nature and manner of performance...",
            "metadata": {
                "section": "2(11)",
                "title": "Definitions",
                "source_act": "Consumer Protection Act, 2019",
            },
        }
    ]

    mock_llm_response = json.dumps({
        "is_supported": True,
        "reason": "The definition of deficiency in Section 2(11) explicitly covers fault and imperfection."
    })

    with patch("citation_verification_agent.call_llm_structured", return_value=mock_llm_response):
        result = verify_citations(qa_result, retrieved_chunks)

    assert result["verified"] is True
    assert result["verified_sections"] == ["2(11)"]
    assert result["rejected_sections"] == []
    assert result["details"]["2(11)"]["supported"] is True
    assert "fault and imperfection" in result["details"]["2(11)"]["reason"]
    assert result["final_answer"] == qa_result["answer"]
    print("  Test 1 passed: All citations verified -> original answer retained.")


def test_citation_not_in_retrieved_chunks():
    """Test (2): A citation to a section NOT in retrieved_chunks -> rejected, final_answer becomes safe fallback."""
    qa_result = {
        "answer": "Under Section 999, consumers are entitled to a full refund within 30 days.",
        "cited_sections": ["999"],
        "status": "answered",
    }
    retrieved_chunks = [
        {
            "id": "chunk_0020",
            "text": "Section 35 provides for manner in which complaint shall be made...",
            "metadata": {
                "section": "35",
                "title": "Manner in which complaint shall be made",
            },
        }
    ]

    with patch("citation_verification_agent.call_llm_structured") as mock_llm:
        result = verify_citations(qa_result, retrieved_chunks)
        # LLM should not even be called since Section 999 is not in retrieved_chunks
        assert mock_llm.call_count == 0

    assert result["verified"] is False
    assert result["verified_sections"] == []
    assert result["rejected_sections"] == ["999"]
    assert result["details"]["999"]["supported"] is False
    assert "not found in retrieved chunks" in result["details"]["999"]["reason"]
    assert result["final_answer"] == UNVERIFIED_FALLBACK_ANSWER
    print("  Test 2 passed: Unretrieved section rejected without LLM call -> safe fallback returned.")


def test_citation_unsupported_by_chunk_text():
    """Test (3): Citation is in retrieved chunks, but chunk text does NOT support the claim -> rejected."""
    qa_result = {
        "answer": "According to Section 35, the District Commission can award criminal imprisonment for simple deficiency.",
        "cited_sections": ["35"],
        "status": "answered",
    }
    retrieved_chunks = [
        {
            "id": "chunk_0025",
            "text": "A complaint, in relation to any goods sold or delivered or agreed to be sold or delivered or any service provided or agreed to be provided, may be filed with a District Commission...",
            "metadata": {
                "section": "35",
                "title": "Manner in which complaint shall be made",
            },
        }
    ]

    mock_llm_response = json.dumps({
        "is_supported": False,
        "reason": "Section 35 only specifies how and by whom a complaint may be filed, not criminal penalties."
    })

    with patch("citation_verification_agent.call_llm_structured", return_value=mock_llm_response):
        result = verify_citations(qa_result, retrieved_chunks)

    assert result["verified"] is False
    assert result["verified_sections"] == []
    assert result["rejected_sections"] == ["35"]
    assert result["details"]["35"]["supported"] is False
    assert "criminal penalties" in result["details"]["35"]["reason"]
    assert result["final_answer"] == UNVERIFIED_FALLBACK_ANSWER
    print("  Test 3 passed: Unsupported claim rejected by LLM audit -> safe fallback returned.")


def test_mixed_citations_partial_failure():
    """Test (4): One citation valid/supported, one citation not retrieved -> overall result rejected."""
    qa_result = {
        "answer": "Deficiency is defined in Section 2(11) and penalty is under Section 999.",
        "cited_sections": ["2(11)", "999"],
        "status": "answered",
    }
    retrieved_chunks = [
        {
            "id": "chunk_0010",
            "text": "deficiency means any fault, imperfection, shortcoming...",
            "metadata": {"section": "2(11)"},
        }
    ]

    mock_llm_response = json.dumps({
        "is_supported": True,
        "reason": "Section 2(11) supports definition."
    })

    with patch("citation_verification_agent.call_llm_structured", return_value=mock_llm_response):
        result = verify_citations(qa_result, retrieved_chunks)

    assert result["verified"] is False
    assert result["verified_sections"] == ["2(11)"]
    assert result["rejected_sections"] == ["999"]
    assert result["details"]["2(11)"]["supported"] is True
    assert result["details"]["999"]["supported"] is False
    assert result["final_answer"] == UNVERIFIED_FALLBACK_ANSWER
    print("  Test 4 passed: Partial citation mismatch rejects entire unverified answer.")


def test_llm_malformed_response_fails_safe():
    """Test (5): LLM returns malformed or non-JSON output -> fails safe and rejects citation."""
    qa_result = {
        "answer": "Claim supported by Section 35.",
        "cited_sections": ["35"],
        "status": "answered",
    }
    retrieved_chunks = [
        {
            "id": "chunk_0025",
            "text": "A complaint may be filed with a District Commission...",
            "metadata": {"section": "35"},
        }
    ]

    with patch("citation_verification_agent.call_llm_structured", return_value="Invalid non-json text"):
        result = verify_citations(qa_result, retrieved_chunks)

    assert result["verified"] is False
    assert result["rejected_sections"] == ["35"]
    assert result["details"]["35"]["supported"] is False
    assert "Failed to parse LLM verification response" in result["details"]["35"]["reason"]
    assert result["final_answer"] == UNVERIFIED_FALLBACK_ANSWER
    print("  Test 5 passed: Malformed LLM response fails safe -> safe fallback returned.")


def test_logging_on_unsupported_and_parse_error():
    """Test (6): Verify warning logs are emitted when citations are unsupported or fail parsing."""
    qa_result = {
        "answer": "Claim under Section 35.",
        "cited_sections": ["35"],
        "status": "answered",
    }
    retrieved_chunks = [
        {
            "id": "chunk_0025",
            "text": "Statutory text for Section 35",
            "metadata": {"section": "35"},
        }
    ]

    # Test unsupported logging
    mock_unsupported = json.dumps({"is_supported": False, "reason": "Text does not back up claim"})
    with patch("citation_verification_agent.call_llm_structured", return_value=mock_unsupported), \
         patch("citation_verification_agent.logger.warning") as mock_warn:
        verify_citations(qa_result, retrieved_chunks)
        assert mock_warn.called
        assert "section '%s' not supported by text" in mock_warn.call_args[0][0]

    # Test parse error logging
    with patch("citation_verification_agent.call_llm_structured", return_value="{broken json"), \
         patch("citation_verification_agent.logger.warning") as mock_warn:
        verify_citations(qa_result, retrieved_chunks)
        assert mock_warn.called
        assert "failed to parse LLM response" in mock_warn.call_args[0][0]

    print("  Test 6 passed: Warning logging on unsupported citation and parse error verified.")


if __name__ == "__main__":
    print("\nRunning Citation Verification Agent Tests:")
    test_all_citations_verified()
    test_citation_not_in_retrieved_chunks()
    test_citation_unsupported_by_chunk_text()
    test_mixed_citations_partial_failure()
    test_llm_malformed_response_fails_safe()
    test_logging_on_unsupported_and_parse_error()
    print("\nAll Citation Verification Agent tests passed successfully!")
