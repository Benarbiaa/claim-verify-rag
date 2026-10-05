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

## 2. Question-level set: `questions.jsonl` (to build)

Tests **end to end**: 20 to 30 questions, each annotated with the verdict pattern you expect
(for example "must surface at least one conflict naming both chunking papers"). Run with
`make batch`. `smoke_questions.txt` is the starting point.

## Running the evaluations

| Command | What it does | LLM calls |
|---|---|---|
| `make check-gold` | checks both sets: labels, sources, every quote in the stored text | none |
| `make eval-retrieval` | ranks every chunk of each quote's document; recall at k for every method and chunk size | none |
| `make eval-judge` | the verifier of `config.yaml` on the 10 gold claims; each wrong verdict is blamed on retrieval (proof not read) or on the judge | about 40K tokens (`RESUME=1` continues a stopped run) |

Results are written to [`results/`](results/) and committed with the code that produced them.
