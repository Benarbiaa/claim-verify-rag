# claim-verify-rag
### RAG Agentique avec Vérification de Véracité

An agentic RAG system that **does not trust its own answer**. It drafts an answer from a corpus,
splits it into atomic factual claims, re-checks **each claim independently against every
source**, and returns a verdict per claim (**supported**, **contradicted** or **unverifiable**)
with a justification.

Most student RAG demos trust the retrieved chunks blindly. This one treats its own answer as a
set of falsifiable claims, and it can catch cases where two sources in the corpus disagree.

> Built as a technical project for a PFE (final-year internship) application, targeting AI
> engineering roles (agentic systems, RAG, data engineering).

## How it works

```
question ─► per-document retrieval ─► grounded draft ─► atomic claims ─► per-claim verify loop ─► verdicts
             (every source gets        (LLM, cited)      (LLM, JSON)      (LangGraph: re-retrieve
              top-k slots)                                                  + judge, ignoring the
                                                                            draft's citation)
```

**Stack:** PostgreSQL + pgvector · `BAAI/bge-base-en-v1.5` (local embeddings) · LangGraph ·
any OpenAI-compatible LLM, configured **per role**:

| Role | Default model (Groq) | Why |
|---|---|---|
| Draft answer | `openai/gpt-oss-120b` | Fluent, cited prose |
| Claim decomposition | `openai/gpt-oss-120b` | Text transformation |
| **Verification** | `llama-3.3-70b-versatile` | A **different model family** from the drafter, so the judge doesn't grade its own work |

Each role can be moved to another provider or a local model (Ollama, vLLM) from `.env`. See
[`.env.example`](.env.example).

Design rationale: [`docs/architecture.md`](docs/architecture.md).

## Corpus: a real disagreement, not a synthetic one

The corpus covers an open question in RAG research: does sophisticated chunking beat simple
fixed-size chunking?

| File | Source | Role |
|---|---|---|
| `vectara-semantic-chunking-naacl2025.pdf` | Vectara, NAACL 2025 Findings | Sophisticated chunking rarely pays off |
| `lumberchunker-emnlp2024.pdf` | EMNLP 2024 Findings | LLM-based chunking beats every baseline |
| `lewis-rag-neurips2020.pdf` | Lewis et al., NeurIPS 2020 | Original RAG paper: clean baseline claims |
| `anthropic-contextual-retrieval.md` | Anthropic blog, 2024 | Complementary technique: must *not* be flagged as a contradiction |

Full titles: [`data/corpus/SOURCES.md`](data/corpus/SOURCES.md).

## Repository layout

```
├── src/claimverify/            # the package
│   ├── contracts.py            #   data objects passed between stages
│   ├── config.py, llm.py       #   .env loading, per-role LLM config
│   ├── components/             #   shared by both pipelines
│   │   ├── embedding.py        #     bge model: embeds chunks, questions and claims
│   │   └── store.py            #     pgvector: table setup, writing, searching
│   ├── indexing/               #   pipeline 1: files → database
│   │   ├── loading.py          #     PDF / Markdown → Document
│   │   ├── chunking.py         #     Document → Chunk
│   │   └── ingest.py           #     A: load → chunk → embed → store
│   └── answering/              #   pipeline 2: question → verdicts
│       ├── retrieval.py        #     passages formatted for prompts
│       ├── drafting.py         #     B: grounded draft answer
│       ├── decomposition.py    #     C: atomic claims
│       ├── verification.py     #     D: LangGraph verification loop
│       ├── pipeline.py         #     B→C→D in one run + timed report
│       └── query_check.py      #     retrieval sanity check (no LLM)
├── data/corpus/            # source documents
├── eval/                   # evaluation sets and protocol (Step F)
├── tests/                  # unit tests (no DB / GPU / API key needed)
├── docs/                   # architecture, roadmap
├── docker-compose.yml      # Postgres 16 + pgvector
├── Makefile                # common commands
└── pyproject.toml
```

## Quickstart

```bash
# 1. install (editable)
pip install -e ".[dev]"            # or: pip install -r requirements.txt && pip install -e .

# 2. database: Postgres + pgvector
make db-up                         # or use your own Postgres with: CREATE EXTENSION vector;

# 3. API key
cp .env.example .env               # then set GROQ_API_KEY (the only required key);
                                   # DB_URL already matches docker-compose.yml

# 4. ingest the corpus
make ingest

# 5. ask a question: draft → claims → verdicts, report saved in reports/
make run Q="Does semantic chunking improve retrieval performance compared to fixed-size chunking?"
```

Other commands (`make help`):

| Command | What it does |
|---|---|
| `make check Q="..."` | Show the retrieved chunks, no LLM calls |
| `make batch QUESTIONS=eval/smoke_questions.txt` | Run several questions, aggregate report |
| `make db-reset` | Drop the `chunks` table (before re-ingesting) |
| `make test` | Unit tests |

Each stage also runs on its own:

```bash
python -m claimverify.answering.drafting      --query "..." --save_to draft.json
python -m claimverify.answering.decomposition --draft_file draft.json --save_json claims.json
python -m claimverify.answering.verification --claims_file claims.json --save_json verdicts.json
python -m claimverify.answering.verification --debug_claim "..."   # inspect one claim's evidence
```

Every script reads the database URL from `DB_URL` in `.env`. Pass `--db_url` to point one run at
another database.

## Status

- [x] Corpus selected and ingested
- [x] Per-document retrieval (guaranteed coverage of every source)
- [x] Grounded, cited draft answers
- [x] Atomic claim decomposition
- [x] Per-claim independent verification (LangGraph)
- [x] End-to-end runner with timings and saved reports
- [x] Per-role LLM config: the verifier uses a different model than the drafter
- [ ] Retrieval correctness fixes (index, token-aware chunking)
- [ ] **Step F:** formal evaluation (claim-level gold set + end-to-end questions)
- [ ] **Step G:** minimal UI
- [ ] Technical report

Details and priorities: [`docs/roadmap.md`](docs/roadmap.md).

## Known limitations

- Decomposition can produce near-duplicate claims (for example when an intro and a conclusion
  say the same thing). They are not deduplicated yet.
- `top_k_per_doc=2` keeps requests under Groq's free-tier tokens-per-minute cap.
- Verification cost is linear in the number of claims: one retrieval and one LLM call each.
- The pipeline is pinned to English to match the corpus and the embedder. French claims
  silently and severely degraded retrieval.
