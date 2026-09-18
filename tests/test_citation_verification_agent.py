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
import llm_client
from citation_verification_agent import (
    verify_citations,
    reverify_answer_citations,
    extract_cited_sections,
    UNVERIFIED_FALLBACK_ANSWER,
)


def test_all_citations_verified():
    """Test (1): All citations exist in retrieved chunks and are supported by LLM -> answer passes through with trailing as_of_date note."""
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
                "as_of_date": "2026-08-06",
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
    expected_answer = (
        f"{qa_result['answer']}\n\n(This answer reflects the Consumer Protection Act, 2019 as of 2026-08-06.)"
    )
    assert result["final_answer"] == expected_answer
    print("  Test 1 passed: All citations verified -> original answer with trailing as_of_date note retained.")


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

    # Test parse error logging via shared helper in llm_client
    with patch("citation_verification_agent.call_llm_structured", return_value="{broken json"), \
         patch("llm_client.logger.warning") as mock_llm_warn, \
         patch("citation_verification_agent.logger.warning") as mock_agent_warn:
        verify_citations(qa_result, retrieved_chunks)
        assert mock_llm_warn.called
        assert "failed to parse JSON" in mock_llm_warn.call_args[0][0]
        assert mock_agent_warn.called
        assert "not supported by text" in mock_agent_warn.call_args[0][0]

    print("  Test 6 passed: Warning logging on unsupported citation and parse error verified.")


def test_multiple_citations_supporting_different_subclaims():
    """
    Regression Test:
    A QA answer cites TWO different sections for two DIFFERENT sub-claims (e.g. Section 2(11)
    supports 'liability/deficiency', Section 39 supports 'remedy/refund').
    Each section's actual chunk text genuinely supports only its own sub-claim.
    Assert BOTH citations pass verification (not rejected for failing to cover the whole answer alone).
    """
    qa_result = {
        "answer": (
            "Under Section 2(11), the delivery of defective goods constitutes a deficiency in service "
            "attracting liability. Under Section 39, the District Commission has the power to order a full "
            "refund and compensation for the consumer's loss."
        ),
        "cited_sections": ["2(11)", "39"],
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
                "as_of_date": "2024-01-15",
            },
        },
        {
            "id": "chunk_0039",
            "text": "Where the District Commission is satisfied that any of the allegations contained in the complaint are proved, it shall issue an order to return to the complainant the price, or to pay compensation...",
            "metadata": {
                "section": "39",
                "title": "Findings of District Commission",
                "source_act": "Consumer Protection Act, 2019",
                "as_of_date": "2026-08-06",
            },
        },
    ]

    def mock_llm_verification(prompt: str) -> str:
        if "Section 2(11)" in prompt:
            return json.dumps({
                "is_supported": True,
                "reason": "Section 2(11) text genuinely supports the deficiency in service / liability sub-claim.",
            })
        elif "Section 39" in prompt:
            return json.dumps({
                "is_supported": True,
                "reason": "Section 39 text genuinely supports the remedy / refund sub-claim.",
            })
        return json.dumps({"is_supported": False, "reason": "Unknown section in prompt."})

    with patch("citation_verification_agent.call_llm_structured", side_effect=mock_llm_verification) as mock_call:
        result = verify_citations(qa_result, retrieved_chunks)

    assert mock_call.call_count == 2
    assert result["verified"] is True
    assert result["verified_sections"] == ["2(11)", "39"]
    assert result["rejected_sections"] == []
    assert result["details"]["2(11)"]["supported"] is True
    assert result["details"]["39"]["supported"] is True
    expected_answer = (
        f"{qa_result['answer']}\n\n(This answer reflects the Consumer Protection Act, 2019 as of 2026-08-06.)"
    )
    assert result["final_answer"] == expected_answer
    print("  Test 7 passed: Multiple citations supporting separate sub-claims both verified with most recent as_of_date.")


def test_empty_citations_not_verified():
    """Test (8): An answer with NO citations must NOT be marked verified (case_07-class bug)."""
    # Case A: status is 'unclear' with empty citations
    qa_unclear = {
        "answer": "The retrieved provisions do not cover this issue.",
        "cited_sections": [],
        "status": "unclear",
    }
    result_unclear = verify_citations(qa_unclear, [])
    assert result_unclear["verified"] is False
    assert result_unclear["verified_sections"] == []
    assert result_unclear["rejected_sections"] == []
    assert result_unclear["final_answer"] == qa_unclear["answer"]

    # Case B: status is 'answered' but LLM provided 0 citations
    qa_answered = {
        "answer": "You can file a complaint in your home city.",
        "cited_sections": [],
        "status": "answered",
    }
    result_answered = verify_citations(qa_answered, [])
    assert result_answered["verified"] is False
    assert result_answered["verified_sections"] == []
    assert result_answered["rejected_sections"] == []
    assert result_answered["final_answer"] == UNVERIFIED_FALLBACK_ANSWER
    print("  Test 8 passed: Empty citations correctly marked unverified.")


