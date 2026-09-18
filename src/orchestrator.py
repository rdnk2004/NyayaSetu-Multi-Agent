"""
NyayaSetu Orchestrator

Coordinates the end-to-end legal assistance pipeline as a resumable,
multi-turn state machine:
  1. Query Understanding (first user message -> domain & initial facts)
  2. Intelligent Intake (multi-turn checklist-based Q&A until facts complete)
  3. Retrieval & Grounded QA (retrieve relevant statutory chunks -> answer)
  4. Citation Verification (audit citations against chunks and LLM support)
  5. Debate Mechanism (adversarial statutory arguments & grey-zone adjudication)
  6. Critic Agent (final quality re-verification & calibration pass)

The caller (e.g. API layer or UI) drives the session turn-by-turn via:
  - session.start(first_message)
  - session.answer_question(field_key, answer_text)
  - session.proceed()  # optional helper to proceed past final check gaps
"""

import logging
from typing import Any

from config import MAX_MESSAGE_LENGTH, DEBATE_RETRIEVAL_TOP_K
from query_understanding import understand_query
from intake_agent import IntakeSession
from qa_agent import answer_question as qa_answer_question, _build_query_from_facts
from citation_verification_agent import verify_citations, reverify_answer_citations
from retrieve import retrieve
from debate_mechanism import run_debate
from critic_agent import run_final_critique
from models import CaseBrief, OrchestratorStageResult, DebateResult, CriticResult

logger = logging.getLogger(__name__)

