"""
End-to-end evaluation — the whole pipeline against the question set
====================================================================

Each question of eval/questions.jsonl goes through the REAL pipeline (draft,
decomposition, verification). The claims are written by the pipeline, so they
cannot be labelled in advance: each question is scored by checks that hold
whatever the claims are, read from its recorded events (no LLM call here).

    sources used       every document holding a quote is cited by a verdict
    no false conflict  no `contested` verdict, except on conflict questions
    conflict found     a `contested` verdict with the two sides of the conflict
    no contradiction   no claim of the answer is `contradicted` (single/multi source)
    premise caught     the false premise is contradicted, or its correction supported
                       by the passage that refutes it
    nothing supported  no claim is `supported` on a question the corpus never discusses

Each failed check says whether the proof reached the judge, as in the judge
evaluation: a proof never read is a retrieval failure, not a judgment one.
The checks cannot tell whether every verdict is right: the review sheet lists
each claim with its verdict and evidence, to be read by a human.

With 5 questions (one per category, `make eval-e2e`) or 10 (ALL=1), this is a smoke
test: read the counts.
"""

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

from claimverify.contracts import VERDICT_LABELS, Claim, Draft, Verdict
from claimverify.evaluation import QUESTION_CATEGORIES, GoldQuestion
from claimverify.events import (
    ClaimsExtracted,
    ClaimVerified,
    DraftWritten,
    Event,
    PassagesRetrieved,
    QuestionFinished,
    Usage,
)
from claimverify.indexing.cleaning import content_signature

# Two claims whose wording is at least this similar count as near-identical
# (a textual stand-in for the embedding test planned in the roadmap).
NEAR_DUPLICATE_RATIO = 0.8

CHECKS: dict[str, tuple[str, ...]] = {
    "single_source": ("sources used", "no false conflict", "no contradiction"),
    "multi_source": ("sources used", "no false conflict", "no contradiction"),
    "conflict": ("sources used", "conflict found"),
    "false_premise": ("sources used", "no false conflict", "premise caught"),
    "out_of_corpus": ("no false conflict", "nothing supported"),
}


@dataclass(frozen=True)
class QuestionRun:
    """What the pipeline produced for one question, read back from its events."""
    draft: Draft
    claims: list[Claim]
    verdicts: list[Verdict]
    usage: Usage
    seconds: float


def read_question(events: list[Event], question_index: int) -> QuestionRun | None:
    """The question's outputs, or None if it did not finish (stopped run)."""
    mine = [e for e in events if getattr(e, "question_index", None) == question_index]
    finished = next((e for e in mine if isinstance(e, QuestionFinished)), None)
    draft = next((e.draft for e in mine if isinstance(e, DraftWritten)), None)
    if finished is None or draft is None:
        return None
    usage = Usage()
    for e in mine:
        if isinstance(e, (PassagesRetrieved, DraftWritten, ClaimsExtracted, ClaimVerified)):
            usage = usage + e.usage
    claims = next((e.claims for e in mine if isinstance(e, ClaimsExtracted)), [])
    verdicts = [e.verdict for e in mine if isinstance(e, ClaimVerified)]
    return QuestionRun(draft, claims, verdicts, usage, finished.seconds)


@dataclass(frozen=True)
class Scored:
    question: GoldQuestion
    run: QuestionRun
    checks: dict[str, bool]
    proofs_read: int        # quotes found in a passage the judge read
    proofs_drafted: int     # quotes found in the drafter's passages

    @property
    def passed(self) -> bool:
        return all(self.checks.values())


def _read(quote_filename: str, quote: str, passages) -> bool:
    sig = content_signature(quote)
    return any(p.filename == quote_filename and sig in content_signature(p.text) for p in passages)


def _cited(v: Verdict) -> set[str]:
    return set(v.supporting_sources) | set(v.contradicting_sources)


def _conflict_found(q: GoldQuestion, verdicts: list[Verdict]) -> bool:
    # The pipeline may phrase the claim either way ("X improves" or "X does not
    # improve"), so the two sides may be cited in either order.
    pro = {e.filename for e in q.evidence if e.stance == "supports"}
    con = {e.filename for e in q.evidence if e.stance == "contradicts"}
    for v in verdicts:
        if v.verdict != "contested":
            continue
        s, c = set(v.supporting_sources), set(v.contradicting_sources)
        if any(p != n and ((p in s and n in c) or (p in c and n in s)) for p in pro for n in con):
            return True
    return False


def _premise_caught(q: GoldQuestion, verdicts: list[Verdict]) -> bool:
    for v in verdicts:
        for e in q.evidence:  # all "contradicts" for a false premise
            if v.verdict == "contradicted" and e.filename in v.contradicting_sources:
                return True
            # the draft corrected the premise: the correction is supported by the
            # very passage that refutes the premise
            if (v.verdict == "supported" and e.filename in v.supporting_sources
                    and _read(e.filename, e.quote, v.evidence)):
                return True
    return False


def score_question(q: GoldQuestion, run: QuestionRun) -> Scored:
    verdicts = run.verdicts
    results = {
        "sources used": q.documents <= set().union(*map(_cited, verdicts)) if verdicts else not q.documents,
        "no false conflict": not any(v.verdict == "contested" for v in verdicts),
        "conflict found": _conflict_found(q, verdicts),
        "no contradiction": not any(v.verdict == "contradicted" for v in verdicts),
        "premise caught": _premise_caught(q, verdicts),
        "nothing supported": not any(v.verdict == "supported" for v in verdicts),
    }
    read = [p for v in verdicts for p in v.evidence]
    return Scored(
        q, run, {name: results[name] for name in CHECKS[q.category]},
        proofs_read=sum(_read(e.filename, e.quote, read) for e in q.evidence),
        proofs_drafted=sum(_read(e.filename, e.quote, run.draft.passages) for e in q.evidence),
    )