def test_citation_granularity_matching():
    """Test (9): Sub-clause and prefix citation granularity matches correctly,
    while non-matching sub-clauses are rejected without false cross-matching."""
    qa_result = {
        "answer": "Under Section 39(1), the Commission may order replacement, and Section 86(d) holds seller liable.",
        "cited_sections": ["Section 39(1)", "86(d)"],
        "status": "answered",
    }
    retrieved_chunks = [
        {
            "id": "chunk_0039",
            "text": "Where the District Commission is satisfied... it shall issue an order directing replacement...",
            "metadata": {"section": "39"},
        },
        {
            "id": "chunk_0086",
            "text": "A product seller shall be liable in a product liability action if the manufacturer is not known...",
            "metadata": {"section": "86"},
        },
    ]

    mock_llm_response = json.dumps({
        "is_supported": True,
        "reason": "Supported by the statutory provisions."
    })

    with patch("citation_verification_agent.call_llm_structured", return_value=mock_llm_response):
        result = verify_citations(qa_result, retrieved_chunks)

    assert result["verified"] is True
    assert result["verified_sections"] == ["Section 39(1)", "86(d)"]
    assert result["rejected_sections"] == []
    # When chunks have no as_of_date, final_answer is preserved without crashing
    assert result["final_answer"] == qa_result["answer"]

    # Negative test: 2(11) must NOT match chunk 2(10), and 38(7) must NOT match chunk 38(2)
    qa_mismatched = {
        "answer": "Claims under 2(11) and 38(7).",
        "cited_sections": ["2(11)", "38(7)"],
        "status": "answered",
    }
    chunks_mismatched = [
        {"id": "chunk_1", "text": "Defect text...", "metadata": {"section": "2(10)"}},
        {"id": "chunk_2", "text": "Procedure text...", "metadata": {"section": "38(2)"}},
    ]
    with patch("citation_verification_agent.call_llm_structured") as mock_llm:
        res_mismatch = verify_citations(qa_mismatched, chunks_mismatched)
        assert mock_llm.call_count == 0  # neither should match chunks

    assert res_mismatch["verified"] is False
    assert set(res_mismatch["rejected_sections"]) == {"2(11)", "38(7)"}
    print("  Test 9 passed: Citation granularity matching and negative discrimination work.")


def test_as_of_date_selection_and_graceful_missing():
    """Test (10): Verifies that:
    1. Different as_of_date values pick the most recent one.
    2. Missing, empty, or None as_of_date values are skipped gracefully without crashing.
    3. If all chunks lack as_of_date, final_answer is returned without a broken trailing note.
    """
    qa_result = {
        "answer": "Under Section 2(7) and Section 35, consumer rights are established.",
        "cited_sections": ["2(7)", "35"],
        "status": "answered",
    }
    # Case A: Chunks have varied dates, including empty string and None
    chunks_with_dates = [
        {
            "id": "c1",
            "text": "Section 2(7) defines consumer...",
            "metadata": {
                "section": "2(7)",
                "as_of_date": "2023-05-10",
                "source_act": "Consumer Protection Act, 2019",
            },
        },
        {
            "id": "c2",
            "text": "Section 2(7) sub-clause...",
            "metadata": {
                "section": "2(7)",
                "as_of_date": "",  # empty string skipped gracefully
            },
        },
        {
            "id": "c3",
            "text": "Section 35 filing procedure...",
            "metadata": {
                "section": "35",
                "as_of_date": "2026-09-01",  # most recent date
                "source_act": "Consumer Protection Act, 2019",
            },
        },
        {
            "id": "c4",
            "text": "Section 35 supplementary...",
            "metadata": {
                "section": "35",
                "as_of_date": None,  # None skipped gracefully
            },
        },
    ]

    mock_llm_response = json.dumps({"is_supported": True, "reason": "Both sections supported."})
    with patch("citation_verification_agent.call_llm_structured", return_value=mock_llm_response):
        res = verify_citations(qa_result, chunks_with_dates)

    assert res["verified"] is True
    expected_note = "\n\n(This answer reflects the Consumer Protection Act, 2019 as of 2026-09-01.)"
    assert res["final_answer"] == f"{qa_result['answer']}{expected_note}"

    # Case B: All verified chunks have missing/empty as_of_date -> no trailing note, no crash
    chunks_without_dates = [
        {"id": "c1", "text": "Section 2(7) text", "metadata": {"section": "2(7)"}},
        {"id": "c2", "text": "Section 35 text", "metadata": {"section": "35", "as_of_date": ""}},
    ]
    with patch("citation_verification_agent.call_llm_structured", return_value=mock_llm_response):
        res_no_date = verify_citations(qa_result, chunks_without_dates)

    assert res_no_date["verified"] is True
    assert res_no_date["final_answer"] == qa_result["answer"]
    print("  Test 10 passed: Most recent as_of_date selected, missing dates handled gracefully.")


