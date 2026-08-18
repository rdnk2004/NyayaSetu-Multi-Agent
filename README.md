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
| 1 | Query Understanding Agent | ✅ Built — skeleton |
| 2 | Intelligent Intake Agent | ✅ Built — skeleton |
| 3 | Retrieval Agent (RAG) | ✅ Built — **validated** |
| 4 | Landmark Case Learning Agent | ⬜ Not started |
| 5 | Citation Verification Agent | ✅ Built — skeleton |
| 6 | Adversarial Debate Mechanism (grey-zone detection) | ⬜ Not started |
| 7 | Document-Drafting Agent | ⬜ Not started |
| 8 | Risk / Escalation Agent | ⬜ Not started |
| 9 | Plain-Language Explainer Agent | ⬜ Not started |
| 10 | Adversarial Critic Agent | ⬜ Not started |

**"Skeleton" vs "validated"** — an important distinction, not a
formality: *skeleton* means the code's logic is correct and covered by
unit tests, but those tests mock the LLM call, so the agent has never
actually been run against real model output. *Validated* means it's
been tested against real data end-to-end. Only the Retrieval Agent has
cleared that second bar so far — the others are structurally sound but
unproven against real Gemini responses, real prompt quirks, and real
messy citizen phrasing.

There's also a scaffolding module, `qa_agent.py`, built as a
step toward orchestration - it's not one of the 10 blueprint agents
itself, but the bridge that lets Retrieval and Citation Verification
be tested together before the Explainer Agent exists to take over
final answer delivery.

Orchestration wiring these agents together, security hardening, and
formal evaluation against a labeled test set come after the individual
agents are built and validated.

---

## Progress so far

**Retrieval pipeline (built and validated):**
- Direct PDF text extraction (`extract_pdf.py`) — no OCR needed, since
  source Acts are digital PDFs with selectable text. Correctly parses
  all sections of the Consumer Protection Act, 2019 (107/107, no gaps
  or duplicates).
- Legal-structure-aware chunking (`chunk_text.py`) — splits on numbered
  sub-clauses (e.g. definitions, sub-sections) rather than raw word
  count, so each chunk is one atomic, precisely citable legal unit
  (e.g. `2(11)`, not a fragment cut mid-sentence).
- Embedding + vector store (`embed_and_store.py`) — local, free
  embeddings (`multi-qa-mpnet-base-dot-v1`, tuned for question→passage
  matching) stored in Chroma with inner-product distance.
- Retrieval function (`retrieve.py`) — tested against real queries on
  the real 107-section corpus; correct answer lands in the top 5
  results consistently.

**Intake pipeline (built, logic-tested with mocked LLM calls):**
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

**Answer + verification pipeline (built, logic-tested with mocked LLM calls):**
- `qa_agent.py` — takes a completed case brief, retrieves candidate
  chunks, and answers strictly grounded in retrieved text, citing
  exact section numbers. Returns "unclear" rather than guessing when
  retrieved chunks don't support an answer. Exposes the retrieved
  chunks it used, so downstream verification doesn't need to
  re-retrieve.
- `citation_verification_agent.py` — cross-checks every cited section
  against what was actually retrieved (exact match), then uses an LLM
  judgment pass to confirm the cited text genuinely supports the
  claim. Any citation that fails either check causes the whole answer
  to fall back to a safe "needs manual review" response rather than
  reaching the user unverified.

**LLM client (`llm_client.py`):** Gemini API integration with real
cost/safety guardrails — prompt caching, session call budget cap,
per-minute rate limiting, retry with backoff.

**Domains:**
- Consumer Protection Act, 2019 — fully extracted, chunked, and validated.
- Second domain — not yet chosen / sourced.

**Tests:** `test_intake_flow.py`, `test_llm_client_guards.py`,
`test_qa_agent.py`, `test_citation_verification_agent.py` — 18 tests,
all passing. All mock the LLM call — they prove logic correctness, not
real-world output quality.

---

## Project structure

```
├── data/
│   ├── raw/              # section-tagged .txt source files (per Act)
│   ├── processed/        # chunks.json (generated)
│   └── chroma_db/        # vector store (generated, gitignored)
├── src/
│   ├── extract_pdf.py                  # PDF -> section-tagged .txt
│   ├── chunk_text.py                   # sections -> retrieval chunks
│   ├── embed_and_store.py              # chunks -> embeddings -> vector store
│   ├── retrieve.py                     # query -> top-k relevant chunks
│   ├── domain_checklists.py            # required-fact checklist per domain
│   ├── query_understanding.py          # first-pass domain + fact extraction
│   ├── intake_agent.py                 # follow-up question state machine
│   ├── qa_agent.py                     # retrieval-grounded answer generation
│   ├── citation_verification_agent.py  # citation cross-check before output
│   └── llm_client.py                   # Gemini API wrapper + guardrails
├── tests/
│   ├── test_intake_flow.py
│   ├── test_llm_client_guards.py
│   ├── test_qa_agent.py
│   └── test_citation_verification_agent.py
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
PYTHONPATH=src python -m pytest tests/ -v
```

---

## Next steps

**Validate before building further:** Query Understanding, Intake, QA
Agent, and Citation Verification have only been tested with mocked LLM
calls. Before orchestration, run each against a real Gemini API key on
real sample citizen messages — check extraction quality, JSON
reliability, and whether citation verification is appropriately strict
without being overcautious.

**Second domain:** choosing and sourcing the second legal domain,
extracting and chunking it using the existing pipeline
(`extract_pdf.py` → `chunk_text.py`) as the reference — new PDFs
should be spot-checked against the source after extraction, since the
section-parsing logic is a heuristic tuned on one Act's formatting and
may need adjustment for different document layouts.

**Orchestration:** wire Query Understanding → Intake → Retrieval → QA
→ Citation Verification into a single real pipeline call, once the
pieces above are individually validated.

**Later:** Landmark Case Agent, the grey-zone adversarial debate
mechanism, document drafting, risk escalation, Plain-Language
Explainer Agent, Adversarial Critic Agent, security hardening (PII
redaction, prompt-injection defense), and evaluation against a labeled
test set.

A frontend (React/Next, served via a FastAPI backend) is being built
in parallel, decoupled from the agent pipeline via a fixed API
contract once agent output shapes stabilize.