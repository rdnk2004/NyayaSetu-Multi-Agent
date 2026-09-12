"""
Unit tests for the Debate Mechanism (src/debate_mechanism.py).

Tests:
1. Normal case with genuinely opposing arguments: returns is_grey_zone=True with both sides' cited sections preserved.
2. Case where judge determines one side is clearly correct: returns is_grey_zone=False with clearly_supported_side set.
3. Empty retrieved_chunks: skips all LLM calls and returns the safe default.
4. Malformed JSON from any one of the three calls fails safe without crashing.

Run:
  python -m pytest tests/test_debate_mechanism.py
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure src is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from debate_mechanism import run_debate
from models import DebateResult


def test_opposing_arguments_grey_zone():
    """Test (1): A normal case with genuinely opposing arguments returns is_grey_zone=True with cited sections preserved."""
    case_brief = {
        "domain": "Consumer Protection",
        "facts": {
            "what_was_bought_or_hired": "Water Purifier",
            "what_went_wrong": "Purifier leaked and caused short circuit after user replaced filter with third party part",
            "amount_paid": "15,000 INR",
            "seller_or_provider": "AquaPure Systems",
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
            },
        },
        {
            "id": "chunk_0087",
            "text": "A product liability action cannot be brought against the product manufacturer where the product was altered, modified or misused...",
            "metadata": {
                "section": "87",
                "title": "Exceptions to product liability action",
            },
        },
    ]

    mock_plaintiff = json.dumps({
        "argument": "Under Section 2(11), the manufacturer is strictly liable for selling a fundamentally deficient product that caused electrical failure.",
        "cited_sections": ["Section 2(11)"],
    })

    mock_defense = json.dumps({
        "argument": "Under Section 87, product liability cannot be brought against the manufacturer because the user altered and modified the product using unauthorized components.",
        "cited_sections": ["Section 87"],
    })

    mock_judge = json.dumps({
        "is_grey_zone": True,
        "judge_summary": "There is a genuine legal grey zone: while Section 2(11) defines deficiency broadly, Section 87 provides statutory exceptions where unauthorized alterations occurred.",
        "clearly_supported_side": None,
    })

    with patch("debate_mechanism.call_llm_structured", side_effect=[mock_plaintiff, mock_defense, mock_judge]) as mock_llm:
        result = run_debate(case_brief, mock_chunks)

    assert mock_llm.call_count == 3
    assert result["is_grey_zone"] is True
    assert result["clearly_supported_side"] is None
    assert "2(11)" in result["plaintiff_cited_sections"]
    assert "87" in result["defense_cited_sections"]
    assert len(result["plaintiff_argument"]) > 0
    assert len(result["defense_argument"]) > 0
    assert len(result["judge_summary"]) > 0


def test_judge_determines_clearly_supported_side():
    """Test (2): Case where the judge determines one side is clearly correct returns is_grey_zone=False with clearly_supported_side set."""
    case_brief = {
        "domain": "Consumer Protection",
        "facts": {
            "what_was_bought_or_hired": "Refrigerator",
            "what_went_wrong": "Compressor broke on day 1 and dealer refused any support",
            "amount_paid": "32,000 INR",
            "seller_or_provider": "CoolTech Retailers",
        },
        "ready": True,
    }

    mock_chunks = [
        {
            "id": "chunk_0035",
            "text": "A complaint in relation to any goods sold or delivered or agreed to be sold or delivered or any service provided or agreed to be provided may be filed with a District Commission...",
            "metadata": {
                "section": "35",
                "title": "Manner in which complaint shall be made",
            },
        },
        {
            "id": "chunk_0002",
            "text": "defect means any fault, imperfection or shortcoming in the quality, quantity, potency, purity or standard...",
            "metadata": {
                "section": "2(10)",
                "title": "Defect",
            },
        },
    ]

    mock_plaintiff = json.dumps({
        "argument": "The consumer has an express statutory right under Section 35 to file a complaint before the District Commission for a defect defined under Section 2(10).",
        "cited_sections": ["Section 35", "Section 2(10)"],
    })

    mock_defense = json.dumps({
        "argument": "The consumer should not approach the District Commission.",
        "cited_sections": ["Section 35"],
    })

    mock_judge = json.dumps({
        "is_grey_zone": False,
        "judge_summary": "The statutory text of Section 35 unambiguously grants the consumer the right to file a complaint for defective goods under Section 2(10). The defense has no statutory basis under the retrieved provisions.",
        "clearly_supported_side": "plaintiff",
    })

    with patch("debate_mechanism.call_llm_structured", side_effect=[mock_plaintiff, mock_defense, mock_judge]) as mock_llm:
        result = run_debate(case_brief, mock_chunks)

    assert mock_llm.call_count == 3
    assert result["is_grey_zone"] is False
    assert result["clearly_supported_side"] == "plaintiff"
    assert "35" in result["plaintiff_cited_sections"]
    assert "2(10)" in result["plaintiff_cited_sections"]
    assert "35" in result["defense_cited_sections"]
    assert len(result["judge_summary"]) > 0


def test_empty_retrieved_chunks_skips_llm_calls():
    """Test (3): Empty retrieved_chunks skips all LLM calls and returns safe default."""
    case_brief = {
        "domain": "Consumer Protection",
        "facts": {
            "what_was_bought_or_hired": "Laptop",
            "what_went_wrong": "Battery drained fast",
        },
        "ready": True,
    }

    with patch("debate_mechanism.call_llm_structured") as mock_llm:
        result_empty = run_debate(case_brief, [])
        result_none = run_debate(case_brief, None)

    mock_llm.assert_not_called()

    for res in (result_empty, result_none):
        assert res["is_grey_zone"] is False
        assert res["clearly_supported_side"] is None
        assert res["plaintiff_argument"] == ""
        assert res["plaintiff_cited_sections"] == []
        assert res["defense_argument"] == ""
        assert res["defense_cited_sections"] == []
        assert "no relevant statutory" in res["judge_summary"].lower() or "nothing to debate" in res["judge_summary"].lower()


def test_malformed_json_fails_safe():
    """Test (4): Malformed JSON from any one of the three calls fails safe without crashing."""
    case_brief = {
        "domain": "Consumer Protection",
        "facts": {
            "what_was_bought_or_hired": "Smartphone",
            "what_went_wrong": "Camera cracked",
        },
        "ready": True,
    }

    mock_chunks = [
        {
            "id": "chunk_0010",
            "text": "Deficiency provisions...",
            "metadata": {"section": "2(11)", "title": "Deficiency"},
        }
    ]

    valid_plaintiff = json.dumps({
        "argument": "Valid plaintiff argument under Section 2(11).",
        "cited_sections": ["2(11)"],
    })

    valid_defense = json.dumps({
        "argument": "Valid defense argument under Section 2(11).",
        "cited_sections": ["2(11)"],
    })

    valid_judge = json.dumps({
        "is_grey_zone": True,
        "judge_summary": "Both sides arguable.",
        "clearly_supported_side": None,
    })

    malformed_payloads = [
        "This is not JSON at all",
        "{broken json",
        "```json\n{'unterminated': true",
        "",
        "None",
        json.dumps(["not a dictionary"]),
    ]

    # 4a: Call 1 (Plaintiff) fails
    for bad in malformed_payloads:
        with patch("debate_mechanism.call_llm_structured", side_effect=[bad, valid_defense, valid_judge]):
            res = run_debate(case_brief, mock_chunks)
        assert isinstance(res, (dict, DebateResult))
        assert res["is_grey_zone"] is False
        assert res["clearly_supported_side"] is None
        assert isinstance(res["judge_summary"], str)

    # 4b: Call 2 (Defense) fails
    for bad in malformed_payloads:
        with patch("debate_mechanism.call_llm_structured", side_effect=[valid_plaintiff, bad, valid_judge]):
            res = run_debate(case_brief, mock_chunks)
        assert isinstance(res, (dict, DebateResult))
        assert res["is_grey_zone"] is False
        assert res["clearly_supported_side"] is None
        assert isinstance(res["judge_summary"], str)

    # 4c: Call 3 (Judge) fails
    for bad in malformed_payloads:
        with patch("debate_mechanism.call_llm_structured", side_effect=[valid_plaintiff, valid_defense, bad]):
            res = run_debate(case_brief, mock_chunks)
        assert isinstance(res, (dict, DebateResult))
        assert res["is_grey_zone"] is False
        assert res["clearly_supported_side"] is None
        assert isinstance(res["judge_summary"], str)


def test_invalid_case_brief_fails_safe():
    """Edge case: None or non-dict case_brief handled gracefully without crashing."""
    mock_chunks = [
        {
            "id": "chunk_0010",
            "text": "Some chunk",
            "metadata": {"section": "2(11)"},
        }
    ]
    with patch("debate_mechanism.call_llm_structured") as mock_llm:
        res_none = run_debate(None, mock_chunks)
        res_str = run_debate("invalid brief", mock_chunks)

    mock_llm.assert_not_called()
    assert res_none["is_grey_zone"] is False
    assert res_none["clearly_supported_side"] is None
    assert res_str["is_grey_zone"] is False
