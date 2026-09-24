# Evaluation (Step F, in progress)

Two levels, evaluated separately so a failure can be attributed to the right stage.

## 1. Claim-level gold set: `claims_gold.jsonl` (to build)

Tests the **verifier alone**. Claims are fed directly into the verification graph, which bypasses
drafting and decomposition. One JSON object per line:

```json
{"id": "g01", "claim": "LumberChunker outperforms semantic chunking on GutenQA.", "expected": "supported", "evidence": ["lumberchunker-emnlp2024.pdf"], "category": "single_source"}
{"id": "g02", "claim": "Semantic chunking consistently outperforms fixed-size chunking.", "expected": "contested", "evidence": ["vectara-semantic-chunking-naacl2025.pdf", "lumberchunker-emnlp2024.pdf"], "category": "cross_source_conflict"}
{"id": "g03", "claim": "RAG was introduced by Google in 2018.", "expected": "contradicted", "evidence": ["lewis-rag-neurips2020.pdf"], "category": "perturbed_fact"}
{"id": "g04", "claim": "GPT-4 was trained on 13 trillion tokens.", "expected": "unverifiable", "evidence": [], "category": "out_of_corpus"}
```

Target: about 30 claims, balanced across these categories:

| Category | How to build it | Expected verdict |
|---|---|---|
| `single_source` | Copy a finding straight from one paper | supported |
| `perturbed_fact` | Take a true claim and change a number, name, year or direction | contradicted |
| `cross_source_conflict` | Claims where Vectara and LumberChunker disagree | contested* |
| `complementary` | Anthropic contextual-retrieval claims next to the chunking papers | supported (must NOT be contradicted) |
| `out_of_corpus` | Plausible RAG facts the corpus never discusses | unverifiable |

\* The verifier currently has only 3 verdicts, so a conflict comes out as `contradicted`. See
`docs/roadmap.md`, item P0-3.

Metrics: per-class precision and recall, a confusion matrix, and a separate
**false-contradiction rate** on `complementary` claims.

## 2. Question-level set: `questions.jsonl` (to build)

Tests **end to end**: 20 to 30 questions, each annotated with the verdict pattern you expect
(for example "must surface at least one conflict naming both chunking papers"). Run with
`make batch`. `smoke_questions.txt` is the starting point.

## Planned runner

`scripts/run_eval.py` (to write): loads `claims_gold.jsonl`, invokes `build_graph()` directly,
scores against `expected`, and writes `reports/eval_<timestamp>.md`. Also useful for ablations:
per-document vs. global retrieval, `top_k_per_doc` 2 vs. 3, and different LLMs.
