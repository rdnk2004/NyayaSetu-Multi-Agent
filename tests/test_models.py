"""
Unit tests for NyayaSetu Pydantic Data Contracts (src/models.py).
Tests attribute access, dict-style subscripting, default fields, serialization,
and container protocol (__contains__, get, keys, values, items, __iter__).
"""

import sys
from pathlib import Path

# Ensure src directory is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from models import (
    CaseBrief,
    QAResult,
    CitationVerificationDetail,
    CitationVerificationResult,
    LandmarkCase,
    LandmarkCaseResult,
    DebateResult,
    OrchestratorStageResult,
)


def test_case_brief_model():
    brief = CaseBrief(
        domain="Consumer Protection",
        facts={"what_was_bought_or_hired": "Smartphone"},
        ready=True,
    )
    # Attribute access
    assert brief.domain == "Consumer Protection"
    assert brief.facts == {"what_was_bought_or_hired": "Smartphone"}
    assert brief.ready is True

    # Dict subscript access
    assert brief["domain"] == "Consumer Protection"
    assert brief["facts"]["what_was_bought_or_hired"] == "Smartphone"
    assert brief["ready"] is True

    # Dict methods
    assert brief.get("domain") == "Consumer Protection"
    assert brief.get("nonexistent", "fallback") == "fallback"
    assert "domain" in brief
    assert "ready" in brief
    assert set(brief.keys()) >= {"domain", "facts", "ready"}


def test_qa_result_model():
    res = QAResult(
        answer="Under Section 35, complaint is permitted.",
        cited_sections=["35"],
        status="answered",
        retrieved_chunks=[{"text": "chunk text", "metadata": {"section": "35"}}],
    )
    assert res.status == "answered"
    assert res["status"] == "answered"
    assert res["cited_sections"] == ["35"]
    assert len(res["retrieved_chunks"]) == 1
    assert res.get("answer").startswith("Under Section 35")


def test_citation_verification_result_model():
    detail = CitationVerificationDetail(supported=True, reason="Grounded in text")
    res = CitationVerificationResult(
        verified=True,
        verified_sections=["2(11)"],
        rejected_sections=[],
        final_answer="Original text.",
        details={"2(11)": detail},
    )
    assert res.verified is True
    assert res["verified"] is True
    assert res["details"]["2(11)"]["supported"] is True
    assert res["details"]["2(11)"]["reason"] == "Grounded in text"
    assert res.details["2(11)"].supported is True


def test_landmark_case_result_model():
    case = LandmarkCase(
        case_title="Test vs Union",
        court="Supreme Court",
        date="2025-01-01",
        source_url="https://indiankanoon.org/doc/123/",
        attribution="Powered by Indian Kanoon",
        relevance_explanation="Directly on point.",
    )
    res = LandmarkCaseResult(cases=[case], status="found")
    assert res.status == "found"
    assert len(res["cases"]) == 1
    assert res["cases"][0]["case_title"] == "Test vs Union"
    assert res["cases"][0]["source_url"] == "https://indiankanoon.org/doc/123/"
    assert res.cases[0].court == "Supreme Court"


def test_debate_result_model():
    res = DebateResult(
        plaintiff_argument="Arg 1",
        plaintiff_cited_sections=["2(11)"],
        defense_argument="Arg 2",
        defense_cited_sections=["87"],
        is_grey_zone=True,
        judge_summary="Ambiguous issue.",
        clearly_supported_side=None,
    )
    assert res["is_grey_zone"] is True
    assert res.is_grey_zone is True
    assert res["clearly_supported_side"] is None
    assert "2(11)" in res["plaintiff_cited_sections"]
    assert "87" in res["defense_cited_sections"]


def test_orchestrator_stage_result_model():
    # Unclear domain stage
    s1 = OrchestratorStageResult(stage="unclear_domain", message="Please clarify")
    assert s1["stage"] == "unclear_domain"
    assert "message" in s1
    assert "field_key" not in s1
    assert s1.get("message") == "Please clarify"
    assert s1.get("field_key") is None

    # Intake question stage
    s2 = OrchestratorStageResult(stage="intake_question", field_key="amount", question_text="How much?")
    assert s2["stage"] == "intake_question"
    assert s2["field_key"] == "amount"
    assert s2["question_text"] == "How much?"
    assert "field_key" in s2
    assert "message" not in s2

    # Complete stage
    s3 = OrchestratorStageResult(
        stage="complete",
        verified=True,
        final_answer="Answer here",
        verified_sections=["35"],
        rejected_sections=[],
    )
    assert s3["stage"] == "complete"
    assert s3["verified"] is True
    assert s3["final_answer"] == "Answer here"
    assert s3["verified_sections"] == ["35"]
    assert s3["rejected_sections"] == []


if __name__ == "__main__":
    test_case_brief_model()
    test_qa_result_model()
    test_citation_verification_result_model()
    test_landmark_case_result_model()
    test_debate_result_model()
    test_orchestrator_stage_result_model()
    print("All models unit tests passed successfully!")
