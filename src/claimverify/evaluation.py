"""
Evaluation — the gold set of claims, the retrieval set, and their checks
========================================================================

The gold set (eval/claims_gold.jsonl) holds claims whose right verdict is
known IN ADVANCE, independently of the system, and PROVEN by an exact quote
from the source. The verifier is evaluated by comparing its verdicts with
these answers. The labels are reviewed by a human: a mistake here would
become "the truth" of every measurement.

This module defines the format (GoldClaim) and refuses an inconsistent gold
set before any measurement: an impossible label, sources incompatible with
the label, a file missing from the corpus, or a quote not found in the
stored text.

The retrieval set (eval/retrieval_set.jsonl) is simpler and larger: claim ->
quote pairs, with no verdict. It only measures whether the search brings
back the proof (retrieval_eval.py): no label to review, no LLM call, so more
items are affordable.

The question set (eval/questions.jsonl) is for the end-to-end evaluation:
questions whose claims the pipeline writes itself, so what is known in
advance is which documents hold the answer, and for some questions a
statement the pipeline must find contested or false (GoldQuestion).

Usage:
    python -m claimverify.evaluation check-gold         (both sets; no LLM call, no database)
    python -m claimverify.evaluation retrieval          (no LLM call; GPU for the embedding)
    python -m claimverify.evaluation retrieval-details  (no LLM call: the chunks the judge would read)
    python -m claimverify.evaluation chunks --size 256  (no LLM call: the corpus cut at that size)
    python -m claimverify.evaluation judge              (LLM CALLS: the judge on the gold set)
    python -m claimverify.evaluation e2e                (LLM CALLS: the pipeline on the question set)
    python -m claimverify.evaluation score-e2e          (scores the recorded runs again; no LLM call)
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Literal, TypeVar, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from claimverify.contracts import Document, JudgeLabel
from claimverify.indexing.cleaning import content_signature

M = TypeVar("M", bound=BaseModel)

DEFAULT_GOLD_PATH = Path("eval/claims_gold.jsonl")
DEFAULT_RETRIEVAL_SET_PATH = Path("eval/retrieval_set.jsonl")
DEFAULT_QUESTIONS_PATH = Path("eval/questions.jsonl")
CORPUS_DIR = Path("data/corpus")

Category = Literal["single_source", "perturbed_fact", "cross_source_conflict",
                   "complementary", "out_of_corpus"]
CATEGORIES: tuple[str, ...] = get_args(Category)


class GoldEvidence(BaseModel):
    """An exact quote from a source, and what it does to the claim."""
    model_config = ConfigDict(extra="forbid")
    filename: str
    stance: Literal["supports", "contradicts"]
    quote: str = Field(min_length=20)  # a sentence, not an isolated word


class GoldClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    category: Category
    claim: str = Field(min_length=10)
    expected: JudgeLabel  # never "error": that is a failure of the judge, not a conclusion
    evidence: list[GoldEvidence] = []
    note: str = ""        # why this label, in one line

    @model_validator(mode="after")
    def _evidence_matches_the_label(self) -> "GoldClaim":
        # Stricter than the Verdict contract: the gold set is the reference.
        pro = {e.filename for e in self.evidence if e.stance == "supports"}
        con = {e.filename for e in self.evidence if e.stance == "contradicts"}
        rules = {
            "supported": (pro and not con, "at least one quote for, none against"),
            "contradicted": (con and not pro, "at least one quote against, none for"),
            # "contested": the SOURCES contradict each other, so two different documents
            "contested": (pro and con and len(pro | con) >= 2, "quotes on both sides, from different documents"),
            "unverifiable": (not self.evidence, "no quote (the corpus does not discuss it)"),
        }
        ok, rule = rules[self.expected]
        if not ok:
            raise ValueError(f"'{self.expected}' needs {rule}")
        return self


class RetrievalPair(BaseModel):
    """A claim and the quote the search should bring back (no verdict)."""
    model_config = ConfigDict(extra="forbid")
    id: str
    claim: str = Field(min_length=10)
    filename: str
    quote: str = Field(min_length=20)


QuestionCategory = Literal["single_source", "multi_source", "conflict", "out_of_corpus", "false_premise"]
QUESTION_CATEGORIES: tuple[str, ...] = get_args(QuestionCategory)


class GoldQuestion(BaseModel):
    """A question for the end-to-end evaluation. Its claims are written by the
    pipeline, so they cannot be labelled in advance: what is known in advance
    is which documents hold the answer (those with a quote) and, for some
    categories, a `statement` the pipeline must find contested or false.

    A quote's stance refers to the `statement` when there is one, otherwise to
    the expected answer."""
    model_config = ConfigDict(extra="forbid")
    id: str
    category: QuestionCategory
    question: str = Field(min_length=10)
    statement: str | None = None  # conflict: what the sources disagree on; false_premise: the false premise
    evidence: list[GoldEvidence] = []
    note: str = ""

    @property
    def documents(self) -> set[str]:
        """The documents the pipeline must use: those holding a quote."""
        return {e.filename for e in self.evidence}

    @model_validator(mode="after")
    def _evidence_matches_the_category(self) -> "GoldQuestion":
        pro = {e.filename for e in self.evidence if e.stance == "supports"}
        con = {e.filename for e in self.evidence if e.stance == "contradicts"}
        rules = {
            "single_source": (pro and not con and len(pro) == 1, "quotes for the answer, all from one document"),
            "multi_source": (pro and not con and len(pro) >= 2, "quotes for the answer from at least two documents"),
            # as for a contested claim: the SOURCES disagree, so a document on each side
            "conflict": (any(p != c for p in pro for c in con),
                         "quotes for and against the statement, from different documents"),
            "false_premise": (con and not pro, "quotes against the premise, none for it"),
            "out_of_corpus": (not self.evidence, "no quote (the corpus does not discuss it)"),
        }
        ok, rule = rules[self.category]
        if not ok:
            raise ValueError(f"'{self.category}' needs {rule}")
        needs_statement = self.category in ("conflict", "false_premise")
        if needs_statement != (self.statement is not None):
            raise ValueError(f"'{self.category}' {'needs' if needs_statement else 'takes no'} statement")
        return self


def _load_jsonl(path: Path, model: type[M]) -> list[M]:
    """One JSON line per object; blank lines are ignored. An error names the
    faulty line."""
    items = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(model.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as e:
            raise ValueError(f"{path}, line {number}: {e}") from e
    return items


def load_gold(path: Path) -> list[GoldClaim]:
    return _load_jsonl(path, GoldClaim)


def load_retrieval_set(path: Path) -> list[RetrievalPair]:
    return _load_jsonl(path, RetrievalPair)


def load_questions(path: Path) -> list[GoldQuestion]:
    return _load_jsonl(path, GoldQuestion)


def check_gold(claims: list[GoldClaim], documents: dict[str, str]) -> list[str]:
    """The gold set's problems against the corpus (documents: filename ->
    STORED text, i.e. cleaned). An empty list = a usable gold set."""
    return _set_problems(claims, CATEGORIES, "claim", documents)


def check_questions(questions: list[GoldQuestion], documents: dict[str, str]) -> list[str]:
    """Same checks for the question set."""
    return _set_problems(questions, QUESTION_CATEGORIES, "question", documents)


def _set_problems(items: list[GoldClaim] | list[GoldQuestion], categories: tuple[str, ...],
                  kind: str, documents: dict[str, str]) -> list[str]:
    problems = []
    for item_id, n in Counter(i.id for i in items).items():
        if n > 1:
            problems.append(f"duplicate id: {item_id} ({n} times)")
    for category in categories:
        if not any(i.category == category for i in items):
            problems.append(f"no {kind} in the category {category}")

    quotes = [(i.id, e.filename, e.quote) for i in items for e in i.evidence]
    return problems + _quote_problems(quotes, documents)


def check_retrieval_set(pairs: list[RetrievalPair], documents: dict[str, str]) -> list[str]:
    problems = [f"duplicate id: {pair_id} ({n} times)"
                for pair_id, n in Counter(p.id for p in pairs).items() if n > 1]
    return problems + _quote_problems([(p.id, p.filename, p.quote) for p in pairs], documents)


def _quote_problems(quotes: list[tuple[str, str, str]], documents: dict[str, str]) -> list[str]:
    # Compared without spaces, line breaks or hyphens: a quote copied from the
    # PDF or from the stored text is found, an invented or altered one is not.
    signatures = {name: content_signature(text) for name, text in documents.items()}
    problems = []
    for item_id, filename, quote in quotes:
        if filename not in documents:
            problems.append(f"{item_id}: {filename} is not in the corpus")
        elif content_signature(quote) not in signatures[filename]:
            problems.append(f"{item_id}: quote not found in {filename}: \"{quote[:60]}…\"")
    return problems


def corpus_documents(settings) -> list[Document]:
    """The documents as stored: loaded then cleaned by config.yaml's stages
    (no embedder, no database)."""
    from claimverify.factory import build_cleaner, build_loader  # local import: factory is heavy

    documents = build_loader(settings).load(CORPUS_DIR)
    return [c.document for c in build_cleaner(settings).clean(documents)]


def corpus_texts(settings) -> dict[str, str]:
    return {d.filename: d.text for d in corpus_documents(settings)}


def retrieval_targets(claims: list[GoldClaim], pairs: list[RetrievalPair]):
    """Each quote of the gold set and of the retrieval set becomes a target
    (g02.1, g02.2 when a claim has several)."""
    from claimverify.retrieval_eval import Target

    targets = []
    for c in claims:
        for i, e in enumerate(c.evidence, start=1):
            suffix = f".{i}" if len(c.evidence) > 1 else ""
            targets.append(Target(f"{c.id}{suffix}", c.claim, e.filename, e.quote))
    return targets + [Target(p.id, p.claim, p.filename, p.quote) for p in pairs]


# Rule fixed BEFORE measuring, so the threshold is not chosen after seeing the numbers:
# a method replaces the current search if it gains at least MIN_NET_GAIN quotes net at
# the judge's k, with no document losing proofs.
MIN_NET_GAIN = 4


def retrieval_report(results: dict[tuple[int, str], list], current_size: int, judge_k: int) -> str:
    """The report in Markdown. `results`: (chunk size, method) -> results.
    The reference is today's search: config.yaml's chunk size, dense method."""
    from claimverify.retrieval_eval import K_VALUES, paired_changes, recall_at, wilson_interval

    def pct(hits: int, n: int) -> str:
        low, high = wilson_interval(hits, n)
        return f"{hits}/{n} ({100 * hits / n:.0f} %, {100 * low:.0f}–{100 * high:.0f})"

    reference = (current_size, "dense")
    base = results[reference]
    n = len(base)
    files = sorted({f.target.filename for f in base})
    lines = ["# Retrieval: does the search bring back the proof?", "",
             f"{n} quotes (gold set + retrieval set). A quote counts as found at k when the chunk",
             "containing it is among the k best chunks of its document (the search is per document).",
             "In brackets: the 95 % Wilson interval, the honest range for so few items.",
             "This is a lower bound: another chunk may state the same fact in other words (an",
             "abstract repeating a result), which is enough for the judge but not detected here.", "",
             f"`config.yaml`: chunks of {current_size} tokens, the judge gets k = {judge_k} per document.",
             "Methods: `dense` = by meaning (today's search), `bm25` = by exact words,",
             "`hybrid` = both rankings merged by reciprocal rank fusion,",
             "`rerank` = hybrid, then its 10 best chunks per document re-sorted by a cross-encoder",
             "(`BAAI/bge-reranker-base`) that reads the claim and each chunk together.", ""]

    lines += ["## Recall by k", "",
              "| Chunk size | Method | " + " | ".join(f"k = {k}" for k in K_VALUES) + " |",
              "|---|---|" + "---|" * len(K_VALUES)]
    for (size, method), found in sorted(results.items()):
        mark = " (today)" if (size, method) == reference else ""
        lines.append(f"| {size} | {method}{mark} | " + " | ".join(pct(recall_at(found, k), n) for k in K_VALUES) + " |")

    lines += ["", f"## Against today's search, quote by quote (k = {judge_k})", "",
              f"Rule fixed before measuring: keep a method if it gains at least {MIN_NET_GAIN} quotes net and",
              "no document loses proofs.", "",
              "| Chunk size | Method | Found | Gained | Lost | Documents losing proofs | Rule |",
              "|---|---|---|---|---|---|---|"]
    for key, found in sorted(results.items()):
        if key == reference:
            continue
        gained, lost = paired_changes(base, found, judge_k)
        losing = [f.split("-")[0] for f in files
                  if recall_at([x for x in found if x.target.filename == f], judge_k)
                  < recall_at([x for x in base if x.target.filename == f], judge_k)]
        met = len(gained) - len(lost) >= MIN_NET_GAIN and not losing
        lines.append(f"| {key[0]} | {key[1]} | {recall_at(found, judge_k)}/{n} | {', '.join(gained) or '–'} "
                     f"| {', '.join(lost) or '–'} | {', '.join(losing) or 'none'} | {'met' if met else 'not met'} |")

    methods = [m for (size, m) in sorted(results) if size == current_size]
    lines += ["", f"## By document ({current_size} tokens, k = {judge_k})", "",
              "| Document | Chunks | " + " | ".join(methods) + " |", "|---|---|" + "---|" * len(methods)]
    for f in files:
        mine = {m: [x for x in results[(current_size, m)] if x.target.filename == f] for m in methods}
        cells = [f"{recall_at(mine[m], judge_k)}/{len(mine[m])}" for m in methods]
        lines.append(f"| {f} | {mine[methods[0]][0].chunks_in_doc} | " + " | ".join(cells) + " |")

    lines += ["", f"## Rank of each quote's chunk ({current_size} tokens; > {judge_k}: the judge does not see it)", "",
              "| Id | Document | " + " | ".join(methods) + " | Claim |", "|---|---|" + "---|" * len(methods) + "---|"]
    by_id = {m: {x.target.id: x for x in results[(current_size, m)]} for m in methods}

    def shown(x) -> str:
        return str(x.rank) if x.rank else f"split ({x.rank_partial})"
    for x in base:
        ranks = [shown(by_id[m][x.target.id]) for m in methods]
        lines.append(f"| {x.target.id} | {x.target.filename.split('-')[0]} | " + " | ".join(ranks)
                     + f" | {x.target.claim} |")
    return "\n".join(lines) + "\n"


def _retrieval_inputs(args):
    """Settings, stored documents and the 44 targets, after checking both sets."""
    from claimverify.settings import load_settings

    settings = load_settings(args.config)
    documents = corpus_documents(settings)
    texts = {d.filename: d.text for d in documents}
    claims, pairs = load_gold(args.gold), load_retrieval_set(args.set)
    problems = check_gold(claims, texts) + check_retrieval_set(pairs, texts)
    if problems:
        sys.exit("Invalid evaluation sets:\n  - " + "\n  - ".join(problems))
    return settings, documents, retrieval_targets(claims, pairs)


def _reranker(settings):
    from claimverify.components.reranking import CrossEncoderReranker
    return CrossEncoderReranker(device=settings.embedding.device)


def run_retrieval(args) -> None:
    from claimverify.factory import build_embedder
    from claimverify.indexing.chunking import FixedSizeChunker
    from claimverify.retrieval_eval import InMemoryIndex

    settings, documents, targets = _retrieval_inputs(args)
    chunker_cfg = settings.indexing.chunker
    sizes = sorted(set(args.chunk_sizes or []) | {chunker_cfg.chunk_size})
    methods = list(dict.fromkeys(["dense", *args.methods]))  # dense: the reference, always measured
    embedder = build_embedder(settings)
    reranker = _reranker(settings) if "rerank" in methods else None
    results = {}
    for size in sizes:
        chunks = FixedSizeChunker(embedder, size, chunker_cfg.overlap_ratio).chunk(documents)
        index = InMemoryIndex(documents, chunks, embedder, reranker)
        for method in methods:
            results[(size, method)] = [index.find(t, method) for t in targets]
        print(f"[{size} tokens] {len(chunks)} chunks, {len(targets)} quotes ranked ({', '.join(methods)})",
              flush=True)

    report = retrieval_report(results, chunker_cfg.chunk_size,
                              settings.answering.verifier.retriever.top_k_per_doc)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print("\n" + report + f"\nWritten to {args.out}")


def run_retrieval_details(args) -> None:
    """The chunks the judge would read for each quote, for one method and chunk
    size (by default the verifier's of config.yaml)."""
    from claimverify.factory import build_embedder
    from claimverify.indexing.chunking import FixedSizeChunker
    from claimverify.retrieval_eval import InMemoryIndex, details_report

    settings, documents, targets = _retrieval_inputs(args)
    retriever = settings.answering.verifier.retriever
    method = args.method or ("rerank" if retriever.rerank else "hybrid" if retriever.type == "hybrid" else "dense")
    size = args.size or settings.indexing.chunker.chunk_size
    k = args.k or retriever.top_k_per_doc
    embedder = build_embedder(settings)
    chunks = FixedSizeChunker(embedder, size, settings.indexing.chunker.overlap_ratio).chunk(documents)
    index = InMemoryIndex(documents, chunks, embedder, _reranker(settings) if method == "rerank" else None)
    out = args.out or Path(f"runs/retrieval_details_{method}_{size}_k{k}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(details_report(index, targets, method, k, size), encoding="utf-8")
    print(f"{len(targets)} quotes, {method}, chunks of {size} tokens, k = {k}: written to {out}")


def run_chunks(args) -> None:
    """The corpus cut at any size, in memory: the database is not touched."""
    from claimverify.factory import build_embedder
    from claimverify.indexing.chunking import FixedSizeChunker
    from claimverify.retrieval_eval import chunks_report
    from claimverify.settings import load_settings

    settings = load_settings(args.config)
    documents = corpus_documents(settings)
    size = args.size or settings.indexing.chunker.chunk_size
    overlap = settings.indexing.chunker.overlap_ratio
    chunks = FixedSizeChunker(build_embedder(settings), size, overlap).chunk(documents)
    out = args.out or Path(f"runs/chunks_{size}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(chunks_report(documents, chunks, size, overlap), encoding="utf-8")
    print(f"{len(chunks)} chunks of at most {size} tokens: written to {out}")


def run_judge(args) -> None:
    """config.yaml's verifier on each claim of the gold set (LLM CALLS). Each
    verdict is written as soon as it arrives: a stop (daily limit) loses
    nothing already paid for, and --resume continues without paying again."""
    import psycopg2

    from claimverify.contracts import Claim, Verdict
    from claimverify.factory import build_embedder, build_verifier
    from claimverify.judge_eval import report, score
    from claimverify.llm import LLMCallError, UsageMeter
    from claimverify.settings import load_settings

    settings = load_settings(args.config)
    gold = load_gold(args.gold)
    problems = check_gold(gold, corpus_texts(settings))
    if problems:
        sys.exit("Invalid gold set:\n  - " + "\n  - ".join(problems))

    verdicts: dict[str, Verdict] = {}
    if args.resume and args.verdicts.exists():
        verdicts = {v.claim_id: v for v in _load_jsonl(args.verdicts, Verdict)}
    todo = [Claim(id=g.id, claim=g.claim) for g in gold if g.id not in verdicts]
    print(f"{len(verdicts)} verdicts already saved, {len(todo)} to obtain from the judge", flush=True)

    meter = UsageMeter()
    conn = psycopg2.connect(args.db_url)
    args.verdicts.parent.mkdir(parents=True, exist_ok=True)
    stopped = None
    try:
        verifier = build_verifier(settings, build_embedder(settings), conn, meter)
        with args.verdicts.open("a" if args.resume else "w", encoding="utf-8") as out:
            for v in verifier.verify(todo):
                verdicts[v.claim_id] = v
                out.write(v.model_dump_json() + "\n")
                out.flush()
                u = meter.take()
                print(f"[{len(verdicts)}/{len(gold)}] {v.claim_id}: {v.verdict} "
                      f"({u.tokens_in + u.tokens_out} tokens, waited {u.waited_seconds:.0f}s)", flush=True)
    except LLMCallError as e:
        stopped = str(e)
        print(f"Stopped: {stopped}", flush=True)
    finally:
        conn.close()

    totals = meter.totals_by_role().get("verify")
    note = (f"This run: {totals.calls} judge calls, {totals.tokens_in + totals.tokens_out} tokens, "
            f"{totals.waited_seconds:.0f} s of rate-limit waits." if totals else "")
    if stopped:
        note += f" **Stopped early: {stopped}** (resume with --resume)."
    judge = settings.answering.verifier.judge.model
    text = report(score(gold, verdicts), judge, note)
    args.out.write_text(text, encoding="utf-8")
    print("\n" + text + f"\nWritten to {args.out} (verdicts: {args.verdicts})")


def _selected(questions: list[GoldQuestion], only: list[str] | None) -> list[GoldQuestion]:
    """The questions named by --only (all of them without it)."""
    if not only:
        return questions
    unknown = set(only) - {q.id for q in questions}
    if unknown:
        sys.exit(f"Unknown question ids: {', '.join(sorted(unknown))}")
    return [q for q in questions if q.id in only]


def _load_manifest(path: Path) -> dict[str, dict]:
    """question id -> {"run_id", "question_index"}: which recorded run answered it."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def run_e2e(args) -> None:
    """The whole pipeline on each question of the set (LLM CALLS, about 50K
    tokens per question). Each question is its own run in runs/, recorded in
    the manifest as soon as it finishes: a stop (daily limit) loses nothing
    already paid for, and --resume skips the questions already answered."""
    import time

    import psycopg2

    from claimverify.answering.pipeline import run_single_question
    from claimverify.events import RunFinished, RunStarted
    from claimverify.factory import build_answering
    from claimverify.llm import LLMCallError
    from claimverify.reporting import Run
    from claimverify.settings import load_settings

    settings = load_settings(args.config)
    questions = load_questions(args.questions)
    problems = check_questions(questions, corpus_texts(settings))
    if problems:
        sys.exit("Invalid question set:\n  - " + "\n  - ".join(problems))
    questions = _selected(questions, args.only)

    manifest = _load_manifest(args.manifest) if args.resume else {}
    todo = [q for q in questions if q.id not in manifest]
    print(f"{len(manifest)} questions already answered, {len(todo)} to run "
          f"(about {50 * len(todo)}K tokens)", flush=True)

    conn = psycopg2.connect(args.db_url)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    try:
        stages = build_answering(settings, conn)
        for q in todo:
            run, start = Run("answering"), time.perf_counter()
            run.emit(RunStarted, config=settings.model_dump(),
                     inputs={"config_file": str(args.config), "questions": [q.question], "eval_question": q.id})
            run_single_question(q.question, stages, run)
            run.emit(RunFinished, seconds=time.perf_counter() - start, summary={"questions": 1, "run_dir": str(run.dir)})
            manifest[q.id] = {"run_id": run.run_id, "question_index": 1}
            args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except LLMCallError as e:
        print(f"Stopped: {e} (resume with --resume)", flush=True)
    finally:
        conn.close()
    score_e2e(args)


def score_e2e(args) -> None:
    """Scores the runs of the manifest (no LLM call): rerun it after changing a check."""
    from claimverify.e2e_eval import read_question, report, review_sheet, score_question
    from claimverify.reporting import RUNS_DIR, load_events

    questions = _selected(load_questions(args.questions), args.only)
    manifest = _load_manifest(args.manifest)
    scored, models = [], "No run"
    for q in questions:
        entry = manifest.get(q.id)
        if entry is None:
            continue
        events = load_events(RUNS_DIR / entry["run_id"] / "events.jsonl")
        run = read_question(events, entry["question_index"])
        if run is None:
            print(f"{q.id}: run {entry['run_id']} did not finish, not scored", flush=True)
            continue
        scored.append(score_question(q, run))
        answering = events[0].config["answering"]
        models = (f"Drafter `{answering['drafter']['model']}`, "
                  f"judge `{answering['verifier']['judge']['model']}`")

    text = report(scored, questions, models)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    review = args.out.with_name(args.out.stem + "_review.md")
    review.write_text(review_sheet(scored), encoding="utf-8")
    print("\n" + text + f"\nWritten to {args.out} (review sheet: {review})")


def main():
    from claimverify.config import add_db_url_argument
    from claimverify.settings import add_config_argument, load_settings

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-gold", help="Checks the gold set (no LLM call).")
    check.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    check.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS_PATH)
    add_config_argument(check)
    retrieval = commands.add_parser("retrieval", help="Does the search bring back the proofs? (no LLM call)")
    retrieval.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    retrieval.add_argument("--set", type=Path, default=DEFAULT_RETRIEVAL_SET_PATH)
    retrieval.add_argument("--chunk-sizes", type=int, nargs="*", default=None,
                           help="Chunk sizes to compare, besides config.yaml's (e.g. 256 510).")
    retrieval.add_argument("--methods", nargs="*", default=["dense"], choices=["dense", "bm25", "hybrid", "rerank"],
                           help="Search methods to compare with today's search (dense).")
    retrieval.add_argument("--out", type=Path, default=Path("eval/results/retrieval.md"))
    add_config_argument(retrieval)
    details = commands.add_parser("retrieval-details",
                                  help="The chunks the judge would read for each quote (no LLM call).")
    details.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    details.add_argument("--set", type=Path, default=DEFAULT_RETRIEVAL_SET_PATH)
    details.add_argument("--method", choices=["dense", "bm25", "hybrid", "rerank"], default=None,
                         help="Search method (default: the verifier's in config.yaml).")
    details.add_argument("--size", type=int, default=None, help="Chunk size in tokens (default: config.yaml's).")
    details.add_argument("--k", type=int, default=None, help="Chunks read per document (default: config.yaml's).")
    details.add_argument("--out", type=Path, default=None)
    add_config_argument(details)
    chunk_dump = commands.add_parser("chunks", help="Writes every chunk of the corpus at a chunk size (no LLM call).")
    chunk_dump.add_argument("--size", type=int, default=None, help="Chunk size in tokens (default: config.yaml's).")
    chunk_dump.add_argument("--out", type=Path, default=None)
    add_config_argument(chunk_dump)
    judge = commands.add_parser("judge", help="The verifier on the gold set (LLM CALLS: costs quota).")
    judge.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    judge.add_argument("--verdicts", type=Path, default=Path("eval/results/judge_verdicts.jsonl"))
    judge.add_argument("--out", type=Path, default=Path("eval/results/judge.md"))
    judge.add_argument("--resume", action="store_true", help="Keeps the verdicts already written, asks for the others.")
    add_config_argument(judge)
    add_db_url_argument(judge)
    e2e = commands.add_parser("e2e", help="The whole pipeline on the question set (LLM CALLS: costs quota).")
    rescore = commands.add_parser("score-e2e", help="Scores the recorded end-to-end runs (no LLM call).")
    for p in (e2e, rescore):
        p.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS_PATH)
        p.add_argument("--manifest", type=Path, default=Path("eval/results/e2e_runs.json"))
        p.add_argument("--out", type=Path, default=Path("eval/results/e2e.md"))
        p.add_argument("--only", nargs="*", default=None, metavar="ID",
                       help="Only these questions (e.g. q01 q04), for a smoke test within one day's quota.")
    e2e.add_argument("--resume", action="store_true", help="Keeps the questions already answered, runs the others.")
    add_config_argument(e2e)
    add_db_url_argument(e2e)
    args = parser.parse_args()

    if args.command == "e2e":
        run_e2e(args)
        return
    if args.command == "score-e2e":
        score_e2e(args)
        return
    if args.command == "judge":
        run_judge(args)
        return
    if args.command == "retrieval":
        run_retrieval(args)
        return
    if args.command == "retrieval-details":
        run_retrieval_details(args)
        return
    if args.command == "chunks":
        run_chunks(args)
        return

    texts = corpus_texts(load_settings(args.config))
    claims = load_gold(args.gold)
    problems = check_gold(claims, texts)

    print(f"{len(claims)} claims in {args.gold}")
    for category in CATEGORIES:
        labels = Counter(c.expected for c in claims if c.category == category)
        print(f"  {category:22} {sum(labels.values())}  " + ", ".join(f"{n} {lab}" for lab, n in labels.items()))
    if args.questions.exists():
        questions = load_questions(args.questions)
        problems += check_questions(questions, texts)
        print(f"\n{len(questions)} questions in {args.questions}")
        for category in QUESTION_CATEGORIES:
            print(f"  {category:22} {sum(q.category == category for q in questions)}")
    else:
        print(f"\nNo question set yet ({args.questions}): not checked.")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("\nEvaluation sets valid.")


if __name__ == "__main__":
    main()
