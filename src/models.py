"""
NyayaSetu Inter-Agent Data Contracts & Domain Models.

Defines Pydantic models for structured data exchange across agents:
- CaseBrief: intake -> retrieval / QA / landmark case / debate
- QAResult: QA agent -> citation verification / orchestrator
- CitationVerificationResult: citation verification agent -> orchestrator
- LandmarkCase / LandmarkCaseResult: landmark case agent output
- DebateResult: debate mechanism output
- OrchestratorStageResult: orchestrator state transition output

All models inherit from NyayaSetuModel to provide dual interface compatibility:
strongly-typed attribute access (.status, .answer) AND backward-compatible dict
subscripting (model["status"], model.get("answer")) without requiring changes to
existing callers or tests that expect dict behavior.

NOTE ON ARCHITECTURE & MIGRATION SCAFFOLDING:
The dictionary emulation (__getitem__, get, __contains__, keys, etc.) in
NyayaSetuModel is intentional transitional scaffolding to allow safe, zero-breakage
migration. New code should exclusively use typed attribute access (.status, .answer).
In a planned stabilization pass, existing callers will be transitioned to attribute
access and the dict-emulation methods will be deprecated and removed.
"""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class NyayaSetuModel(BaseModel):
    """
    Base model providing dict subscripting and dictionary method compatibility
    as transitional scaffolding during the dict -> Pydantic migration.

    Preference for new code: use typed attribute access (e.g., `model.status`).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        if hasattr(self, item):
            val = getattr(self, item)
            if val is not None or item in self.model_fields_set:
                return val
        return default

    def __contains__(self, item: str) -> bool:
        if item in self.model_fields_set:
            return True
        return hasattr(self, item) and getattr(self, item) is not None

    def keys(self):
        return self.model_dump().keys()

    def values(self):
        return self.model_dump().values()

    def items(self):
        return self.model_dump().items()

    def __iter__(self):
        return iter(self.model_dump())


class CaseBrief(NyayaSetuModel):
    """
    Handoff contract from Intelligent Intake Agent to downstream agents
    (QA, Landmark Cases, Debate). Matches IntakeSession.to_case_brief().
    """
    domain: str = "unclear"
    facts: dict[str, Any] = Field(default_factory=dict)
    ready: bool = False


class QAResult(NyayaSetuModel):
    """
    Output of QA Agent answering a citizen's inquiry grounded in statutory chunks.
    """
    answer: str = ""
    cited_sections: list[str] = Field(default_factory=list)
    status: str = "unclear"  # "answered" | "unclear"
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)


class CitationVerificationDetail(NyayaSetuModel):
    """
    Per-citation audit verification status and reasoning.
    """
    supported: bool = False
    reason: str = ""


class CitationVerificationResult(NyayaSetuModel):
    """
    Output of Citation Verification Agent auditing statutory citations in QA answer.
    """
    verified: bool = False
    verified_sections: list[str] = Field(default_factory=list)
    rejected_sections: list[str] = Field(default_factory=list)
    final_answer: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class LandmarkCase(NyayaSetuModel):
    """
    A single precedent case with metadata programmatically copied from ChromaDB
    and a grounded relevance explanation.
    """
    case_title: str = ""
    court: str = ""
    date: str = ""
    source_url: str = ""
    attribution: str = ""
    relevance_explanation: str = ""


class LandmarkCaseResult(NyayaSetuModel):
    """
    Output of Landmark Case Agent containing retrieved precedent cases.
    """
    cases: list[LandmarkCase] = Field(default_factory=list)
    status: str = "no_relevant_cases"  # "found" | "no_relevant_cases"


class DebateResult(NyayaSetuModel):
    """
    Output of Debate Mechanism containing plaintiff/defense arguments and judicial verdict.
    """
    plaintiff_argument: str = ""
    plaintiff_cited_sections: list[str] = Field(default_factory=list)
    defense_argument: str = ""
    defense_cited_sections: list[str] = Field(default_factory=list)
    is_grey_zone: bool = False
    judge_summary: str = ""
    clearly_supported_side: str | None = None


class OrchestratorStageResult(NyayaSetuModel):
    """
    Output of CaseSession state transitions (start, answer_question, proceed).
    """
    stage: str
    message: str | None = None
    field_key: str | None = None
    question_text: str | None = None
    gap: str | None = None
    verified: bool | None = None
    final_answer: str | None = None
    verified_sections: list[str] = Field(default_factory=list)
    rejected_sections: list[str] = Field(default_factory=list)
