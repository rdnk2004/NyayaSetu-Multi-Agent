# Eval Set: Leakage Fix (v2)

## The problem this fixes

`labeled_cases.json`'s `specific_legal_question` field is concatenated
directly into the retrieval query (`qa_agent._build_query_from_facts`).
`check_eval_leakage.py` confirmed that **all 20/20 cases** named at least
one of their own `expected_cited_sections` inside that field -- e.g. case_01
asked "...under Section 39?" when `Section 39` was the answer being graded.
That means the reported 60% grounding rate is partly measuring whether the
system can echo a number the citizen already handed it, not whether
retrieval finds the right provision from a real description of a problem.

## Three dataset variants, same 20 cases, same `expected_cited_sections`

| File | `specific_legal_question` | `citizen_message` | Leak-free? |
|---|---|---|---|
| `labeled_cases.json` (original) | names section numbers | clean | No — 20/20 leak |
| `labeled_cases_v2.json` | rewritten in plain language, no section numbers | 5 ambiguous cases (15-19) still have the *antagonist* naming a section inside the narrative | Partial — 15/20 leak-free |
| `labeled_cases_v2_strict.json` | same as v2 | those 5 mentions masked to "a specific provision" | Yes — 0/20 leak |

**Why v2 and v2_strict are both worth keeping, not just the strict one:**
in cases 15-19, it's the *opposing party* (manufacturer/company) citing a
section number to the citizen as part of a real dispute -- e.g. "the company
invokes Section 87". That is realistic dispute content, not an artifact of
how the dataset was written; real citizens do sometimes get a clause number
thrown at them. Masking it (v2_strict) gives the cleanest signal on raw
retrieval ability; leaving it in (v2) tests something closer to the actual
deployed scenario, where the system also has to correctly *engage with* a
number the other side already raised, not just retrieve blind. Run both and
report the gap between them -- that gap is itself a data point about how much
the system leans on citizen-supplied hints. This is a judgement call, not
something I resolved unilaterally; flag it to a legal reviewer alongside the
question rewrites (see below).

## What's still manual / not yet trustworthy

1. **The question rewrites are mine, not a lawyer's.** I rewrote all 20
   `specific_legal_question` fields to remove section numbers while trying
   to preserve the actual legal issue each case is testing. I am not a
   lawyer and these have not been reviewed by one. Some rewrites simplify
   nuance (e.g. case_14's appeal-forum question) that a domain expert might
   phrase more precisely. Treat every rewritten question as a draft.
2. **`expected_cited_sections` (the ground truth itself) is untouched** --
   still your original author-labeled answer key, still the single biggest
   gap per the handoff (Section 9, point 1). Fixing the *questions* doesn't
   fix the *labels*. Getting even 3-5 of these cross-checked by someone with
   real Consumer Protection Act familiarity (a law student is enough to
   start) would matter more for credibility than adding more cases right
   now.
3. **Only 20 cases, one domain.** This fix doesn't address size or
   single-domain coverage (handoff Section 9, points 1 and 6).
4. **`check_eval_leakage.py` checks section-number leakage specifically.**
   It won't catch a question that leaks the answer some other way (e.g.
   naming a legal doctrine or remedy type verbatim). Worth a human skim of
   v2_strict's 20 questions for that before relying on it.

## Suggested next step

Run `run_evaluation.py` (once the harness is updated to point at
`labeled_cases_v2_strict.json` and prompt caching is disabled — see the
separate ablation-harness handoff) and compare the resulting grounding rate
against the 60% baseline. Expect it to drop; a real drop here is the honest
number, in the same spirit as the 50%→30% audit already documented in the
main README.