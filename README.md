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
| 6 | Adversarial Debate Mechanism (grey-zone detection) | ✅ Built — **validated** |
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
appears in the source text, not invented).

**Infrastructure, not one of the 10 agents:**
- **Pipeline Orchestrator** (`orchestrator.py`) — a resumable,
  multi-turn state machine wiring Query Understanding → Intake →
  Retrieval → QA → Citation Verification into one flow.
- **QA Agent** (`qa_agent.py`) — a scaffolding module bridging
  Retrieval and Citation Verification before the Explainer Agent
  exists to take over final answer delivery.
- **Supporting modules:** `config.py` (centralized, `.env`-driven
  tunables), `models.py` (typed Pydantic contracts between agents,
  with dict-style backward compatibility — see its own docstring for
  the planned migration path), `pii_redaction.py` (best-effort
  redaction of citizen-derived text before it hits logs),
  `logging_config.py` (centralized `LOG_LEVEL`-driven logging setup).

---

## Current Scope & Limitations

This system currently operates on **one legal domain** (the Consumer Protection Act, 2019) with a **10-case precedent corpus**, both narrow by design at this stage of the project. Any claim of accuracy or reliability in this README should be read as strictly scoped to this narrow domain and corpus size, not as a general claim about Indian law coverage.

---

## Resolved Issues (real bugs found via end-to-end and evaluation-driven testing)

Worth documenting since each was found through actual testing — real
API calls, real data — not code review alone:

1. **Vector store contamination.** `chunk_text.py` had a leftover code
   path (predating `index_case_law.py`) that merged case law records
   into the same `legal_chunks` collection used for statutes. Fixed by
   removing case-law parsing from `chunk_text.py` entirely — that
   responsibility belongs solely to `index_case_law.py`, which uses a
   separate `case_law` collection.
2. **Citation Verification rejecting valid multi-section answers.**
   When an answer correctly cited two different sections for two
   different sub-claims, the verifier checked each section's text
   against the *entire* answer, rejecting valid citations because no
   single section covered the whole response. Fixed to check only the
   portion of the answer attributable to that specific section.
