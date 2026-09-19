"""
Unit and integration tests for the NyayaSetu FastAPI HTTP API (api/main.py).

Uses FastAPI's TestClient and mocks all external orchestrator dependencies:
  - orchestrator.understand_query
  - orchestrator.IntakeSession
  - orchestrator.answer_question (QA agent)
  - orchestrator.verify_citations
  - orchestrator.retrieve
  - orchestrator.run_debate
  - orchestrator.run_final_critique

No real calls to Gemini API or ChromaDB are made during these tests.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock
import uuid

import pytest
from fastapi.testclient import TestClient

# Ensure src and api are in sys.path
root_dir = Path(__file__).resolve().parent.parent
src_dir = root_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from models import DebateResult, CriticResult
from api.main import app, session_store


@pytest.fixture(autouse=True)
def clear_session_store():
    """Clear in-memory sessions before each test."""
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


@pytest.fixture
def client():
    """Create a test client with application lifespan."""
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client):
    """
    GET /api/health returns 200 without invoking orchestrator components.
    """
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_session_unclear_domain(client):
    """
    POST /api/sessions with unclear domain returns session_id and stage 'unclear_domain'.
    """
    with patch("orchestrator.understand_query") as mock_understand:
        mock_understand.return_value = {"domain": "unclear", "facts": {}}

        response = client.post("/api/sessions", json={"message": "Write a song about clouds."})

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert uuid.UUID(data["session_id"])  # Valid UUID
        assert data["stage"] == "unclear_domain"
        assert "message" in data
        assert len(data["message"]) > 0

        # Session is registered in store
        stored = session_store.get(data["session_id"])
        assert stored is not None
        assert stored.domain == "unclear"


def test_create_session_intake_question(client):
    """
    POST /api/sessions with clear domain initializes intake and returns first question.
    """
    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Refrigerator"},
        }
        mock_intake = MockIntakeSession.return_value
        mock_intake.next_question.return_value = {
            "field_key": "what_went_wrong",
            "question_text": "What went wrong with the refrigerator?",
        }

        response = client.post(
            "/api/sessions",
            json={"message": "I bought a refrigerator that broke down immediately."},
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["stage"] == "intake_question"
        assert data["field_key"] == "what_went_wrong"
        assert data["question_text"] == "What went wrong with the refrigerator?"


def test_answer_unknown_session_returns_404(client):
    """
    POST /api/sessions/{session_id}/answer with unknown session_id returns HTTP 404.
    """
    response = client.post(
        "/api/sessions/unknown-session-12345/answer",
        json={"field_key": "what_went_wrong", "answer": "Cooling stopped working."},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_proceed_unknown_session_returns_404(client):
    """
    POST /api/sessions/{session_id}/proceed with unknown session_id returns HTTP 404.
    """
    response = client.post("/api/sessions/unknown-session-12345/proceed")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_answer_question_advances_state(client):
    """
    POST /api/sessions/{session_id}/answer records the answer and returns the next question.
    """
    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Laptop"},
        }
        mock_intake = MockIntakeSession.return_value
        mock_intake.next_question.side_effect = [
            {"field_key": "what_went_wrong", "question_text": "What went wrong?"},
            {"field_key": "amount_paid", "question_text": "How much did you pay?"},
        ]

        # 1. Create session
        resp1 = client.post(
            "/api/sessions",
            json={"message": "I purchased a laptop yesterday."},
        )
        session_id = resp1.json()["session_id"]

        # 2. Answer first question
        resp2 = client.post(
            f"/api/sessions/{session_id}/answer",
            json={"field_key": "what_went_wrong", "answer": "The motherboard failed."},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["stage"] == "intake_question"
        assert data2["field_key"] == "amount_paid"
        assert data2["question_text"] == "How much did you pay?"
        mock_intake.record_answer.assert_called_with("what_went_wrong", "The motherboard failed.")


def test_proceed_valid_session_advances_after_gap(client):
    """
    POST /api/sessions/{session_id}/proceed bypasses surfaced final check gap to complete.
    """
    mock_qa_result = {
        "answer": "Under Section 35 of the Consumer Protection Act, 2019...",
        "cited_sections": ["35"],
        "status": "answered",
        "retrieved_chunks": [
            {
                "id": "c1",
                "text": "Text 1",
                "metadata": {"section": "35", "title": "Complaint procedure"},
            }
        ],
    }
    mock_verification = {
        "verified": True,
        "verified_sections": ["35"],
        "rejected_sections": [],
        "details": {},
        "final_answer": "Under Section 35 of the Consumer Protection Act, 2019...",
    }

    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession, \
         patch("orchestrator.answer_question") as mock_qa, \
         patch("orchestrator.verify_citations") as mock_verify, \
         patch("orchestrator.retrieve") as mock_retrieve, \
         patch("orchestrator.run_debate") as mock_debate, \
         patch("orchestrator.run_final_critique") as mock_critic:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Laptop"},
        }
        mock_intake = MockIntakeSession.return_value
        mock_intake.next_question.return_value = None  # intake checklist satisfied
        mock_intake.run_final_check.return_value = "Missing invoice copy"
        mock_intake.to_case_brief.return_value = {"domain": "Consumer Protection", "facts": {}}

        mock_qa.return_value = mock_qa_result
        mock_verify.return_value = mock_verification
        mock_retrieve.return_value = []
        mock_debate.return_value = None
        mock_critic.return_value = None

        # Start session -> surfaces final_check_gap
        resp1 = client.post("/api/sessions", json={"message": "Defective laptop"})
        assert resp1.status_code == 200
        assert resp1.json()["stage"] == "final_check_gap"
        assert resp1.json()["gap"] == "Missing invoice copy"
        session_id = resp1.json()["session_id"]

        # Call proceed -> completes pipeline
        resp2 = client.post(f"/api/sessions/{session_id}/proceed")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["stage"] == "complete"
        assert data2["verified"] is True
        assert data2["final_answer"] == "Under Section 35 of the Consumer Protection Act, 2019..."


def test_full_mocked_run_to_complete(client):
    """
    Full multi-turn flow reaching stage == 'complete' returns all required fields:
    final_answer, verified_sections, critic, critic_revision_discarded.
    """
    mock_qa_result = {
        "answer": "Initial QA answer text.",
        "cited_sections": ["35"],
        "status": "answered",
        "retrieved_chunks": [
            {
                "id": "c1",
                "text": "Chunk text",
                "metadata": {"section": "35", "title": "Section 35"},
            }
        ],
    }

    mock_verification = {
        "verified": True,
        "verified_sections": ["35"],
        "rejected_sections": [],
        "details": {},
        "final_answer": "Verified QA answer text citing Section 35.",
    }

    mock_debate_result = DebateResult(
        plaintiff_argument="Plaintiff rights under Section 35.",
        plaintiff_cited_sections=["35"],
        defense_argument="Defense exemption under Section 87.",
        defense_cited_sections=["87"],
        is_grey_zone=True,
        judge_summary="Statutory ambiguity noted.",
        clearly_supported_side=None,
    )

    mock_critic_result = CriticResult(
        approved=True,
        final_answer="Verified QA answer text citing Section 35.",
        critique_notes="Audit approved without revision.",
        flagged_grey_zone_conflict=False,
    )

    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession, \
         patch("orchestrator.answer_question") as mock_qa, \
         patch("orchestrator.verify_citations") as mock_verify, \
         patch("orchestrator.retrieve") as mock_retrieve, \
         patch("orchestrator.run_debate") as mock_debate, \
         patch("orchestrator.run_final_critique") as mock_critic:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "AC"},
        }
        mock_intake = MockIntakeSession.return_value
        mock_intake.next_question.side_effect = [
            {"field_key": "what_went_wrong", "question_text": "What went wrong with the AC?"},
            None,
        ]
        mock_intake.run_final_check.return_value = None
        mock_intake.to_case_brief.return_value = {"domain": "Consumer Protection", "facts": {}}

        mock_qa.return_value = mock_qa_result
        mock_verify.return_value = mock_verification
        mock_retrieve.return_value = []
        mock_debate.return_value = mock_debate_result
        mock_critic.return_value = mock_critic_result

        # Step 1: Start
        resp1 = client.post("/api/sessions", json={"message": "AC stopped cooling."})
        assert resp1.status_code == 200
        session_id = resp1.json()["session_id"]
        assert resp1.json()["stage"] == "intake_question"

        # Step 2: Answer question -> finish intake & run pipeline
        resp2 = client.post(
            f"/api/sessions/{session_id}/answer",
            json={"field_key": "what_went_wrong", "answer": "Gas leak after 2 days."},
        )
        assert resp2.status_code == 200
        data = resp2.json()

        assert data["stage"] == "complete"
        assert data["verified"] is True
        assert data["final_answer"] == "Verified QA answer text citing Section 35."
        assert data["verified_sections"] == ["35"]
        assert data["rejected_sections"] == []
        assert data["critic_revision_discarded"] is False
        assert data["debate"] is not None
        assert data["debate"]["is_grey_zone"] is True
        assert data["critic"] is not None
        assert data["critic"]["approved"] is True


def test_unhandled_orchestrator_exception_returns_500(client):
    """
    Unhandled exceptions from inside CaseSession return HTTP 500 with a generic
    error message and never leak internal stack trace to the caller.
    """
    with patch("orchestrator.understand_query") as mock_understand:
        mock_understand.side_effect = RuntimeError("Sensitive internal database connection leaked!")

        response = client.post(
            "/api/sessions",
            json={"message": "A normal query that triggers an error."},
        )

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "Something went wrong, please start a new session."
        assert "Sensitive internal database" not in str(data)
        assert "RuntimeError" not in str(data)


def test_answer_validation_error_returns_400(client):
    """
    Calling answer_question before starting or with invalid state returns HTTP 400.
    """
    # Create an uninitialized session directly in the store to simulate invalid lifecycle call
    session_id, session = session_store.create()
    assert session.intake_session is None

    response = client.post(
        f"/api/sessions/{session_id}/answer",
        json={"field_key": "field", "answer": "val"},
    )
    assert response.status_code == 400
    assert "not started intake" in response.json()["detail"].lower()


def test_session_store_eviction_and_touch():
    """
    SessionStore evicts sessions inactive for >30 minutes and retains recently touched sessions.
    """
    sid1, s1 = session_store.create()
    sid2, s2 = session_store.create()

    # Manually adjust sid1 last_active to 35 minutes ago
    past_time = datetime.now(timezone.utc) - timedelta(minutes=35)
    session_store._sessions[sid1]["last_active"] = past_time

    # Touch sid2
    session_store.touch(sid2)

    evicted_count = session_store.evict_expired(max_idle_seconds=1800)
    assert evicted_count == 1
    assert session_store.get(sid1) is None
    assert session_store.get(sid2) is not None


def test_cors_middleware_headers(client):
    """
    CORS headers are returned appropriately for allowed origin.
    """
    response = client.options(
        "/api/sessions",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