# Module-level aliases to support both qa_answer_question and answer_question in tests/patches
qa_agent_answer = qa_answer_question
answer_question = qa_answer_question
critic_agent_critique = run_final_critique


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

    def start(self, first_message: str) -> OrchestratorStageResult:
        """
        Processes the citizen's initial problem description:
        - Classifies domain and extracts any already-mentioned facts.
        - Halts if domain is unclear.
        - Otherwise initializes IntakeSession and either asks the first question
          or skips straight to QA if the checklist is already satisfied.
        """
        if len(first_message) > MAX_MESSAGE_LENGTH:
            self.state = "message_too_long"
            return OrchestratorStageResult(
                stage="message_too_long",
                message=(
                    f"Please keep your message under {MAX_MESSAGE_LENGTH} characters "
                    "and split longer situations into a few messages."
                ),
            )

        understanding = understand_query(first_message)
        domain = understanding.get("domain", "unclear")
        facts = understanding.get("facts", {})

        if domain == "unclear":
            self.state = "unclear_domain"
            self.domain = "unclear"
            return OrchestratorStageResult(
                stage="unclear_domain",
                message=(
                    "Could you please provide more details about your situation? "
                    "We currently assist with Consumer Protection and related legal issues."
                ),
            )

        self.domain = domain
        self.intake_session = IntakeSession(domain=domain, known_facts=facts)

        next_q = self.intake_session.next_question()
        if next_q is not None:
            self.state = "intake_question"
            return OrchestratorStageResult(
                stage="intake_question",
                field_key=next_q["field_key"],
                question_text=next_q["question_text"],
            )

        # Checklist already full from first message
        return self._finish_intake()

    def answer_question(self, field_key: str, answer_text: str) -> OrchestratorStageResult:
        """
        Records the user's answer to a pending intake question and either:
        - returns the next required question, or
        - finishes intake and executes QA + Citation Verification.
        """
        if self.intake_session is None:
            raise ValueError("Session has not started intake. Call start() first.")

        if len(answer_text) > MAX_MESSAGE_LENGTH:
            self.state = "message_too_long"
            return OrchestratorStageResult(
                stage="message_too_long",
                message=(
                    f"Please keep your message under {MAX_MESSAGE_LENGTH} characters "
                    "and split longer situations into a few messages."
                ),
            )

        self.intake_session.record_answer(field_key, answer_text)

        next_q = self.intake_session.next_question()
        if next_q is not None:
            self.state = "intake_question"
            return OrchestratorStageResult(
                stage="intake_question",
                field_key=next_q["field_key"],
                question_text=next_q["question_text"],
            )

        return self._finish_intake()

    def proceed(self) -> OrchestratorStageResult:
        """
        Proceed with the pipeline (e.g. after a final_check_gap has been surfaced,
        to proceed directly to QA without adding more facts).
        """
        return self._finish_intake()

    def _finish_intake(self) -> OrchestratorStageResult:
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
                return OrchestratorStageResult(stage="final_check_gap", gap=gap)

        case_brief = self.intake_session.to_case_brief()
        qa_result = answer_question(case_brief)

        retrieved_chunks = qa_result.get("retrieved_chunks", [])
        if logger.isEnabledFor(logging.DEBUG):
            lines = [
                f"  {c.get('metadata', {}).get('section', '')} : {c.get('metadata', {}).get('title', '')}"
                for c in retrieved_chunks
            ]
            logger.debug("Retrieved chunks (section : title):\n%s", "\n".join(lines))

        verification = verify_citations(qa_result, retrieved_chunks)

        self.final_result = verification
        self.state = "complete"

        # Stage 5: Debate Mechanism (Adversarial Statutory Argumentation & Grey-Zone Adjudication)
        # Debate runs after Citation Verification (even on verification fallback),
        # using its OWN retrieval call with wider context window (DEBATE_RETRIEVAL_TOP_K).
        debate_result: DebateResult | None = None
        debate_chunks: list[dict[str, Any]] = []
        try:
            facts = case_brief.get("facts", {}) if isinstance(case_brief, (dict, CaseBrief)) else {}
            if not isinstance(facts, dict):
                facts = {}
            debate_query = _build_query_from_facts(facts)
            debate_chunks = retrieve(debate_query, top_k=DEBATE_RETRIEVAL_TOP_K)
            debate_result = run_debate(case_brief, debate_chunks)
        except Exception as e:
            logger.warning("Debate mechanism step failed: %s. Proceeding with debate=None.", e, exc_info=True)
            debate_result = None
            debate_chunks = []

        # Stage 6: Critic Agent (Final Re-Verification & Quality Pass)
        # Runs after debate (whether debate succeeded or fell back to None).
        critic_result: CriticResult | None = None
        try:
            critic_result = run_final_critique(case_brief, verification, debate_result)
        except Exception as e:
            logger.warning("Critic agent step failed: %s. Proceeding with critic=None.", e, exc_info=True)
            critic_result = None

        # Default: no critic revision, deliver the already-verified answer as-is.
        final_answer = verification["final_answer"]
        final_verified_sections = verification["verified_sections"]
        final_rejected_sections = verification["rejected_sections"]
        critic_revision_discarded = False

        critic_revised_text = bool(
            critic_result
            and critic_result.final_answer
            and critic_result.final_answer.strip() != verification["final_answer"].strip()
        )

        if critic_revised_text:
            # The Critic rewrote the verified answer - typically to weave in
            # context from the Debate Mechanism's wider (top_k=DEBATE_RETRIEVAL_TOP_K)
            # retrieval, which never itself passes through Citation Verification.
            # Re-audit the Critic's actual text before letting it reach the citizen,
            # against the UNION of both retrieval passes, so a citation introduced
            # from the Debate's context gets checked exactly like anything the QA
            # Agent originally cited (see Known Issue #10).
            combined_chunks = list(retrieved_chunks)
            seen_chunk_keys = {
                (c.get("metadata", {}).get("section", ""), c.get("text", "")) for c in retrieved_chunks
            }
            for chunk in debate_chunks:
                key = (chunk.get("metadata", {}).get("section", ""), chunk.get("text", ""))
                if key not in seen_chunk_keys:
                    combined_chunks.append(chunk)
                    seen_chunk_keys.add(key)

            try:
                reverification = reverify_answer_citations(critic_result.final_answer, combined_chunks)
            except Exception as e:
                logger.warning(
                    "Re-verification of Critic's revised answer failed: %s. "
                    "Failing safe by discarding the Critic's revision.",
                    e,
                    exc_info=True,
                )
                reverification = None

            if reverification is not None and reverification.verified:
                final_answer = reverification.final_answer
                final_verified_sections = reverification.verified_sections
                final_rejected_sections = reverification.rejected_sections
            else:
                # Fail-safe: the Critic's revision introduced (or we couldn't confirm
                # it didn't introduce) a citation that isn't actually grounded in
                # retrieved text. Never deliver an unaudited claim - fall back to the
                # pre-critic, already-verified answer instead, and say so explicitly
                # rather than silently swallowing the discrepancy.
                logger.warning(
                    "Critic's revised answer failed re-verification (unverified sections: %s). "
                    "Discarding revision and delivering the pre-critic verified answer instead.",
                    reverification.rejected_sections if reverification else "unknown",
                )
                final_answer = verification["final_answer"]
                final_verified_sections = verification["verified_sections"]
                final_rejected_sections = verification["rejected_sections"]
                critic_revision_discarded = True

        return OrchestratorStageResult(
            stage="complete",
            verified=verification["verified"],
            final_answer=final_answer,
            verified_sections=final_verified_sections,
            rejected_sections=final_rejected_sections,
            debate=debate_result,
            critic=critic_result,
            critic_revision_discarded=critic_revision_discarded,
        )