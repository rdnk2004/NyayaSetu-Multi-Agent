"""
NyayaSetu Orchestrator

Coordinates the end-to-end legal assistance pipeline as a resumable,
multi-turn state machine:
  1. Query Understanding (first user message -> domain & initial facts)
  2. Intelligent Intake (multi-turn checklist-based Q&A until facts complete)
  3. Retrieval & Grounded QA (retrieve relevant statutory chunks -> answer)
  4. Citation Verification (audit citations against chunks and LLM support)

The caller (e.g. API layer or UI) drives the session turn-by-turn via:
  - session.start(first_message)
  - session.answer_question(field_key, answer_text)
  - session.proceed()  # optional helper to proceed past final check gaps
"""

import logging
from typing import Any

from query_understanding import understand_query
from intake_agent import IntakeSession
from qa_agent import answer_question as qa_answer_question
from citation_verification_agent import verify_citations

logger = logging.getLogger(__name__)

# Module-level aliases to support both qa_answer_question and answer_question in tests/patches
qa_agent_answer = qa_answer_question
answer_question = qa_answer_question


class CaseSession:
    """
    Resumable multi-turn state machine managing the lifecycle of a legal inquiry.
    """

    def __init__(self):
        self.state: str = "intake"
        self.domain: str | None = None
        self.intake_session: IntakeSession | None = None
        self.final_result: dict[str, Any] | None = None
        self._final_check_surfaced: bool = False

    def start(self, first_message: str) -> dict[str, Any]:
        """
        Processes the citizen's initial problem description:
        - Classifies domain and extracts any already-mentioned facts.
        - Halts if domain is unclear.
        - Otherwise initializes IntakeSession and either asks the first question
          or skips straight to QA if the checklist is already satisfied.
        """
        understanding = understand_query(first_message)
        domain = understanding.get("domain", "unclear")
        facts = understanding.get("facts", {})

        if domain == "unclear":
            self.state = "unclear_domain"
            self.domain = "unclear"
            return {
                "stage": "unclear_domain",
                "message": (
                    "Could you please provide more details about your situation? "
                    "We currently assist with Consumer Protection and related legal issues."
                ),
            }

        self.domain = domain
        self.intake_session = IntakeSession(domain=domain, known_facts=facts)

        next_q = self.intake_session.next_question()
        if next_q is not None:
            self.state = "intake_question"
            return {
                "stage": "intake_question",
                "field_key": next_q["field_key"],
                "question_text": next_q["question_text"],
            }

        # Checklist already full from first message
        return self._finish_intake()

    def answer_question(self, field_key: str, answer_text: str) -> dict[str, Any]:
        """
        Records the user's answer to a pending intake question and either:
        - returns the next required question, or
        - finishes intake and executes QA + Citation Verification.
        """
        if self.intake_session is None:
            raise ValueError("Session has not started intake. Call start() first.")

        self.intake_session.record_answer(field_key, answer_text)

        next_q = self.intake_session.next_question()
        if next_q is not None:
            self.state = "intake_question"
            return {
                "stage": "intake_question",
                "field_key": next_q["field_key"],
                "question_text": next_q["question_text"],
            }

        return self._finish_intake()

    def proceed(self) -> dict[str, Any]:
        """
        Proceed with the pipeline (e.g. after a final_check_gap has been surfaced,
        to proceed directly to QA without adding more facts).
        """
        return self._finish_intake()

    def _finish_intake(self) -> dict[str, Any]:
        """
        Runs final check for gaps once, then hands off to QA Agent and
        Citation Verification Agent.
        """
        if self.intake_session is None:
            raise ValueError("Intake session has not been initialized.")

        # Surface critical missing info gap ONCE if flagged by final check
        if not self._final_check_surfaced:
            self._final_check_surfaced = True
            gap = self.intake_session.run_final_check()
            if gap:
                self.state = "final_check_gap"
                return {"stage": "final_check_gap", "gap": gap}

        case_brief = self.intake_session.to_case_brief()
        qa_result = answer_question(case_brief)

        # --- TEMPORARY DIAGNOSTIC PRINT - remove after we diagnose the microwave case ---
        print("\n--- Retrieved chunks (section : title) ---")
        for c in qa_result.get("retrieved_chunks", []):
            print(f"  {c['metadata']['section']} : {c['metadata'].get('title', '')}")
        # --- END TEMPORARY DIAGNOSTIC PRINT ---

        retrieved_chunks = qa_result.get("retrieved_chunks", [])
        verification = verify_citations(qa_result, retrieved_chunks)

        self.final_result = verification
        self.state = "complete"

        return {
            "stage": "complete",
            "verified": verification["verified"],
            "final_answer": verification["final_answer"],
            "verified_sections": verification["verified_sections"],
            "rejected_sections": verification["rejected_sections"],
        }