def near_duplicates(claims: list[Claim]) -> int:
    """Pairs of claims with near-identical wording."""
    texts = [c.claim.lower() for c in claims]
    return sum(SequenceMatcher(None, a, b).ratio() >= NEAR_DUPLICATE_RATIO
               for i, a in enumerate(texts) for b in texts[i + 1:])


def report(scored: list[Scored], questions: list[GoldQuestion], models: str) -> str:
    n = len(scored)
    lines = ["# End-to-end evaluation on the question set", "",
             f"{models}. {n} of {len(questions)} questions scored, each through the whole pipeline",
             "(draft, decomposition, verification). A question passes when all the checks of its",
             "category pass (see `src/claimverify/e2e_eval.py`). A smoke test (1 or 2 questions",
             "per category): read the counts, not percentages.", "",
             f"**Questions passed: {sum(s.passed for s in scored)}/{n}.**", ""]
    missing = [q.id for q in questions if q.id not in {s.question.id for s in scored}]
    if missing:
        lines += [f"Not run yet: {', '.join(missing)}.", ""]

    lines += ["## By category", "", "| Category | Passed | Checks |", "|---|---|---|"]
    for c in QUESTION_CATEGORIES:
        mine = [s for s in scored if s.question.category == c]
        if mine:
            lines.append(f"| {c} | {sum(s.passed for s in mine)}/{len(mine)} | {', '.join(CHECKS[c])} |")

    lines += ["", "## By check", "", "| Check | Passed |", "|---|---|"]
    names = dict.fromkeys(name for s in scored for name in s.checks)
    for name in names:
        mine = [s.checks[name] for s in scored if name in s.checks]
        lines.append(f"| {name} | {sum(mine)}/{len(mine)} |")

    claims = [c for s in scored for c in s.run.claims]
    meta = sum(c.kind == "meta" for c in claims)
    counts = Counter(v.verdict for s in scored for v in s.run.verdicts)
    tokens = sum(s.run.usage.tokens_in + s.run.usage.tokens_out for s in scored)
    lines += ["", "## Recorded, not graded", "",
              (f"- Claims: {len(claims)} ({len(claims) / max(n, 1):.1f} per question), "
               f"of which {meta} about the answer itself (meta, not verified), "
               f"near-identical pairs: {sum(near_duplicates(s.run.claims) for s in scored)}"),
              "- Verdicts: " + ", ".join(f"{counts[lab]} {lab}" for lab in VERDICT_LABELS),
              (f"- Tokens: {tokens} ({tokens // max(n, 1)} per question), "
               f"rate-limit waits: {sum(s.run.usage.waited_seconds for s in scored):.0f} s, "
               f"time: {sum(s.run.seconds for s in scored):.0f} s"), ""]

    lines += ["## Every question", "",
              "Proofs: the question's quotes found in the drafter's passages / in the judge's passages.", "",
              "Claims: verified + meta (about the answer itself, not verified).", "",
              "| Id | Category | Result | Failed checks | Proofs (draft / judge) | Claims | Verdicts |",
              "|---|---|---|---|---|---|---|"]
    for s in scored:
        failed = ", ".join(name for name, ok in s.checks.items() if not ok) or "–"
        total = len(s.question.evidence)
        proofs = f"{s.proofs_drafted}/{total} / {s.proofs_read}/{total}" if total else "–"
        verdicts = Counter(v.verdict for v in s.run.verdicts)
        lines.append(f"| {s.question.id} | {s.question.category} | {'✓ pass' if s.passed else '✗ fail'} | "
                     f"{failed} | {proofs} | {len(s.run.verdicts)} + {len(s.run.claims) - len(s.run.verdicts)} | "
                     + (", ".join(f"{k} {lab}" for lab, k in verdicts.items()) or "–") + " |")
    return "\n".join(lines) + "\n"


def review_sheet(scored: list[Scored]) -> str:
    """Every claim with its verdict and what the judge read: for a human to
    say whether each verdict is right (the checks cannot)."""
    lines = ["# End-to-end review sheet", "",
             "Each claim the pipeline wrote, its verdict and its justification. Mark each verdict",
             "right or wrong by hand: the automatic checks only test the question as a whole.", ""]
    for s in scored:
        q = s.question
        lines += [f"## {q.id} ({q.category}): {q.question}", ""]
        if q.statement:
            lines += [f"Statement: *{q.statement}*", ""]
        lines += ["### Draft", "", s.run.draft.text, "", "### Verdicts", ""]
        for v in s.run.verdicts:
            sources = (f" (for: {', '.join(v.supporting_sources) or '–'}; "
                       f"against: {', '.join(v.contradicting_sources) or '–'})")
            read = ", ".join(f"{p.filename.split('-')[0]} #{p.chunk_index}" for p in v.evidence)
            lines += [f"- **{v.verdict}**{sources}: {v.claim}",
                      f"  - {v.justification}",
                      f"  - Read: {read or '–'}",
                      "  - Right? ☐ yes ☐ no", ""]
        meta = [c for c in s.run.claims if c.kind == "meta"]
        if meta:
            lines += ["### Set aside as being about the answer itself (not verified)", ""]
            lines += [f"- {c.claim}\n  - Really about the answer, not the topic? ☐ yes ☐ no\n" for c in meta]
    return "\n".join(lines)
