# Roadmap and next steps

Status as of 2026-09-24: steps A–E work end to end (ingest → draft → decompose → verify →
report). Remaining work, in priority order. **P0 items change retrieval or verdicts, so fix
them before building the eval baseline**, or the numbers you report will be skewed.

## Done

- [x] **Modular pipeline**: data contracts (`contracts.py`), one interface per stage, and
  `config.yaml` + `factory.py` to choose each implementation. Secrets stay in `.env`.
- [x] **Per-role LLM config** (now in `config.yaml`): draft and decompose on
  `gpt-oss-120b`, verify on `qwen/qwen3.8-27b` (Groq retired `llama-3.3-70b-versatile`). Every role can be moved to another
  OpenAI-compatible provider or a local model from `config.yaml`. The `verifier_model` is recorded in
  every verdict and in the report header.

## P0: correctness (fix one at a time, re-run `make check` after each)

- [x] **P0-1. IVFFlat index built on an empty table.** `setup_db()` created the
  `ivfflat (lists = 10)` index *before* inserting rows, so the cluster centroids were
  meaningless. pgvector searches only one list by default (`ivfflat.probes = 1`), and the
  `WHERE filename = …` filter in `search_per_document` is applied *after* the approximate
  search.
  *Measured (no LLM call):* with 57 rows, Postgres never used the index: it read every row
  (exact search), so the recorded runs were not affected (15 queries, 91/91 passages identical to
  an exact search). Forcing the index, the chunking question lost LumberChunker and Anthropic
  entirely (5 passages instead of 9). The planner would have switched to the index on its own as
  the table grew.
  *Fix:* `setup_db()` drops the index; search is exact. Checked: same 15 queries, same passages,
  order and scores as before, and no index to use even with `enable_seqscan = off`.
  *Consequence:* this was not the cause of the false "unverifiable" verdicts. The one in the
  recorded run (c11) is a claim about the draft itself, a decomposition issue (Q4 in design.md).

- [ ] **P0-2. Chunks are measured in words, but the embedder limit is 512 tokens.** 512
  whitespace words is likely more than 512 WordPiece tokens for academic PDF text, and
  `bge-base-en-v1.5` silently truncates at 512. So the tail of every chunk may never be
  embedded, while the LLM still sees it in the evidence.
  *Check:* count `model.tokenizer(chunk)["input_ids"]` lengths over the corpus.
  *Fix:* chunk by tokenizer tokens (for example 400 tokens with 15% overlap).

- [x] **P0-3. Split "contradicted" into two verdicts.** Added `contested` (the sources conflict
  with each other) next to `contradicted` (the evidence says the claim is wrong), with rules
  tying each verdict to its sources. Unusable judge answers are now `error` instead of a fake
  `unverifiable`, and each verdict records the passages it was judged on.

- [x] **P0-4. Re-ingest after the corpus rename.** Ingest used to upsert rows by `chunk_id`
  and never delete, so a removed or renamed file kept its rows. `replace_chunks` now replaces
  the whole table in one transaction (and refuses an empty chunk list). `SOURCES.md` moved to
  `data/info/`: it had been ingested as a fifth source and took one slot in every search.
  Re-ingested: 56 chunks from 4 documents; apart from `SOURCES.md`, the 15 baseline queries
  return the same passages.

- [ ] **P0-5. Housekeeping.** `requirements.txt` pins unused packages (anthropic, google-*,
  Spark, …); regenerate it from the direct dependencies in `pyproject.toml`. (Done along the
  way: `top_k_per_doc` now comes from `config.yaml`, and the unused `tqdm` import went away
  when `ingest.py` was split.)

## P1: Step F, evaluation (the part recruiters will look at)

- [ ] Build `eval/claims_gold.jsonl` (about 30 claims across 5 categories, see `eval/README.md`).
- [ ] Write `scripts/run_eval.py`: verifier-only scoring, confusion matrix, per-class P/R,
  false-contradiction rate.
- [ ] Build `eval/questions.jsonl` (20–30 questions) for end-to-end runs.
- [ ] Ablations, one table each: global vs. per-document retrieval · `top_k_per_doc` 2/3/4 ·
  2 LLMs. Report accuracy, latency and tokens.
- [ ] Deduplicate near-identical claims after decomposition (embedding cosine > ~0.92), and
  measure how much verification time it saves.
- [ ] **Verifier experiment: plain loop vs. agentic loop.** Today the LangGraph verifier is a
  straight loop (retrieve → judge per claim), so LangGraph adds complexity without deciding
  anything. Compare two `Verifier` implementations:
  `LoopVerifier` (a plain `for` loop, the simple default) and `AgenticVerifier` (LangGraph with
  a real decision: when the verdict is `unverifiable`, reformulate the query, retrieve again and
  re-judge, at most 2 tries). Measure wrong-`unverifiable` rate, accuracy and extra API calls.
  LangGraph checkpointing could also let long evaluation runs resume after a rate-limit stop.

## P2: robustness and engineering

- [x] Retries in `LLM.chat` with limits per provider in `config.yaml` (`max_retries`,
  `max_wait_seconds`, `timeout_seconds`): rate limits and server errors wait and retry, a
  request too large for the per-minute limit or a daily limit stops the run with a clear
  message.
- [x] Validate LLM JSON with Pydantic models: claims through the `Claim` contract, verdicts
  through `Verdict` (with source-consistency rules). Unusable verdicts are counted as `error`.
- [x] Token usage per stage: each stage event records calls, tokens, retries and waiting time,
  and the report totals them per role. (Replacing the remaining `print`s with `logging` is
  still open.)
- [ ] GitHub Actions: `ruff` + `pytest` (the tests need no DB, GPU or API key).
- [x] PDF cleanup at ingest: a minimal `Cleaner` stage (page numbers, NFKC, words split at
  line ends), with a no-content-lost guarantee checked on every document. Reference sections
  are kept on purpose: removing them is a judgment about content, and the corpus may grow.
- [ ] Measure whether reference-list chunks are retrieved as evidence; only then look for a
  general fix. Also: 105 split words keep a hyphen because their paper never uses the joined
  word (`gen-erating`); evidence from the whole corpus would repair most of them.

- [ ] **Store runs in PostgreSQL** once the UI or the experiments need to query many runs
  ("all contested verdicts from judge X", "verification time per model"): `runs` and `events`
  tables with the event content in JSONB. It is one more event sink next to the file recorder
  (`reporting.py`), so the orchestrators don't change.

## P3: Step G interface and deliverables

- [x] Web UI (FastAPI + React, `ui/`): replay of recorded runs, live runs streamed as events,
  the claims × sources plate with each claim's evidence, one time axis with rate-limit waits,
  indexing view. See the README's "Web UI" section and `DESIGN.md`.
- [ ] README: add a demo GIF, an example report excerpt and the eval results table.
- [ ] Technical report (rapport): problem, corpus rationale, architecture, eval method,
  results, ablations, limitations.
- [ ] Add the missing `docs/cahier-des-charges.md` (the README used to link to it).
- [ ] Choose a license.

## Suggested order for the next sessions

1. P0-1 → re-run the smoke questions and compare the "unverifiable" counts.
2. P0-2 → re-ingest.
3. P0-3 (verdict schema), because the gold set's labels depend on it.
4. Gold set + eval runner → first baseline numbers.
5. Ablations, then the UI, then the report.
