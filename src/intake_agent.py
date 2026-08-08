"""
Intelligent Intake Agent

Takes over after Query Understanding. Its job:
  - look at the domain's checklist vs. facts collected so far
  - ask ONE question at a time for the highest-priority missing field
  - stop once every required field is filled (or the user has answered
    a max number of questions, so we don't loop forever on a vague case)
  - run a final "anything else important?" pass before handing off

This is designed as a small state machine (IntakeSession) rather than
one big function, because intake is inherently multi-turn: the API
layer calls next_question() -> shows it to the user -> gets an answer
-> calls record_answer() -> repeats.
"""

from domain_checklists import get_missing_required_fields, is_intake_complete
from llm_client import call_llm_structured
import json


MAX_QUESTIONS = 6  # safety valve - don't interrogate someone forever

FINAL_CHECK_PROMPT_TEMPLATE = """A citizen described a legal situation and answered \
some follow-up questions. Here is everything gathered so far:

Domain: {domain}
Facts: {facts_json}

Is there anything CRITICAL and commonly relevant to this type of case \
that seems to be missing, which isn't already covered by the facts \
above? Only flag something if it's genuinely important - do not invent \
concerns. Respond with ONLY a JSON object:
{{
  "missing_critical_info": "<a short description, or null if nothing critical is missing>"
}}
"""


class IntakeSession:
    def __init__(self, domain: str, known_facts: dict | None = None):
        self.domain = domain
        self.known_facts = dict(known_facts or {})
        self.questions_asked = 0
        self.finished = False

    def next_question(self) -> dict | None:
        """
        Returns the next question to ask, or None if intake is complete.

        Shape when a question exists:
            {"field_key": str, "question_text": str}
        """
        if self.finished:
            return None

        if self.questions_asked >= MAX_QUESTIONS:
            self.finished = True
            return None

        missing = get_missing_required_fields(self.domain, self.known_facts)
        if not missing:
            self.finished = True
            return None

        next_field = missing[0]  # checklist order = priority order
        return {"field_key": next_field["key"], "question_text": next_field["prompt"]}

    def record_answer(self, field_key: str, answer_text: str) -> None:
        """Store the user's answer against the field it was asked for."""
        self.known_facts[field_key] = answer_text.strip()
        self.questions_asked += 1

    def run_final_check(self) -> str | None:
        """
        One last LLM pass: "did we miss anything critical?" - only called
        once the checklist is full. Returns a short description of a gap,
        or None if nothing critical seems missing.
        """
        prompt = FINAL_CHECK_PROMPT_TEMPLATE.format(
            domain=self.domain,
            facts_json=json.dumps(self.known_facts, indent=2),
        )
        raw_response = call_llm_structured(prompt)
        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            return None
        return parsed.get("missing_critical_info")

    def is_ready(self) -> bool:
        """True once the checklist is satisfied (used by the pipeline
        to decide whether to hand off to Retrieval yet)."""
        return is_intake_complete(self.domain, self.known_facts)

    def to_case_brief(self) -> dict:
        """The structured handoff object the Retrieval Agent consumes."""
        return {
            "domain": self.domain,
            "facts": self.known_facts,
            "ready": self.is_ready(),
        }