def test_extract_cited_sections_various_phrasings():
    """extract_cited_sections() picks up single, comma-joined, 'and'-joined, and sub-clause mentions."""
    assert extract_cited_sections(
        "Under Section 83 you have rights. Section 84 and Section 86 also apply. "
        "See Section 39(1) for remedies."
    ) == ["83", "84", "86", "39(1)"]
    assert extract_cited_sections("Under Sections 82, 83 you may act.") == ["82", "83"]
    assert extract_cited_sections("Section 86(e) is relevant, as is Section 87(3).") == ["86(e)", "87(3)"]
    assert extract_cited_sections("No sections here at all.") == []
    print("  Test 11 passed: extract_cited_sections handles realistic Critic-answer phrasing.")


def test_reverify_answer_citations_catches_unverified_critic_addition():
    """
    Regression test for Known Issue #10: the Critic Agent can weave in a section
    number (typically surfaced by the Debate Mechanism's wider-top_k retrieval)
    that was never audited by Citation Verification. reverify_answer_citations()
    must catch this - i.e. NOT report `verified=True` when the Critic's text
    cites a section absent from the chunk pool it's checked against.
    """
    critic_answer = (
        "Under Section 83 you may claim relief. However Section 84 governs whether "
        "the defect is a manufacturing defect. (This answer reflects the Act as of 2026-08-06.)"
    )
    # Only Section 83 was actually retrieved/available - Section 84 is absent,
    # simulating it having only ever surfaced via the Debate Mechanism's separate
    # top_k=8 retrieval pool, never checked by Citation Verification.
    chunks_missing_84 = [
        {"id": "c1", "text": "Section 83 text about liability...", "metadata": {"section": "83"}},
    ]

    with patch("citation_verification_agent.call_llm_structured") as mock_llm:
        result = reverify_answer_citations(critic_answer, chunks_missing_84)
        # LLM support-check should only ever be reached for Section 83 (the one
        # actually retrieved); Section 84 is rejected before any LLM call.
        assert mock_llm.call_count <= 1

    assert result["verified"] is False
    assert "84" in result["rejected_sections"]
    print("  Test 12 passed: reverify_answer_citations rejects a Critic-introduced, never-retrieved section.")


def test_reverify_answer_citations_passes_when_fully_grounded():
    """
    When every section the Critic's revised text cites IS present in the
    (combined QA + Debate) chunk pool and LLM-supported, reverification
    succeeds and the Critic's text is delivered unchanged (no duplicate
    as_of_date trailer appended).
    """
    critic_answer = (
        "Under Section 83 you may claim relief, and Section 84 governs whether "
        "the defect qualifies. (This answer reflects the Act as of 2026-08-06.)"
    )
    chunks_with_84 = [
        {"id": "c1", "text": "Section 83 text about liability...", "metadata": {"section": "83"}},
        {"id": "c2", "text": "Section 84 text about manufacturing defects...", "metadata": {"section": "84"}},
    ]
    mock_llm_response = json.dumps({"is_supported": True, "reason": "Text supports the claim."})

    with patch("citation_verification_agent.call_llm_structured", return_value=mock_llm_response):
        result = reverify_answer_citations(critic_answer, chunks_with_84)

    assert result["verified"] is True
    assert set(result["verified_sections"]) == {"83", "84"}
    # Delivered text is exactly the Critic's answer - no second as_of_date trailer appended.
    assert result["final_answer"] == critic_answer
    print("  Test 13 passed: reverify_answer_citations passes through a fully-grounded Critic revision unchanged.")


if __name__ == "__main__":
    print("\nRunning Citation Verification Agent Tests:")
    test_all_citations_verified()
    test_citation_not_in_retrieved_chunks()
    test_citation_unsupported_by_chunk_text()
    test_mixed_citations_partial_failure()
    test_llm_malformed_response_fails_safe()
    test_logging_on_unsupported_and_parse_error()
    test_multiple_citations_supporting_different_subclaims()
    test_empty_citations_not_verified()
    test_citation_granularity_matching()
    test_as_of_date_selection_and_graceful_missing()
    test_extract_cited_sections_various_phrasings()
    test_reverify_answer_citations_catches_unverified_critic_addition()
    test_reverify_answer_citations_passes_when_fully_grounded()
    print("\nAll Citation Verification Agent tests passed successfully!")