"""
Évaluation du juge — ses verdicts face au gold set
===================================================

Chaque claim du gold set (eval/claims_gold.jsonl) passe par le VRAI
vérificateur de config.yaml (recherche + juge LLM), comme dans le pipeline,
sans brouillon ni décomposition. Son verdict est comparé à l'étiquette prouvée.

Pour chaque erreur, on distingue deux causes :
    la preuve n'était pas dans les passages lus  -> échec du RETRIEVAL
    la preuve y était, et le verdict est faux     -> échec du JUGE
Sans cette distinction, un mauvais score ne dit pas quoi corriger.

Avec 10 claims (2 par catégorie), c'est un test de fumée : les résultats se
lisent en comptes ("1/2"), pas en pourcentages.
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
    proof_seen: bool | None    # toutes les citations de preuve étaient-elles dans les passages lus ? (None : aucune)
    sources_ok: bool           # les sources citées par le juge contiennent-elles celles du gold set ?


def proof_seen(gold: GoldClaim, verdict: Verdict) -> bool | None:
    """Chaque citation du gold set se trouve-t-elle dans un passage que le juge a lu ?"""
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
    """Les claims du gold set qui ont un verdict (un run arrêté en cours en a moins)."""
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
