# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Decided by the user: FastAPI + uvicorn backend in `src/claimverify/api/` (Server-Sent Events for
live runs); React + TypeScript + Vite frontend in `ui/`, Tailwind CSS, shadcn/ui (Radix) for
accessible primitives, Motion for animation, TanStack Query for data, EventSource for live events.

## Users

- **Recruiters and a jury**, shown the project on a projector in a lit room or on a laptop across
  a table. They must understand what the system does at first sight, without knowing RAG.
- **Technical evaluators** (engineers, jury members with ML background) who want to inspect the
  intermediate results: retrieved passages, scores, the evidence a judge read, tokens and retries.
- **The author**, who uses the same views to debug runs and compare experiments.

## Product Purpose

claim-verify-rag is a RAG pipeline: it drafts an answer from a corpus, splits the answer
into atomic claims, and re-verifies each claim against every source with a judge from a different
model family. The UI makes that PROCESS visible: each stage, its intermediate results, and the
final verdicts. Success: a visitor can say, after one viewing, "it wrote an answer, then checked
every sentence against all the papers, and showed where they agree and disagree."

## Positioning

Most RAG demos show an answer with citations. This one distrusts its own answer: every claim is
re-checked against the whole corpus, not just the cited source, and the system can report that
the sources disagree with each other (`contested`), which the corpus demonstrates with a real
scientific disagreement (Vectara NAACL 2025 vs LumberChunker EMNLP 2024 on chunking).

## Operating Context

- Data is read from run folders `runs/<run_id>/` (`events.jsonl`, plus `report.json`/`report.md`
  for answering runs). Replay of a saved run is the primary demo mode and makes no API call.
- Live mode runs the real pipeline on Groq's free tier: ~50K tokens per question, per-minute
  limits cause long rate-limit waits (in the sample run, 294 of 305 s of verification were waits),
  and daily limits or oversized requests stop a run.
- Pipeline stages: Retrieve (top-k per document) → Draft → Decompose → Verify (per claim) → Done.
  Indexing: documents → cleaned → chunks → embeddings → stored.

## Capabilities and Constraints

- Verdict labels: `supported`, `contradicted`, `contested` (sources disagree with each other),
  `unverifiable` (no source addresses the claim), `error` (the judge's answer was unusable; not a
  conclusion about the sources, retryable).
- No pipeline logic in the UI; the pipeline core is changed only when the UI strictly needs it,
  after asking the author.
- Tests run without network, API key or GPU (saved runs and fakes).
- UI language: English.

## Evidence on Hand

- Sample answering run `runs/20260926_155834_answering/` (1 question, 11 claims: 10 supported,
  1 unverifiable; no contested verdict yet) and indexing run `runs/20260926_142114_indexing/`
  (5 documents, 57 chunks).
- Corpus in `data/corpus/` (3 papers, 1 blog post, SOURCES.md).
- A `contested` example does not exist in real data yet; a test fixture may include one, labeled
  as a fixture.

## Product Principles

1. Show the process, not just the result: every stage's output is inspectable.
2. Honesty over polish: waits, retries, errors and disagreement are shown, never hidden.
3. Understandable in five seconds, precise under inspection.
4. Never spend API quota without the user's explicit action and a visible cost estimate.

## Accessibility & Inclusion

- Verdicts never rely on color alone: icon + label + color, colorblind-safe palette.
- Light theme for projectors in lit rooms and dark theme for laptops, with a toggle; text sizes
  readable from the back of a room.
- Keyboard-operable replay controls and claim navigation; respects reduced motion.
