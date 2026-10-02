# Evaluation (Step F, in progress)

Two levels, evaluated separately so a failure can be attributed to the right stage.

## 1. Claim-level gold set: `claims_gold.jsonl` (to build)

Tests the **verifier alone**. Claims are fed directly into the verification graph, which bypasses
drafting and decomposition. The correct verdict of each claim is known in advance and **proven by
an exact quote** from the source; every label is reviewed by a human (an LLM-written label graded
against an LLM judge would measure nothing). One JSON object per line:

```json
{"id": "g03", "category": "perturbed_fact", "claim": "LumberChunker uses GPT-4 to find chunk boundaries.",
 "expected": "contradicted",
 "evidence": [{"filename": "lumberchunker-emnlp2024.pdf", "stance": "contradicts", "quote": "<the exact sentence>"}],
 "note": "why this label, in one line"}
```

(shown on several lines here; one line per claim in the file)

| Field | Meaning |
|---|---|
| `expected` | `supported`, `contradicted`, `contested` or `unverifiable`, never `error` |
| `evidence` | the quotes that prove the label: `filename`, `stance` (`supports` / `contradicts`), `quote` (copied word for word) |
| `note` | why this label |

Rules, checked by `make check-gold` (`python -m claimverify.evaluation check-gold`), no LLM call:
`supported` needs a quote for and none against; `contradicted` a quote against and none for;
`contested` quotes on both sides from at least two documents; `unverifiable` no quote. Every quote
must appear in the **stored** (cleaned) text of its document, ignoring spaces, line breaks and
hyphens, so an invented or altered quote is refused. Every category must be present.

Target: **10 claims, 2 per category.** That is a smoke test of the verifier, not a statistical
measure: results are reported as counts ("1/2"), never as percentages.

| Category | How to build it | Expected verdict |
|---|---|---|
| `single_source` | Copy a finding straight from one paper | supported |
| `perturbed_fact` | Take a true claim and change a number, name, year or direction | contradicted |
| `cross_source_conflict` | Claims where Vectara and LumberChunker disagree | contested* |
| `complementary` | Anthropic contextual-retrieval claims next to the chunking papers | supported (must NOT be contradicted) |
| `out_of_corpus` | Plausible RAG facts the corpus never discusses | unverifiable |

\* `contested` exists since P0-3. Answers the judge failed to produce are labelled `error`,
never `unverifiable`, so they don't distort that class.

Metrics: per-class precision and recall, a confusion matrix, and a separate
**false-contradiction rate** on `complementary` claims.

## 2. Question-level set: `questions.jsonl` (to build)

Tests **end to end**: 20 to 30 questions, each annotated with the verdict pattern you expect
(for example "must surface at least one conflict naming both chunking papers"). Run with
`make batch`. `smoke_questions.txt` is the starting point.

## Planned runner

`scripts/run_eval.py` (to write): loads `claims_gold.jsonl`, invokes `build_graph()` directly,
scores against `expected`, and writes its results in a run folder under `runs/`. Also useful for ablations:
per-document vs. global retrieval, `top_k_per_doc` 2 vs. 3, and different LLMs.
