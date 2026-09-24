# Architecture

```
question
   │
   ▼
[retrieval]      per-document top-k (claimverify/retrieval.py)
   │
   ▼
[draft]          LLM answer grounded in passages, with citations    (draft_answer.py)
   │
   ▼
[decompose]      LLM → atomic, self-contained claims (JSON)         (decompose_claims.py)
   │
   ▼
[verify loop]    LangGraph: retrieve(claim) → verdict(claim) → next (verify_claims.py)
   │
   ▼
report           supported / contradicted / unverifiable + justification (run_pipeline.py)
```

## Module map

| Module | Stage | Needs DB | Needs LLM | Needs GPU |
|---|---|---|---|---|
| `ingest.py` | A: parse → chunk → embed → store | yes | no | yes (CPU works) |
| `retrieval.py` | shared query embedding + search | yes | no | yes |
| `llm.py` | per-role LLM config (draft / decompose / verify) | no | — | no |
| `query_check.py` | retrieval sanity check | yes | no | yes |
| `draft_answer.py` | B: grounded draft | yes | yes | yes |
| `decompose_claims.py` | C: atomic claims | no | yes | no |
| `verify_claims.py` | D: per-claim verification graph | yes | yes | yes |
| `run_pipeline.py` | B → C → D + timed report | yes | yes | yes |

## Key design decisions

**1. Per-document retrieval, not global top-k.** With global top-k, one paper that matches the
query well can take every slot and hide the paper that disagrees with it. Retrieving the top-k
*per document* guarantees each source is heard. The cost is noise from irrelevant documents,
which the verdict prompt has to tolerate.

**2. Verification ignores the draft's citation.** Each claim is re-retrieved from scratch across
the whole corpus. The `cited_source` field is kept only for reporting. This is what lets the
system catch a claim that is true according to paper A but disputed by paper B.

**3. The judge is a different model from the author.** If one model writes the answer and then
checks it, its mistakes are correlated (whatever it misread while writing, it misreads the same
way while checking), and it tends to approve its own output. `llm.py` resolves a model, base
URL and key per role. By default the verifier is `llama-3.3-70b-versatile` (Meta), while the
drafter is `gpt-oss-120b` (OpenAI). Both run on Groq, so one key is enough, and each model has
its own rate-limit quota.

**4. One LLM call per stage.** Drafting, decomposition and verdicts are separate calls with
separate prompts, so each stage can be run, debugged and evaluated alone (every module has
its own CLI).

**5. The pipeline is pinned to English.** The corpus and `bge-base-en-v1.5` are English. An
earlier version produced claims in French, which silently degraded retrieval. Every prompt now
forces English output.

**6. The corpus disagrees for real.** The contradiction the system has to find comes from real
papers (Vectara vs. LumberChunker), not from injected synthetic errors.

## Data model

A single table, `chunks`: `chunk_id` (sha1(filename)[:12] + index), `doc_id`, `filename`,
`source_type`, `chunk_index`, `text`, `embedding VECTOR(768)`.
