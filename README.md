# NyayaSetu — Multi-Agent AI for Indian Law

[![Tests](https://github.com/rdnk2004/NyayaSetu-Multi-Agent/actions/workflows/test.yml/badge.svg)](https://github.com/rdnk2004/NyayaSetu-Multi-Agent/actions/workflows/test.yml)

A multi-agent AI system that helps citizens understand their legal
situation in plain language, without needing a lawyer to explain the
basics — while still directing them to a lawyer when a situation is
high-stakes.

**Core design principle:** the system never answers from an LLM's own
trained memory. Every legal claim must trace back to a retrieved,
dated, source-linked document from the actual Act or precedent-setting
case law. Hallucination is treated as a retrieval and verification
problem, not something solved by clever prompting.

Scoped to two legal domains for this phase — broad coverage across
"every law" is an explicit non-goal.

---

## Architecture

The system is a pipeline of 10 specialized agents, each with a narrow job:

| # | Agent | Status |
|---|-------|--------|
| 1 | Query Understanding Agent | ✅ Built — skeleton |
| 2 | Intelligent Intake Agent | ✅ Built — skeleton |
| 3 | Retrieval Agent (RAG) | ✅ Built — **validated** |
| 4 | Landmark Case Learning Agent | ✅ Built — **validated** |
| 5 | Citation Verification Agent | ✅ Built — **validated** |
| 6 | Adversarial Debate Mechanism (grey-zone detection) | ⬜ Not started |
| 7 | Document-Drafting Agent | ⬜ Not started |
| 8 | Risk / Escalation Agent | ⬜ Not started |
| 9 | Plain-Language Explainer Agent | ⬜ Not started |
| 10 | Adversarial Critic Agent | ⬜ Not started |

**"Skeleton" vs "validated"** — an important distinction, not a
formality: *skeleton* means the code's logic is correct and covered by
unit tests, but those tests mock the LLM call, so the agent has never
actually been run against real model output. *Validated* means it's
been run against real data end-to-end, including a manual spot-check
of specific claims (e.g. confirming a cited section number actually
appears in the source text, not invented) — and, for Citation
Verification specifically, a real multi-round debugging cycle that
found and fixed genuine bugs (see below).

**Infrastructure, not one of the 10 agents:**
- **Pipeline Orchestrator** (`orchestrator.py`) — a resumable,
  multi-turn state machine wiring Query Understanding → Intake →
  Retrieval → QA → Citation Verification into one flow. Validated
  end-to-end against a real multi-turn conversation (see Resolved
  Issues below).
- **QA Agent** (`qa_agent.py`) — a scaffolding module bridging
  Retrieval and Citation Verification before the Explainer Agent
  exists to take over final answer delivery.

---

## Resolved Issues (real bugs found via end-to-end testing)

A real multi-turn test case (citizen reporting a microwave that
"sparks violently") surfaced three separate, genuine bugs in sequence
— worth documenting since each was found through actual end-to-end
testing, not code review alone:

1. **Vector store contamination.** `chunk_text.py` had a leftover code
   path (predating `index_case_law.py`) that parsed case law files and
   merged them into the same `legal_chunks` collection used for
   statutes. Case law records were showing up disguised as statute
   sections in retrieval results. Fixed by removing the case-law
   parsing entirely from `chunk_text.py` — that responsibility belongs
   solely to `index_case_law.py`, which correctly uses a separate
   `case_law` collection.
2. **Citation Verification rejecting valid multi-section answers.**
   When an answer correctly cited two different sections for two
   different sub-claims (e.g. Section 84 for liability, Section 39(1)
   for remedies), the verifier was checking each section's text
   against the *entire* answer, rejecting valid citations simply
   because no single section covered the whole response. Fixed by
   updating the verification prompt to check only the portion of the
   answer attributable to that specific section.
3. Along the way, confirmed a **non-bug system characteristic worth
   knowing**: `understand_query()`'s LLM-based fact extraction is not
   perfectly deterministic — the same citizen message can produce
   slightly different extracted facts across runs, which can affect
   downstream retrieval. Not something to "fix," just something to
   account for when debugging an unexpected result — rerun before
   assuming a retrieval or prompt bug.

Diagnostic print statements added during this investigation
(`qa_agent.py`'s built-query print, `orchestrator.py`'s retrieved-chunks
print) are intentionally still in the code — useful for future
debugging, kept as a conscious choice rather than forgotten scaffolding.

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
  (e.g. `2(11)`, not a fragment cut mid-sentence). Statute-only —
  case law chunking is handled separately by `index_case_law.py`.
- Embedding + vector store (`embed_and_store.py`) — local, free
  embeddings (`multi-qa-mpnet-base-dot-v1`, tuned for question→passage
  matching) stored in Chroma with inner-product distance.
- Retrieval function (`retrieve.py`) — tested against real queries on
  the real 107-section corpus; correct answer lands in the top 5
  results consistently. A `scripts/check_contamination.py` utility
  exists to verify the `legal_chunks` collection only contains real
  statute entries.

**Case law pipeline (built and validated):**
- `fetch_case_law.py` — Indian Kanoon API integration, supporting both
  shared-token and public-private-key HMAC-signed authentication per
  their official API terms. Logs estimated per-request cost in INR as
  it runs. Handles "powered by IKanoon" attribution per their terms.
  Ingested 10 landmark Consumer Protection Act precedents (deficiency
  in service, product liability, jurisdiction disputes) into
  `data/raw/case_law/`, each with court, date, source URL, and the
  court's actual reasoning (not just the outcome).
- `index_case_law.py` / `retrieve_case_law.py` — embeds and indexes
  case reasoning into a separate Chroma collection (`case_law`, kept
  distinct from statute chunks), same embedding model and distance
  metric as the statute retrieval pipeline for consistency.
- `landmark_case_agent.py` — retrieves candidate precedent cases for a
  citizen's situation and generates a grounded relevance explanation
  per case. Source URLs and metadata are copied programmatically from
  retrieved chunks, never generated by the LLM, guaranteeing they can't
  be hallucinated or altered. Real-key validated: spot-checked a
  specific statutory citation the LLM included in its explanation
  (Section 84) against the actual source case text and confirmed it
  was genuinely present, not invented.

**Intake pipeline (built, logic-tested with mocked LLM calls):**
- `domain_checklists.py` — explicit, inspectable checklist of required
  facts per domain. "Confidence" is mechanical (checklist full), not
  an opaque LLM self-report.
- `query_understanding.py` — single-pass extraction of domain + known
  facts from a citizen's first message. Never guesses — leaves a field
  blank rather than inferring an unstated fact (including refusing to
  fill a field with a generic placeholder word like "seller" when no
  real name was given). Fact extraction is LLM-based and can vary
  slightly run to run — see Resolved Issues above.
- `intake_agent.py` — asks one follow-up question at a time for the
  highest-priority missing field, stops once the checklist is
  satisfied (or a safety-valve question limit is hit), runs a final
  "anything critical missing?" pass before handoff.

**Answer + verification pipeline (built and validated end-to-end):**
- `qa_agent.py` — takes a completed case brief, retrieves candidate
  chunks, and answers strictly grounded in retrieved text, citing
  exact section numbers, attributing each sub-claim to the section
  that actually supports it. Returns "unclear" rather than guessing
  when retrieved chunks don't support an answer. Exposes the retrieved
  chunks it used, so downstream verification doesn't need to
  re-retrieve.
- `citation_verification_agent.py` — cross-checks every cited section
  against what was actually retrieved (exact match), then uses an LLM
  judgment pass to confirm the cited section's text genuinely supports
  the specific claim attributed to it (not the entire answer — fixed
  after real-world testing, see Resolved Issues). Any citation that
  fails either check causes that portion of the answer to fall back to
  a safe "needs manual review" response rather than reaching the user
  unverified. Logs every rejection with a reason.

**Orchestrator (`orchestrator.py`):**
- Resumable multi-turn state machine: `start()` → `answer_question()`
  loop → `proceed()` past an optional final-check gap → `"complete"`.
- Routes a citizen's message through Query Understanding → Intake →
  QA → Citation Verification automatically, surfacing intake questions
  one at a time to the caller.
- Validated end-to-end against multiple real multi-turn conversations,
  including a full debugging cycle that resolved three real bugs (see
  Resolved Issues above).

**LLM client (`llm_client.py`):** Gemini API integration with real
cost/safety guardrails — prompt caching, session call budget cap,
per-minute rate limiting, retry with backoff (fails fast on quota
errors instead of burning retries on a call that can't succeed).

**Domains:**
- Consumer Protection Act, 2019 — fully extracted, chunked, and validated.
- Precedent case law — 10 landmark Consumer Protection judgments
  ingested and validated.
- Second domain — not yet chosen / sourced.

**Tests:** `test_intake_flow.py`, `test_llm_client_guards.py`,
`test_qa_agent.py`, `test_citation_verification_agent.py`,
`test_orchestrator.py`, `test_landmark_case_agent.py` — 26 tests, all
passing.

---

## Project structure

```
├── data/
│   ├── raw/
│   │   ├── consumer-protection-act-2019_sections.txt   # section-tagged Act
│   │   └── case_law/                                   # structured landmark cases (.txt)
│   ├── processed/                                      # chunks.json (statute only, generated)
│   └── chroma_db/                                      # vector store (generated, gitignored)
│                                                        # two collections: legal_chunks + case_law
├── src/
│   ├── extract_pdf.py                  # PDF -> section-tagged .txt
│   ├── chunk_text.py                   # statute sections -> retrieval chunks
│   ├── embed_and_store.py              # chunks -> embeddings -> vector store
│   ├── retrieve.py                     # query -> top-k relevant statute chunks
│   ├── fetch_case_law.py               # Indian Kanoon API ingestion pipeline
│   ├── index_case_law.py               # case law -> embeddings -> vector store
│   ├── retrieve_case_law.py            # query -> top-k relevant case law
│   ├── domain_checklists.py            # required-fact checklist per domain
│   ├── query_understanding.py          # first-pass domain + fact extraction
│   ├── intake_agent.py                 # follow-up question state machine
│   ├── qa_agent.py                     # retrieval-grounded answer generation
│   ├── citation_verification_agent.py  # per-section citation cross-check
│   ├── landmark_case_agent.py          # precedent retrieval + grounded explanation
│   ├── orchestrator.py                 # end-to-end multi-turn state machine
│   └── llm_client.py                   # Gemini API wrapper + guardrails
├── scripts/                            # real-API validation & diagnostic scripts
│   ├── validate_real_llm.py            # Query Understanding + Intake, real key
│   ├── validate_orchestrator_real.py   # full pipeline, real key
│   ├── validate_landmark_case_real.py  # Landmark Case Agent, real key
│   └── check_contamination.py          # verifies legal_chunks has no stray case-law entries
├── tests/
│   ├── test_intake_flow.py
│   ├── test_llm_client_guards.py
│   ├── test_qa_agent.py
│   ├── test_citation_verification_agent.py
│   ├── test_orchestrator.py
│   └── test_landmark_case_agent.py
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
cp .env.example .env            # then fill in GEMINI_API_KEY & Indian Kanoon credentials
```

## Running the retrieval pipeline

```bash
python src/chunk_text.py
python src/embed_and_store.py   # downloads the embedding model on first run
python src/retrieve.py
python scripts/check_contamination.py   # verify legal_chunks is clean
```

## Running case law ingestion + indexing

```bash
python src/fetch_case_law.py
python src/index_case_law.py
python src/retrieve_case_law.py
```

## Running the tests

```bash
PYTHONPATH=src python -m pytest tests/ -v
```

## Running real-API validation (not mocked — uses your actual keys)

```bash
python scripts/validate_real_llm.py
python scripts/validate_orchestrator_real.py
python scripts/validate_landmark_case_real.py
```

---

## Next steps

**Adversarial Debate Mechanism** — two agents argue opposing
interpretations of the same provision; a judge agent surfaces genuine
disagreement as a grey zone.

**Second domain** — choosing and sourcing it, extracting and chunking
using the existing pipeline as reference, spot-checking extraction
against the source since the section-parsing logic is a heuristic
tuned on one Act's formatting.

**Later:** Document-Drafting Agent, Risk/Escalation Agent,
Plain-Language Explainer Agent, Adversarial Critic Agent, security
hardening (PII redaction, prompt-injection defense), evaluation
against a labeled test set.

A frontend (React/Next, served via a FastAPI backend) is being built
in parallel, decoupled from the agent pipeline via a fixed API
contract once agent output shapes stabilize.
```