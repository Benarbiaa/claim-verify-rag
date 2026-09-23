# RAG Agentique avec Vérification de Véracité

Agentic RAG system that goes beyond plain retrieval-and-answer: it decomposes its own
draft answer into atomic factual claims, independently re-checks each claim against the
full corpus (across all sources, not just the one it originally cited), and returns a
verdict per claim — **supported**, **contradicted**, or **unverifiable** — with justification.

Built as a technical project for a PFE (final-year internship) application, targeting
AI engineering roles (agentic systems, RAG, data engineering).

Full specification: [`cahier-des-charges-agentic-rag-verification.md`](./cahier-des-charges-agentic-rag-verification.md).

## Why this project

Most student RAG demos trust retrieved chunks blindly. This system treats its own answer
as a set of falsifiable claims and fact-checks them — including catching cases where two
sources in the corpus genuinely disagree.

The corpus is deliberately chosen to contain a real, citable disagreement in the RAG
research literature: whether sophisticated chunking strategies (semantic chunking,
LLM-based chunking) actually outperform simple fixed-size chunking. Different papers
reach different conclusions — the corpus, not a synthetic injection, is where any
`contradicted` verdict has to come from.

## Corpus

| File | Source | Role |
|---|---|---|
| `Is Semantic Chunking Worth the Computational Cost?.pdf` | Vectara, NAACL 2025 Findings | Argues sophisticated chunking rarely pays off |
| `LumberChunker: Long-Form Narrative Document Segmentation.pdf` | EMNLP 2024 Findings | LLM-based chunking beating every baseline, including semantic chunking |
| `Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.pdf` | Lewis et al., NeurIPS 2020 | Original RAG paper — clean baseline/definitional claims |
| `anthropic-contextual-retrieval.md` | Anthropic engineering blog, 2024 | A different axis (chunk enrichment, not chunking method) — tests whether the system distinguishes "complementary technique" from "contradicts corpus" |

## Architecture

```
question
   │
   ▼
retrieval (per-document top-k — every source gets a chance to surface evidence,
           not just whichever document scores highest globally)
   │
   ▼
draft answer generation (LLM, grounded strictly in retrieved passages)
   │
   ▼
claim decomposition (LLM, splits the answer into atomic, self-contained,
                      independently checkable claims)
   │
   ▼
per-claim verification (LangGraph loop: independent per-document retrieval
                         for EACH claim + LLM verdict — ignores what the
                         draft answer originally cited)
   │
   ▼
verdicts: supported / contradicted / unverifiable, with justification
```

**Stack:** PostgreSQL + pgvector · `BAAI/bge-base-en-v1.5` embeddings (local, GPU) ·
Groq (`openai/gpt-oss-120b`) for generation/decomposition/verification · LangGraph for
the verification loop orchestration.

## Setup

```bash
pip install -r requirements.txt
```

PostgreSQL with the `pgvector` extension must be running:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Copy `.env.example` to `.env` and fill in your key:
```
GROQ_API_KEY=gsk_...
LLM_MODEL=openai/gpt-oss-120b
```

## Usage

**1. Ingest the corpus** (parses PDFs/MD, chunks, embeds, stores in pgvector):
```bash
python -m pipeline.ingest --corpus_dir ./corpus --db_url postgresql://rag_user:admin@localhost:5432/ragdb
```

**2. Run the full pipeline** (recommended — draft → decompose → verify, in one command,
with a saved report):
```bash
python -m pipeline.run_pipeline --db_url postgresql://rag_user:admin@localhost:5432/ragdb \
    --query "Does semantic chunking improve retrieval performance compared to fixed-size chunking?"
```
Produces `reports/report_<timestamp>.md` and `.json` — draft answer, claims, verdicts,
and per-stage timings.

Batch mode, for running several questions in one pass (useful for benchmarking):
```bash
python -m pipeline.run_pipeline --db_url ... --questions_file eval_questions.txt
```

**Individual stages** can also be run separately, useful for debugging one step in
isolation:
```bash
python -m pipeline.draft_answer --db_url ... --query "..." --save_to draft.txt
python -m pipeline.decompose_claims --answer_file draft.txt --save_json claims.json
python -m pipeline.verify_claims --claims_file claims.json --db_url ... --save_json verdicts.json
```

**Retrieval sanity check** (no LLM calls, just inspect what gets retrieved):
```bash
python -m pipeline.query_check --db_url ... --query "..." --per_document
```

**Debug a single claim's retrieval** (used to diagnose false "unverifiable" verdicts):
```bash
python -m pipeline.verify_claims --db_url ... --debug_claim "..."
```

## Project status

- [x] Corpus selected and ingested (4 documents, chunked, embedded, stored)
- [x] Retrieval validated — per-document search guarantees cross-source coverage
- [x] Draft answer generation, grounded and cited
- [x] Claim decomposition into atomic, self-contained claims
- [x] Per-claim independent verification with supported/contradicted/unverifiable verdicts
- [x] End-to-end pipeline runner with timing + saved reports
- [ ] Formal evaluation set (20-30 questions, known expected verdicts) — Step F
- [ ] Minimal interface (CLI/small UI) — Step G
- [ ] Technical report (rapport)

## Known limitations

- **Claim decomposition can produce near-duplicate claims** from repeated conclusions in
  the draft answer (e.g. an intro and a summary restating the same point) — not
  deduplicated yet, so verification does some redundant work.
- **Retrieval vs. free-tier token limits** — per-document retrieval with too high a
  `top_k_per_doc` can exceed Groq's free-tier tokens-per-minute cap on larger models;
  currently tuned to `top_k_per_doc=2` to stay under the limit.
- **Verification cost scales linearly** with claim count (one retrieval + one LLM call
  per claim) — fine at this corpus size, a real constraint to note at larger scale.
- **Pipeline language is pinned to English** to match the corpus and the embedding
  model (`bge-base-en-v1.5` is English-optimized) — an earlier version generated claims
  in French, which silently and severely degraded retrieval quality. All LLM-facing
  prompts now force English output regardless of the input question's language.