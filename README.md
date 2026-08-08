Here's the full README, reflecting the actual current state of the repo (not the day-based framing from our tracker — kept it progress-based like you asked):

```markdown
# NyayaSetu — Multi-Agent AI for Indian Law

A multi-agent AI system that helps citizens understand their legal
situation in plain language, without needing a lawyer to explain the
basics — while still directing them to a lawyer when a situation is
high-stakes.

**Core design principle:** the system never answers from an LLM's own
trained memory. Every legal claim must trace back to a retrieved,
dated, source-linked document from the actual Act. Hallucination is
treated as a retrieval and verification problem, not something solved
by clever prompting.

Scoped to two legal domains for this phase — broad coverage across
"every law" is an explicit non-goal.

---

## Architecture

The system is a pipeline of specialized agents, each with a narrow job:

| # | Agent | Status |
|---|-------|--------|
| 1 | Query Understanding Agent | ✅ Built |
| 2 | Intelligent Intake Agent | ✅ Built |
| 3 | Retrieval Agent (RAG) | ✅ Built |
| 4 | Landmark Case Learning Agent | ⬜ Not started |
| 5 | Citation Verification Agent | ⬜ Not started |
| 6 | Adversarial Debate Mechanism (grey-zone detection) | ⬜ Not started |
| 7 | Document-Drafting Agent | ⬜ Not started |
| 8 | Risk / Escalation Agent | ⬜ Not started |
| 9 | Plain-Language Explainer Agent | ⬜ Not started |
| 10 | Adversarial Critic Agent | ⬜ Not started |

Orchestration wiring these together, security hardening, and formal
evaluation against a labeled test set come after the individual agents
are built.

---

## Progress so far

**Retrieval pipeline (verified working):**
- Direct PDF text extraction (`extract_pdf.py`) — no OCR needed, since
  source Acts are digital PDFs with selectable text. Correctly parses
  all sections of the Consumer Protection Act, 2019 (107/107, no gaps
  or duplicates).
- Legal-structure-aware chunking (`chunk_text.py`) — splits on numbered
  sub-clauses (e.g. definitions, sub-sections) rather than raw word
  count, so each chunk is one atomic, precisely citable legal unit
  (e.g. `Section 2(11)`, not a fragment cut mid-sentence).
- Embedding + vector store (`embed_and_store.py`) — local, free
  embeddings (`multi-qa-mpnet-base-dot-v1`, tuned for question→passage
  matching) stored in Chroma with inner-product distance.
- Retrieval function (`retrieve.py`) — tested against real queries;
  correct answer lands in the top 5 results consistently. (Rank-1 is
  the goal but not guaranteed alone — downstream agents are expected to
  reason over multiple candidates rather than trust rank-1 blindly.)

**Intake pipeline (verified working, tested with mocked LLM calls):**
- `domain_checklists.py` — explicit, inspectable checklist of required
  facts per domain. "Confidence" is mechanical (checklist full), not
  an opaque LLM self-report.
- `query_understanding.py` — single-pass extraction of domain + known
  facts from a citizen's first message. Never guesses — leaves a field
  blank rather than inferring an unstated fact.
- `intake_agent.py` — asks one follow-up question at a time for the
  highest-priority missing field, stops once the checklist is
  satisfied (or a safety-valve question limit is hit), runs a final
  "anything critical missing?" pass before handoff.
- `llm_client.py` — Gemini API integration with real cost/safety
  guardrails: prompt caching, session call budget cap, per-minute rate
  limiting, retry with backoff.

**Domains:**
- Consumer Protection Act, 2019 — fully extracted and chunked.
- Second domain — not yet chosen / sourced.

**Tests:** `tests/test_intake_flow.py` and `tests/test_llm_client_guards.py`,
both passing.

---

## Project structure

```
├── data/
│   ├── raw/              # section-tagged .txt source files (per Act)
│   ├── processed/        # chunks.json (generated)
│   └── chroma_db/        # vector store (generated, gitignored)
├── src/
│   ├── extract_pdf.py         # PDF -> section-tagged .txt
│   ├── chunk_text.py          # sections -> retrieval chunks
│   ├── embed_and_store.py     # chunks -> embeddings -> vector store
│   ├── retrieve.py            # query -> top-k relevant chunks
│   ├── domain_checklists.py   # required-fact checklist per domain
│   ├── query_understanding.py # first-pass domain + fact extraction
│   ├── intake_agent.py        # follow-up question state machine
│   └── llm_client.py          # Gemini API wrapper + guardrails
├── tests/
│   ├── test_intake_flow.py
│   └── test_llm_client_guards.py
├── .env.example
├── requirements.txt
└── README.md
```

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in your GEMINI_API_KEY
```

## Running the retrieval pipeline

```bash
python src/chunk_text.py
python src/embed_and_store.py   # downloads the embedding model on first run
python src/retrieve.py
```

## Running the tests

```bash
PYTHONPATH=src python tests/test_intake_flow.py
PYTHONPATH=src python tests/test_llm_client_guards.py
```

---

## Next steps

**Retrieval / agents:** Single QA Agent grounded in retrieval, followed
by the Citation Verification Agent — every citation the system
produces gets cross-checked against actually-retrieved text before
reaching the user, and the system says "unclear" rather than guessing
when nothing supports a claim.

**Second domain:** choosing and sourcing the second legal domain,
extracting and chunking it using the existing pipeline
(`extract_pdf.py` → `chunk_text.py`) as the reference — new PDFs
should be spot-checked against the source after extraction, since the
section-parsing logic is a heuristic tuned on one Act's formatting and
may need adjustment for different document layouts.

**Later:** Landmark Case Agent, orchestration across all agents, the
grey-zone adversarial debate mechanism, document drafting, risk
escalation, security hardening (PII redaction, prompt-injection
defense), and evaluation against a labeled test set.

A frontend (React/Next, served via a FastAPI backend) is being built
in parallel, decoupled from the agent pipeline via a fixed API
contract once agent output shapes stabilize.
```