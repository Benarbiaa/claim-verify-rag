"""
Judge evaluation — its verdicts against the gold set
====================================================

Each claim of the gold set (eval/claims_gold.jsonl) goes through the REAL
verifier of config.yaml (search + LLM judge), as in the pipeline, without a
draft or a decomposition. Its verdict is compared with the proven label.

Each error is given one of two causes:
    the proof was not in the passages read   -> a RETRIEVAL failure
    the proof was there, the verdict is wrong -> a JUDGE failure
Without this distinction, a bad score does not say what to fix.

With 10 claims (2 per category), this is a smoke test: results read as
counts ("1/2"), not percentages.
"""

from collections import Counter
from dataclasses import dataclass

from claimverify.contracts import VERDICT_LABELS, Verdict
from claimverify.evaluation import CATEGORIES, GoldClaim
from claimverify.indexing.cleaning import content_signature

COMPLEMENTARY = "complementary"


@dataclass(frozen=True)
class Scored:
    gold: GoldClaim
    verdict: Verdict
    correct: bool
    proof_seen: bool | None    # were all the proof quotes in the passages read? (None: no quote)
    sources_ok: bool           # do the sources the judge cited include the gold set's?


def proof_seen(gold: GoldClaim, verdict: Verdict) -> bool | None:
    """Is each quote of the gold set in a passage the judge read?"""
    if not gold.evidence:
        return None
    read = {p.filename: [] for p in verdict.evidence}
    for p in verdict.evidence:
        read[p.filename].append(content_signature(p.text))
    return all(any(content_signature(e.quote) in text for text in read.get(e.filename, []))
               for e in gold.evidence)


def sources_ok(gold: GoldClaim, verdict: Verdict) -> bool:
    pro = {e.filename for e in gold.evidence if e.stance == "supports"}
    con = {e.filename for e in gold.evidence if e.stance == "contradicts"}
    if gold.expected == "unverifiable":
        return not verdict.supporting_sources and not verdict.contradicting_sources
    return pro <= set(verdict.supporting_sources) and con <= set(verdict.contradicting_sources)


def score(gold: list[GoldClaim], verdicts: dict[str, Verdict]) -> list[Scored]:
    """The gold claims that have a verdict (a run stopped midway has fewer)."""
    return [Scored(g, verdicts[g.id], verdicts[g.id].verdict == g.expected,
                   proof_seen(g, verdicts[g.id]), sources_ok(g, verdicts[g.id]))
            for g in gold if g.id in verdicts]


def cause(s: Scored) -> str:
    if s.correct:
        return "–"
    if s.verdict.verdict == "error":
        return "judge answer unusable"
    if s.proof_seen is False:
        return "retrieval: proof not read"
    return "judge"


def report(scored: list[Scored], judge: str, usage_note: str) -> str:
    n = len(scored)
    labels = [lab for lab in VERDICT_LABELS]
    expected_labels = [lab for lab in labels if lab != "error"]
    lines = ["# Judge evaluation on the gold set", "",
             f"Judge: `{judge}`. {n} claims, each verdict compared to its proven label.",
             "A smoke test (2 claims per category): read the counts, not percentages.", "",
             f"**Correct verdicts: {sum(s.correct for s in scored)}/{n}.** {usage_note}", ""]

    lines += ["## By category", "", "| Category | Correct |", "|---|---|"]
    for c in CATEGORIES:
        mine = [s for s in scored if s.gold.category == c]
        if mine:
            lines.append(f"| {c} | {sum(s.correct for s in mine)}/{len(mine)} |")
    comp = [s for s in scored if s.gold.category == COMPLEMENTARY]
    false_alarm = sum(s.verdict.verdict in ("contradicted", "contested") for s in comp)
    lines += ["", f"False contradictions on complementary claims: {false_alarm}/{len(comp)}.", ""]

    counts = Counter((s.gold.expected, s.verdict.verdict) for s in scored)
    lines += ["## Confusion matrix (rows: expected, columns: judge)", "",
              "| expected \\ judge | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for e in expected_labels:
        lines.append(f"| {e} | " + " | ".join(str(counts[(e, j)] or "·") for j in labels) + " |")

    errors = Counter(cause(s) for s in scored if not s.correct)
    lines += ["", "## Why the wrong verdicts are wrong", ""]
    lines += [f"- {c}: {k}" for c, k in errors.most_common()] or ["- none"]

    lines += ["", "## Every claim", "",
              "| Id | Category | Expected | Judge | Proof read | Sources | Cause | Justification |",
              "|---|---|---|---|---|---|---|---|"]
    for s in scored:
        seen = {True: "yes", False: "**no**", None: "–"}[s.proof_seen]
        just = s.verdict.justification.replace("|", "/").replace("\n", " ")
        lines.append(f"| {s.gold.id} | {s.gold.category} | {s.gold.expected} | "
                     f"{'✓' if s.correct else '✗'} {s.verdict.verdict} | {seen} | "
                     f"{'ok' if s.sources_ok else 'wrong'} | {cause(s)} | {just[:220]} |")
    return "\n".join(lines) + "\n"
