# Roadmap and next steps

Status as of 2026-09-24: steps A–E work end to end (ingest → draft → decompose → verify →
report). Remaining work, in priority order. **P0 items change retrieval or verdicts, so fix
them before building the eval baseline**, or the numbers you report will be skewed.

## Done

- [x] **Per-role LLM config** (`src/claimverify/llm.py`): draft and decompose on
  `gpt-oss-120b`, verify on `llama-3.3-70b-versatile`. Every role can be moved to another
  OpenAI-compatible provider or a local model from `.env`. The `verifier_model` is recorded in
  every verdict and in the report header.

## P0: correctness (fix one at a time, re-run `make check` after each)

- [ ] **P0-1. IVFFlat index built on an empty table.** `setup_db()` creates the
  `ivfflat (lists = 10)` index *before* inserting rows, so the cluster centroids are
  meaningless. pgvector also searches only one list by default (`ivfflat.probes = 1`), and the
  `WHERE filename = …` filter in `search_per_document` is applied *after* the approximate
  search. Result: a per-document search can return fewer than k chunks, or the wrong ones. This
  is a likely cause of the false "unverifiable" verdicts.
  *Fix:* at this corpus size (a few hundred chunks), drop the index and use exact search, or
  switch to HNSW and set `hnsw.ef_search`.
  *Check:* for a few claims, compare `--debug_claim` output with and without the index.

- [ ] **P0-2. Chunks are measured in words, but the embedder limit is 512 tokens.** 512
  whitespace words is likely more than 512 WordPiece tokens for academic PDF text, and
  `bge-base-en-v1.5` silently truncates at 512. So the tail of every chunk may never be
  embedded, while the LLM still sees it in the evidence.
  *Check:* count `model.tokenizer(chunk)["input_ids"]` lengths over the corpus.
  *Fix:* chunk by tokenizer tokens (for example 400 tokens with 15% overlap).

- [ ] **P0-3. Split "contradicted" into two verdicts.** Today it covers both "the claim is
  false" and "the sources disagree with each other". Add `contested` (the sources conflict;
  name them) and keep `contradicted` (the evidence says the claim is wrong). This is the core
  story of the project, so the verdict set should express it directly.

- [ ] **P0-4. Re-ingest after the corpus rename.** `make db-reset ingest`. See
  `data/corpus/SOURCES.md`.

- [ ] **P0-5. Housekeeping.** `requirements.txt` pins unused packages (anthropic, google-*,
  Spark, …); regenerate it from the direct dependencies in `pyproject.toml`. `TOP_K_PER_DOC`
  is duplicated across 3 modules (`components/store.py`, `answering/drafting.py`,
  `answering/verification.py`); move it into one `config.py`. (The unused `tqdm` import went
  away when `ingest.py` was split.)

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

- [ ] Retry with backoff on Groq 429 / tokens-per-minute errors (`tenacity` is already
  installed).
- [ ] Validate LLM JSON with Pydantic models. Today a malformed verdict silently becomes
  `unverifiable`, which inflates that class; count parse failures separately.
- [ ] Replace `print` with `logging`; log token usage per call.
- [ ] GitHub Actions: `ruff` + `pytest` (the tests need no DB, GPU or API key).
- [ ] PDF cleanup at ingest: strip the reference sections and fix hyphenated line breaks.
  Reference lists create noisy chunks that match many claims.

## P3: Step G interface and deliverables

- [ ] Minimal UI (Streamlit or Gradio): question → draft with claims highlighted by verdict →
  click a claim to see the evidence passages and the sources it was checked against.
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
