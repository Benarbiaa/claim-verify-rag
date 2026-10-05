# claim-verify-rag
### RAG avec Vérification de Véracité

[![CI](https://github.com/Benarbiaa/claim-verify-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/Benarbiaa/claim-verify-rag/actions/workflows/ci.yml)

A RAG system that **does not trust its own answer**. It drafts an answer from a corpus,
splits it into atomic factual claims, re-checks **each claim independently against every
source**, and returns a verdict per claim with a justification and the passages it was checked
against: **supported**, **contradicted**, **contested** (the sources disagree with each other) or
**unverifiable**. A claim the judge failed to assess is marked **error**, counted separately.

Most student RAG demos trust the retrieved chunks blindly. This one treats its own answer as a
set of falsifiable claims, and it can catch cases where two sources in the corpus disagree.

> Built as a technical project for a PFE (final-year internship) application, targeting AI
> engineering roles (agentic systems, RAG, data engineering).

## Results

Every change below was measured before being kept, against a rule fixed in advance. The sets are
small and say so: read the counts, not percentages.

**Does the judge receive the proof?** 44 claim → quote pairs (`eval/retrieval_set.jsonl` plus
the gold set's quotes): is the passage holding the proof among the 2 the judge reads from its
document? No LLM call ([`eval/results/retrieval.md`](eval/results/retrieval.md)).

| Retrieval | Proof received by the judge |
|---|---|
| By meaning only (embeddings) | 23/44 |
| Hybrid: meaning + exact words (BM25), rankings fused | 31/44 |
| **Hybrid + cross-encoder reranker (current)** | **37/44** |

**Is the verdict right?** The full verifier on a hand-checked gold set of 10 claims, 2 per case,
each label proven by an exact quote ([`eval/results/judge.md`](eval/results/judge.md)):

| Case | Correct |
|---|---|
| Finding from one paper (supported) | 2/2 |
| One detail changed: a number, a source (contradicted) | 2/2 |
| Real disagreement between two papers (contested) | 1/2 |
| Related technique that must not be read as a contradiction (supported) | 2/2 |
| Fact the corpus never discusses (unverifiable) | 2/2 |

**9/10**, no false contradiction. The miss: Vectara's introduction says chunking has "a crucial
effect", its conclusion that the effect is "overshadowed" by the embedding model. The search
brought the introduction, so the judge answered `supported` instead of `contested`.

## How it works

```
question ─► per-document retrieval ─► grounded draft ─► atomic claims ─► per-claim verify loop ─► verdicts
             (meaning + BM25,          (LLM, cited)      (LLM, JSON)      (re-retrieve + judge,
              reranked; every source                                       ignoring the draft's
              gets top-k slots)                                            citation)
```

The verification runs as a LangGraph loop over the claims: the steps are fixed, the LLMs write
and judge. A truly agentic step, where the judge decides to search again for counter-evidence
when a conflict may be hidden deeper in a paper (the miss above), is the next planned feature.

**Stack:** PostgreSQL + pgvector · `BAAI/bge-base-en-v1.5` (local embeddings) + BM25 (hybrid search) + `bge-reranker-base` · LangGraph ·
any OpenAI-compatible LLM. Every stage is chosen and tuned in [`config.yaml`](config.yaml):

| Role | Default model (Groq) | Why |
|---|---|---|
| Draft answer | `openai/gpt-oss-120b` | Fluent, cited prose |
| Claim decomposition | `openai/gpt-oss-120b` | Text transformation |
| **Verification** | `qwen/qwen3.8-27b` | A **different model family** from the drafter, so the judge doesn't grade its own work |

Each stage sits behind an interface, and `config.yaml` picks its implementation and settings:
moving the judge to another provider (Gemini, a local model with Ollama or vLLM…) is a change
to that file, not to the code. `.env` only holds secrets (API keys, `DB_URL`), see
[`.env.example`](.env.example). For an experiment, copy `config.yaml` and pass
`--config my_experiment.yaml` to any command.

Design, diagrams and the reason for each choice: [`docs/design.md`](docs/design.md).

## Corpus: a real disagreement, not a synthetic one

The corpus covers an open question in RAG research: does sophisticated chunking beat simple
fixed-size chunking?

| File | Source | Role |
|---|---|---|
| `vectara-semantic-chunking-naacl2025.pdf` | Vectara, NAACL 2025 Findings | Sophisticated chunking rarely pays off |
| `lumberchunker-emnlp2024.pdf` | EMNLP 2024 Findings | LLM-based chunking beats every baseline |
| `lewis-rag-neurips2020.pdf` | Lewis et al., NeurIPS 2020 | Original RAG paper: clean baseline claims |
| `anthropic-contextual-retrieval.md` | Anthropic blog, 2024 | Complementary technique: must *not* be flagged as a contradiction |

Full titles: [`data/info/SOURCES.md`](data/info/SOURCES.md).

## Repository layout

```
├── src/claimverify/            # the package
│   ├── contracts.py            #   data objects passed between stages
│   ├── settings.py, factory.py #   config.yaml validation, builds the stages from it
│   ├── config.py, llm.py       #   .env loading (secrets), LLM client
│   ├── evaluation.py           #   gold set and retrieval set: formats, checks, commands
│   ├── retrieval_eval.py       #   does the search bring back each proof? (no LLM)
│   ├── judge_eval.py           #   the judge's verdicts against the gold set
│   ├── components/             #   shared by both pipelines
│   │   ├── embedding.py        #     bge model: embeds chunks, questions and claims
│   │   ├── lexical.py          #     BM25 and rank fusion (hybrid search)
│   │   ├── reranking.py        #     cross-encoder reranker
│   │   └── store.py            #     pgvector: table setup, writing, searching
│   ├── api/                    #   the web UI's server: run folders, live runs (SSE)
│   ├── indexing/               #   pipeline 1: files → database
│   │   ├── loading.py          #     PDF / Markdown → Document
│   │   ├── cleaning.py         #     repairs PDF extraction (no content removed)
│   │   ├── chunking.py         #     Document → Chunk (in the embedder's tokens)
│   │   └── ingest.py           #     A: load → clean → chunk → embed → store
│   └── answering/              #   pipeline 2: question → verdicts
│       ├── retrieval.py        #     hybrid search + reranker, passages for prompts
│       ├── drafting.py         #     B: grounded draft answer
│       ├── decomposition.py    #     C: atomic claims
│       ├── verification.py     #     D: LangGraph verification loop
│       ├── pipeline.py         #     B→C→D in one run + timed report
│       └── query_check.py      #     retrieval sanity check (no LLM)
├── ui/                     # web UI (React + TypeScript + Vite)
├── data/corpus/            # source documents (data/info/: their full titles)
├── eval/                   # gold set, retrieval set, protocol, results
├── scripts/                # requirements.txt generator
├── tests/                  # unit tests (no DB / GPU / API key needed)
├── docs/                   # architecture, roadmap
├── docker-compose.yml      # Postgres 16 + pgvector
├── Makefile                # common commands
└── pyproject.toml
```

## Quickstart

```bash
# 1. install: creates .venv and installs the package (editable) with its dev and UI extras
make install                       # Linux, exact versions: pip install -r requirements.txt && pip install -e .

# 2. database: Postgres + pgvector
make db-up                         # or use your own Postgres with: CREATE EXTENSION vector;

# 3. API key (models and settings are in config.yaml)
cp .env.example .env               # then set GROQ_API_KEY (the only required key);
                                   # DB_URL already matches docker-compose.yml

# 4. ingest the corpus
make ingest

# 5. ask a question: draft → claims → verdicts, saved in runs/<run_id>/
make run Q="Does semantic chunking improve retrieval performance compared to fixed-size chunking?"
```

Other commands (`make help`):

| Command | What it does |
|---|---|
| `make check Q="..."` | Show the passages the drafter retrieves (settings from `config.yaml`), no LLM calls |
| `make batch QUESTIONS=eval/smoke_questions.txt` | Run several questions, aggregate report (calls the LLM APIs) |
| `make ui` | Build and serve the web UI, replay only (`make ui LIVE=1` allows live runs) |
| `make test` · `make ui-test` | Lint + Python tests · UI type-check + tests |
| `make db-down` | Stop the database container (data kept) |
| `make check-gold` | Check the gold set: labels, sources, every quote found in the corpus |
| `make eval-retrieval` | Does the search bring back each proof? Methods and chunk sizes compared, no LLM calls |
| `make eval-judge` | The verifier on the 10 gold claims (calls the LLM APIs, about 40K tokens) |
| `make requirements` | Regenerate `requirements.txt` from `pyproject.toml` |

Python comes from `.venv`; use another one with `PY=...` (e.g. `make test PY=python3`).

Each stage also runs on its own:

```bash
python -m claimverify.answering.drafting      --query "..." --save_to draft.json
python -m claimverify.answering.decomposition --draft_file draft.json --save_json claims.json
python -m claimverify.answering.verification --claims_file claims.json --save_json verdicts.json
python -m claimverify.answering.verification --debug_claim "..."   # inspect one claim's evidence
```

Every script reads the database URL from `DB_URL` in `.env` and the pipeline settings from
`config.yaml`. Pass `--db_url` or `--config` to point one run elsewhere.

Each run of `indexing.ingest` or `answering.pipeline` prints one line per stage and gets its own
folder, `runs/<run_id>/`: `events.jsonl` holds every stage's full output (retrieved passages,
draft, claims, each verdict with the passages it was judged on), and answering runs add
`report.json` and `report.md`. `claimverify.reporting.load_events` reads a run back.

## Web UI

The UI shows the pipeline at work: each stage, what it produced, and the verdicts. Its core is
the plate, a grid of claims against source documents that shows which sources support,
contradict, or say nothing about each claim. Recorded runs replay step by step (play, pause,
speed) **without any API call**.

```bash
make ui                                    # http://127.0.0.1:8000, opens on the latest run (replay only)
make ui LIVE=1                             # same, and "Ask a question" can start real runs
```

By hand: `cd ui && npm install && npm run build`, then `python -m claimverify.api.server`
(live runs allowed unless `--no-live`).

| Option | Effect |
|---|---|
| `--no-live` | Replay only: the UI cannot start a run, so no API quota can be spent (safe for demos) |
| `--fixtures` | Also lists `tests/fixtures/runs/`: a run with all five verdicts, including `contested` (labelled as a fixture in the UI) |

"Ask a question" runs the real pipeline (about 50K tokens per question; the cost is shown before
starting). The page follows each stage as it finishes, shows a countdown during rate-limit
waits, and explains run-stopping errors (daily limit, request too large). The run is recorded in
`runs/` like any other.

To work on the UI: `python -m claimverify.api.server` in one terminal, `cd ui && npm run dev` in
another (Vite forwards `/api` to the server). `cd ui && npm test` runs the UI's unit tests. The
visual design is described in [`DESIGN.md`](DESIGN.md).

## Status

- [x] Corpus selected and ingested
- [x] Per-document retrieval (guaranteed coverage of every source)
- [x] Grounded, cited draft answers
- [x] Atomic claim decomposition
- [x] Per-claim independent verification (LangGraph)
- [x] End-to-end runner with timings and saved reports
- [x] Modular pipeline: data contracts, one interface per stage, stages built from `config.yaml`
- [x] The verifier uses a different model family than the drafter
- [x] Retrieval correctness fixes (exact search, ingest replaces the table, PDF cleanup, token-aware chunking)
- [x] Retrieval measured and improved: hybrid search (meaning + BM25) and a cross-encoder reranker
- [x] **Step F, claim level:** gold set, retrieval and judge evaluations (results above)
- [ ] **Step F, end to end:** a question-level set (draft → claims → verdicts)
- [ ] Agentic verification: search again for counter-evidence when a conflict may be hidden
- [x] **Step G:** web UI (replay, live runs, indexing view)
- [ ] Technical report

Details and priorities: [`docs/roadmap.md`](docs/roadmap.md).

## Known limitations

- Decomposition can produce near-duplicate claims (for example when an intro and a conclusion
  say the same thing). They are not deduplicated yet.
- The evaluation is small: 10 gold claims and 44 retrieval quotes, written while reading the
  papers. It detects large problems and compares settings; it is not a statistical measure.
- A conflict can stay hidden when a paper says one thing in its introduction and the opposite in
  its conclusion: the search tends to bring the introduction (see Results).
- `top_k_per_doc=2` keeps requests under Groq's free-tier tokens-per-minute cap; `3` was measured
  and brings one more proof for 45 % more tokens per verdict.
- The reranker adds about 2.6 s per claim on a GPU.
- Verification cost is linear in the number of claims: one retrieval and one LLM call each.
- The pipeline is pinned to English to match the corpus and the embedder. French claims
  silently and severely degraded retrieval.
