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

## 1b. Retrieval set: `retrieval_set.jsonl`

Tests the **search alone**: does it bring the judge the passage that holds the proof? Each line
is a claim and the exact quote it should retrieve, with no verdict:

```json
{"id": "r10", "claim": "LumberChunker beat the strongest baseline by 7.37% in DCG@20.",
 "filename": "lumberchunker-emnlp2024.pdf", "quote": "<the exact sentence>"}
```

32 pairs, 8 per document, plus every quote of the gold set: 44 quotes. Without labels to review or
LLM calls, a larger set is cheap, and 44 items narrow the uncertainty that 12 would leave.

`make eval-retrieval` (no LLM call) ranks every chunk of the quote's document by similarity to the
claim, in memory (same cosine ranking as pgvector, checked identical on all 40 claims), and records
the rank of the chunk that holds the quote. One run gives the recall for every k, for chunk sizes
of 256, 400 and 510 tokens, compared quote by quote. Results: [`results/retrieval.md`](results/retrieval.md).
The recall is a **lower bound**: another chunk may state the same fact in other words.

Ids: `g05` is a gold claim, `r04` a retrieval pair. A gold claim with several quotes gives one
target per quote, numbered in file order: `g05.1` is g05's first quote, `g05.2` its second.

## 2. Question-level set: `questions.jsonl`

Tests **end to end**: question → draft → claims → verdicts. The pipeline writes the claims
itself, so they cannot be labelled in advance. What is known in advance, and proven by exact
quotes, is which documents hold the answer and, for some questions, a `statement` the pipeline
must find contested or false. A quote's stance refers to the `statement` when there is one,
otherwise to the expected answer.

```json
{"id": "q05", "category": "conflict", "question": "Does semantic chunking improve retrieval ...?",
 "statement": "Chunking documents according to their content ... consistently improves retrieval.",
 "evidence": [{"filename": "lumberchunker-emnlp2024.pdf", "stance": "supports", "quote": "..."},
              {"filename": "vectara-semantic-chunking-naacl2025.pdf", "stance": "contradicts", "quote": "..."}],
 "note": "why we expect this"}
```

10 questions, 2 per category; `make eval-e2e` runs 5 of them (one per category) as a smoke
test that fits one day of the judge's free-tier quota. Each category has its quote rules (checked by `make check-gold`)
and its checks, read from the run's recorded events with no LLM call
(`src/claimverify/e2e_eval.py`). A question passes when all its checks pass.

| Category | Quotes | Checks |
|---|---|---|
| `single_source` | for the answer, one document | sources used · no false conflict · no contradiction |
| `multi_source` | for the answer, at least two documents | sources used · no false conflict · no contradiction |
| `conflict` | for and against the statement, from different documents | sources used · conflict found |
| `false_premise` | against the premise only | sources used · no false conflict · premise caught |
| `out_of_corpus` | none | no false conflict · nothing supported |

- **sources used**: every document holding a quote is cited by at least one verdict.
- **no false conflict**: no `contested` verdict.
- **conflict found**: a `contested` verdict citing a document of each side (in either order:
  the claim may be phrased for or against the statement).
- **no contradiction**: no claim of the answer is `contradicted`.
- **premise caught**: a verdict `contradicted` by the refuting document, or a correction
  `supported` by the very passage that refutes the premise.
- **nothing supported**: no claim is `supported` on a subject the corpus never discusses.

Each question also reports whether its quotes reached the drafter and the judge (a failure with
the proof never read is a retrieval failure), and the run records claims, near-identical claim
pairs, verdicts, tokens and time. The checks cannot tell whether each verdict is right:
`results/e2e_review.md` lists every claim with its verdict and evidence, to mark by hand.

Each question is its own run in `runs/`; `results/e2e_runs.json` records which run answered
which question, so a stopped evaluation resumes without paying again and scoring is free.

## Running the evaluations

| Command | What it does | LLM calls |
|---|---|---|
| `make check-gold` | checks both sets: labels, sources, every quote in the stored text | none |
| `make eval-retrieval` | ranks every chunk of each quote's document; recall at k for every method and chunk size | none |
| `make retrieval-details` | for each quote, the k chunks the judge would read and the proof's chunk, quote highlighted, in `runs/` (`METHOD=`, `SIZE=`, `K=`, default `config.yaml`'s) | none |
| `make chunks SIZE=256` | the corpus cut at that size, every chunk in `runs/` (the database keeps `config.yaml`'s size) | none |
| `make eval-judge` | the verifier of `config.yaml` on the 10 gold claims; each wrong verdict is blamed on retrieval (proof not read) or on the judge | about 40K tokens (`RESUME=1` continues a stopped run) |
| `make eval-e2e` | smoke test: the whole pipeline on 5 questions, one per category (`E2E_SMOKE` in the `Makefile`), then the scoring | about 150–200K tokens, one day of the judge's free-tier quota (`RESUME=1` continues) |
| `make eval-e2e ALL=1` | the same on the 10 questions; the smoke test's runs are reused with `RESUME=1` | about 400K tokens, 2–3 days of quota |
| `make score-e2e` | scores the recorded end-to-end runs again (after changing a check; `ALL=1` for the 10) | none |

Results are written to [`results/`](results/) and committed with the code that produced them.
