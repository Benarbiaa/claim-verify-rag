"""
Évaluation — le gold set de claims et sa vérification
======================================================

Le gold set (eval/claims_gold.jsonl) contient des claims dont le bon verdict
est connu À L'AVANCE, indépendamment du système, et PROUVÉ par une citation
exacte de la source. Le vérificateur est évalué en comparant ses verdicts à
ces réponses. Les étiquettes sont relues par un humain : une erreur ici
deviendrait "la vérité" de toutes les mesures.

Ce module définit le format (GoldClaim) et refuse un gold set incohérent avant
toute mesure : étiquette impossible, sources incompatibles avec l'étiquette,
fichier absent du corpus, ou citation introuvable dans le texte stocké.

Usage (aucun appel LLM, aucune base, aucun GPU) :
    python -m claimverify.evaluation check-gold
    python -m claimverify.evaluation check-gold --gold eval/claims_gold.jsonl --config config.yaml
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from claimverify.contracts import JudgeLabel
from claimverify.indexing.cleaning import content_signature

DEFAULT_GOLD_PATH = Path("eval/claims_gold.jsonl")

Category = Literal["single_source", "perturbed_fact", "cross_source_conflict",
                   "complementary", "out_of_corpus"]
CATEGORIES: tuple[str, ...] = get_args(Category)


class GoldEvidence(BaseModel):
    """Une citation exacte d'une source, et ce qu'elle fait du claim."""
    model_config = ConfigDict(extra="forbid")
    filename: str
    stance: Literal["supports", "contradicts"]
    quote: str = Field(min_length=20)  # une phrase, pas un mot isolé


class GoldClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    category: Category
    claim: str = Field(min_length=10)
    expected: JudgeLabel  # jamais "error" : c'est un échec du juge, pas une conclusion
    evidence: list[GoldEvidence] = []
    note: str = ""        # pourquoi cette étiquette, en une ligne

    @model_validator(mode="after")
    def _evidence_matches_the_label(self) -> "GoldClaim":
        # Plus strict que le contrat Verdict : le gold set est la référence.
        pro = {e.filename for e in self.evidence if e.stance == "supports"}
        con = {e.filename for e in self.evidence if e.stance == "contradicts"}
        rules = {
            "supported": (pro and not con, "au moins une citation pour, aucune contre"),
            "contradicted": (con and not pro, "au moins une citation contre, aucune pour"),
            # "contested" : les SOURCES se contredisent entre elles, donc deux documents différents
            "contested": (pro and con and len(pro | con) >= 2, "des citations des deux côtés, de documents différents"),
            "unverifiable": (not self.evidence, "aucune citation (le corpus n'en parle pas)"),
        }
        ok, rule = rules[self.expected]
        if not ok:
            raise ValueError(f"'{self.expected}' demande {rule}")
        return self


def load_gold(path: Path) -> list[GoldClaim]:
    """Une ligne JSON par claim ; les lignes vides sont ignorées. Une erreur
    indique la ligne fautive."""
    claims = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            claims.append(GoldClaim.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as e:
            raise ValueError(f"{path}, ligne {number} : {e}") from e
    return claims


def check_gold(claims: list[GoldClaim], documents: dict[str, str]) -> list[str]:
    """Problèmes du gold set face au corpus (documents : nom de fichier ->
    texte STOCKÉ, c'est-à-dire nettoyé). Liste vide = gold set utilisable."""
    problems = []
    for claim_id, n in Counter(c.id for c in claims).items():
        if n > 1:
            problems.append(f"id en double : {claim_id} ({n} fois)")
    for category in CATEGORIES:
        if not any(c.category == category for c in claims):
            problems.append(f"aucun claim dans la catégorie {category}")

    # Comparaison sans espaces, retours à la ligne ni traits d'union : une
    # citation copiée depuis le PDF ou depuis le texte stocké est retrouvée,
    # une citation inventée ou modifiée ne l'est pas.
    signatures = {name: content_signature(text) for name, text in documents.items()}
    for c in claims:
        for e in c.evidence:
            if e.filename not in documents:
                problems.append(f"{c.id} : {e.filename} n'est pas dans le corpus")
            elif content_signature(e.quote) not in signatures[e.filename]:
                problems.append(f"{c.id} : citation introuvable dans {e.filename} : « {e.quote[:60]}… »")
    return problems


def corpus_texts(settings) -> dict[str, str]:
    """Le texte de chaque document tel qu'il est stocké : chargé puis nettoyé
    par les étapes de config.yaml (sans embedder ni base)."""
    from claimverify.factory import build_cleaner, build_loader  # import local : factory est lourde

    documents = build_loader(settings).load(Path("data/corpus"))
    return {c.document.filename: c.document.text for c in build_cleaner(settings).clean(documents)}


def main():
    from claimverify.settings import add_config_argument, load_settings

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-gold", help="Vérifie le gold set (aucun appel LLM).")
    check.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    add_config_argument(check)
    args = parser.parse_args()

    claims = load_gold(args.gold)
    problems = check_gold(claims, corpus_texts(load_settings(args.config)))

    print(f"{len(claims)} claims dans {args.gold}")
    for category in CATEGORIES:
        labels = Counter(c.expected for c in claims if c.category == category)
        print(f"  {category:22} {sum(labels.values())}  " + ", ".join(f"{n} {lab}" for lab, n in labels.items()))
    if problems:
        print(f"\n{len(problems)} problème(s) :")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("\nGold set valide.")


if __name__ == "__main__":
    main()