3. **Query construction diluted the citizen's actual legal question.**
   The intake checklist captured transaction facts (what was bought,
   what went wrong) but had no field for what the citizen was
   *specifically asking* (e.g. "can I appeal?", "does the
   self-employment exception apply?"). This caused retrieval to
   surface generic, topically-adjacent sections instead of the
   specific provision the question actually turned on. Fixed by adding
   a `specific_legal_question` checklist field, carried through into
   the retrieval query.
4. **Citation matching was too strict on sub-clause granularity.** A
   citation like `84(1)(a)` was rejected as "not retrieved" when only
   the parent section `84` had been retrieved as a chunk — even though
   `84`'s full text (including its sub-clauses) was genuinely present.
   Fixed with a compatibility check (`_sections_are_compatible`) that
   correctly matches sub-clause/parent relationships while still
   guaranteeing distinct clauses (e.g. `2(11)` vs `2(10)`) never
   cross-match.
5. **LLM non-determinism across runs is a real system characteristic,
   confirmed twice** — once informally (the original microwave
   investigation), and once rigorously: two eval runs of *identical*
   code produced different pass/fail outcomes on the same cases
   (`case_13`, `case_18`), traced to the QA Agent citing different
   sections on separate live calls. See the Evaluation Methodology
   note below — this is why single-run deltas should never be trusted
   to attribute cause to a code change.

Diagnostic logging (`qa_agent.py`'s built-query log,
`orchestrator.py`'s retrieved-chunks log) is routed through
`logger.debug()` via `logging_config.py`, with citizen-derived text
passed through `redact_pii()` before logging — available on demand via
`LOG_LEVEL=DEBUG` without needing to hand-edit files or risk leaking
PII into logs.

---

## Progress so far

**Retrieval pipeline (built and validated):**
- Direct PDF text extraction (`extract_pdf.py`) — no OCR needed, since
  source Acts are digital PDFs with selectable text. Correctly parses
  all sections of the Consumer Protection Act, 2019 (107/107, no gaps
  or duplicates).
- Legal-structure-aware chunking (`chunk_text.py`) — splits on numbered
  sub-clauses rather than raw word count, so each chunk is one atomic,
  precisely citable legal unit (e.g. `2(11)`). Statute-only — case law
  chunking is handled separately by `index_case_law.py`.
- Embedding + vector store (`embed_and_store.py`) — local, free
  embeddings (`multi-qa-mpnet-base-dot-v1`) stored in Chroma with
  inner-product distance.
- Retrieval function (`retrieve.py`) — parameterized by collection
  name, shared by both the statute and case-law retrieval paths
  (`retrieve_case_law.py` is a thin wrapper over it). A
  `scripts/check_contamination.py` utility verifies `legal_chunks`
  only contains real statute entries.

**Case law pipeline (built and validated):**
- `fetch_case_law.py` — Indian Kanoon API integration (shared-token
  and public-private-key HMAC-signed auth), with per-request cost
  logging and "powered by IKanoon" attribution handling. Ingested 10
  landmark Consumer Protection Act precedents into `data/raw/case_law/`.
- `index_case_law.py` / `retrieve_case_law.py` — separate `case_law`
  Chroma collection, same embedding model and distance metric as the
  statute path.
- `landmark_case_agent.py` — retrieves candidate precedent cases and
  generates a grounded relevance explanation per case. Source URLs and
  metadata are copied programmatically from retrieved chunks, never
  generated by the LLM.

**Intake pipeline (built, logic-tested with mocked LLM calls):**
- `domain_checklists.py` — explicit, inspectable checklist of required
  facts per domain, including a `specific_legal_question` field
  (see Resolved Issues) so the citizen's actual question — not just
  the transaction facts — drives retrieval.
- `query_understanding.py` — single-pass extraction of domain + known
  facts. Never guesses — leaves a field blank rather than inferring an
  unstated fact, and refuses to fill a field with a generic
  placeholder word when no real value was given.
- `intake_agent.py` — asks one follow-up question at a time, stops
  once the checklist is satisfied, runs a final "anything critical
  missing?" pass before handoff.

**Answer + verification pipeline (built and validated end-to-end):**
- `qa_agent.py` — answers strictly grounded in retrieved text, citing
  exact section numbers per sub-claim. Returns "unclear" rather than
  guessing when retrieved chunks don't support an answer.
- `citation_verification_agent.py` — cross-checks every cited section
  against what was actually retrieved (with sub-clause/parent
  compatibility, see Resolved Issues), then an LLM judgment pass
  confirming the cited text genuinely supports the specific claim
  attributed to it. An answer with zero citations is never trivially
  treated as "verified" — it must actually ground at least one claim.
  Surfaces the source Act's most recent `as_of_date` among verified
  sections in the final answer. Logs every rejection with a reason.

**Adversarial Debate Mechanism (`debate_mechanism.py`, built and validated):**
- Two grounded LLM calls argue opposing interpretations (plaintiff and
  defense) of the same retrieved provisions, followed by an impartial
  judge call determining whether the dispute is a genuine grey zone or
  one side is clearly correct. Plaintiff and defense calls run
  concurrently (independent of each other; the judge call depends on
  both and runs after).
- Uses a wider retrieval `top_k` (8) than QA Agent's `top_k` (5) —
  confirmed via real-case testing that a judge needs visibility into
  adjacent, potentially-countervailing provisions to make a
  well-grounded ambiguity determination; a narrower top-k tuned for
  direct question-answering can hide the exact clause that resolves
  (or properly complicates) the ambiguity.

**Orchestrator (`orchestrator.py`):**
- Resumable multi-turn state machine: `start()` → `answer_question()`
  loop → `proceed()` past an optional final-check gap → `"complete"`.
- Enforces a per-message length limit (`MAX_MESSAGE_LENGTH`, checked
  before any LLM call) to bound cost and prevent abuse.

**LLM client (`llm_client.py`):** Gemini API integration with real
cost/safety guardrails — prompt caching, session call budget cap
(isolated per-session via `LLMSessionGuard`, not shared globally
across concurrent users), per-minute rate limiting, retry with backoff
(fails fast on quota errors instead of burning retries on a call that
can't succeed). A shared `safe_parse_llm_json()` helper handles
fail-safe JSON parsing consistently across every agent.

**Domains:**
- Consumer Protection Act, 2019 — fully extracted, chunked, and validated.
- Precedent case law — 10 landmark Consumer Protection judgments
  ingested and validated.
- Second domain — not yet chosen / sourced.

**Tests:** 69 tests across `test_intake_flow.py`,
`test_llm_client_guards.py`, `test_qa_agent.py`,
`test_citation_verification_agent.py`, `test_orchestrator.py`,
`test_landmark_case_agent.py`, `test_debate_mechanism.py`,
`test_chunk_text.py`, `test_config.py`, `test_models.py`,
`test_pii_redaction.py`, `test_prompt_injection_resistance.py`,
`test_retrieve.py` — all passing, enforced on every push/PR via CI.

---

## Project structure

```
├── .github/
│   └── workflows/
│       └── test.yml                    # CI: runs full test suite on every push/PR
├── data/
│   ├── raw/
│   │   ├── consumer-protection-act-2019_sections.txt
│   │   └── case_law/                   # structured landmark cases (.txt)
│   ├── processed/                      # chunks.json (statute only, generated)
│   ├── eval/                           # labeled_cases.json, run results
│   └── chroma_db/                      # vector store (generated, gitignored)
│                                        # two collections: legal_chunks + case_law
├── src/
│   ├── extract_pdf.py                  # PDF -> section-tagged .txt
│   ├── chunk_text.py                   # statute sections -> retrieval chunks
│   ├── embed_and_store.py              # chunks -> embeddings -> vector store
│   ├── retrieve.py                     # query -> top-k relevant chunks (parameterized by collection)
│   ├── fetch_case_law.py               # Indian Kanoon API ingestion pipeline
│   ├── index_case_law.py               # case law -> embeddings -> vector store
│   ├── retrieve_case_law.py            # thin wrapper over retrieve.py
│   ├── domain_checklists.py            # required-fact checklist per domain
│   ├── query_understanding.py          # first-pass domain + fact extraction
│   ├── intake_agent.py                 # follow-up question state machine
│   ├── qa_agent.py                     # retrieval-grounded answer generation
│   ├── citation_verification_agent.py  # per-section citation cross-check
│   ├── landmark_case_agent.py          # precedent retrieval + grounded explanation
│   ├── debate_mechanism.py             # plaintiff/defense/judge grey-zone detection
│   ├── orchestrator.py                 # end-to-end multi-turn state machine
│   ├── llm_client.py                   # Gemini API wrapper + guardrails
│   ├── config.py                       # centralized, .env-driven tunables
│   ├── models.py                       # typed inter-agent contracts (Pydantic)
│   ├── pii_redaction.py                # best-effort log-sanitization
│   └── logging_config.py               # centralized LOG_LEVEL setup
├── scripts/                            # real-API validation, diagnostic, and eval scripts
│   ├── validate_real_llm.py
│   ├── validate_orchestrator_real.py
│   ├── validate_landmark_case_real.py
│   ├── validate_debate_real.py
│   ├── run_evaluation.py               # labeled-case benchmark, real API
│   └── check_contamination.py
├── tests/                              # 69 tests, see Progress so far
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
cp .env.example .env            # fill in GEMINI_API_KEY & Indian Kanoon credentials
```

`config.py` centralizes every tunable (retrieval `top_k` per agent,
rate limits, message length limits, log level) with sensible defaults
— see `.env.example` for the full list of overridable settings.

### Logging Configuration

By default, logs are emitted at `INFO` level. To enable detailed debug
traces (PII-redacted before logging):

```bash
# In .env:
LOG_LEVEL=DEBUG
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
python scripts/validate_debate_real.py
python scripts/run_evaluation.py
```

---

## Evaluation Results

Benchmark on 20 labeled Consumer Protection scenarios (14 clear-cut,
6 ambiguous/grey-zone), run live against the real Gemini API.

The evaluation labels went through an honesty audit partway through
this project: an early run scored **50.0% (10/20)** under labels that
turned out to be over-permissive — several cases accepted generic,
topically-adjacent citations (e.g. a catch-all remedies section) as a
"match" even when the answer never engaged with what was actually
asked. Auditing and narrowing those labels to require genuine
engagement with each case's specific legal question produced an
honest, stricter baseline of **30.0% (6/20)** — a real drop, but a
trustworthy number instead of an inflated one.

From that honest baseline, two fixes (see Resolved Issues #3 and #4 —
the `specific_legal_question` field, and sub-clause/parent citation
matching) drove real, verified improvement:

| Stage | Citation Match Rate | Note |
|---|---|---|
| Honest baseline (strict labels) | 30.0% (6/20) | After auditing out over-permissive labels |
| After query + citation-matching fixes | 50.0% (10/20) | Verified case-by-case: 7 genuine improvements, 3 cases moved the other way (see variance note below) |
| Current | **60.0%** (12/20) | Further verified improvement |

| Metric | Current | Description |
|---|---|---|
| Citation Rejection Rate (Hallucination Proxy) | 3.4% (1/29) | % of generated citations flagged and rejected by Citation Verification |
| Grey-Zone Detection Accuracy | 66.7% (4/6) | % of ambiguous disputes correctly classified as `is_grey_zone=True` |

*Detailed per-case outputs are saved to `data/eval/results_<timestamp>.json` for audit and inspection.*

### Evaluation Methodology & Variance Note

> [!WARNING]
> **LLM non-determinism is real and confirmed, not theoretical.** Every
> pipeline stage that calls an LLM (fact extraction, answer generation,
> citation auditing) can produce slightly different output on separate
> live runs of *identical* code. This was directly confirmed: two runs
> of the same code showed `case_13` and `case_18` flipping pass/fail,
> traced to the QA Agent citing different sections on each call — not
> a code regression.
>
> **Do not attribute cause from a single-run diff.** Before trusting an
> apparent improvement or regression, run the evaluation 2-3 times to
> establish variance bounds, and only trust a delta that clearly
> exceeds that natural noise.

---

## Next steps

**Second domain** — choosing and sourcing it, extracting and chunking
using the existing pipeline as reference, spot-checking extraction
against the source since the section-parsing logic is a heuristic
tuned on one Act's formatting.

**Remaining agents:** Document-Drafting Agent, Risk/Escalation Agent,
Plain-Language Explainer Agent, Adversarial Critic Agent (the last of
these audits the *combined* pipeline output, so it's a natural
capstone once the others exist).

**Evaluation depth:** the current 20-case labeled set covers one
domain; expanding it once domain 2 exists, and running the
2-3-pass variance-check methodology described above before trusting
future deltas.

A frontend (React/Next, served via a FastAPI backend) is being built
in parallel, decoupled from the agent pipeline via a fixed API
contract once agent output shapes stabilize.