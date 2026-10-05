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

Le jeu de retrieval (eval/retrieval_set.jsonl) est plus simple et plus grand :
des paires claim -> citation, sans verdict. Il ne sert qu'à mesurer si la
recherche ramène la preuve (retrieval_eval.py) : aucune étiquette à relire,
aucun appel LLM, donc on peut se permettre plus d'exemples.

Usage :
    python -m claimverify.evaluation check-gold         (aucun appel LLM, aucune base)
    python -m claimverify.evaluation retrieval          (aucun appel LLM ; GPU pour l'embedding)
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
CORPUS_DIR = Path("data/corpus")

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


class RetrievalPair(BaseModel):
    """Un claim et la citation que la recherche devrait ramener (sans verdict)."""
    model_config = ConfigDict(extra="forbid")
    id: str
    claim: str = Field(min_length=10)
    filename: str
    quote: str = Field(min_length=20)


def _load_jsonl(path: Path, model: type[M]) -> list[M]:
    """Une ligne JSON par objet ; les lignes vides sont ignorées. Une erreur
    indique la ligne fautive."""
    items = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(model.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as e:
            raise ValueError(f"{path}, ligne {number} : {e}") from e
    return items


def load_gold(path: Path) -> list[GoldClaim]:
    return _load_jsonl(path, GoldClaim)


def load_retrieval_set(path: Path) -> list[RetrievalPair]:
    return _load_jsonl(path, RetrievalPair)


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

    quotes = [(c.id, e.filename, e.quote) for c in claims for e in c.evidence]
    return problems + _quote_problems(quotes, documents)


def check_retrieval_set(pairs: list[RetrievalPair], documents: dict[str, str]) -> list[str]:
    problems = [f"id en double : {pair_id} ({n} fois)"
                for pair_id, n in Counter(p.id for p in pairs).items() if n > 1]
    return problems + _quote_problems([(p.id, p.filename, p.quote) for p in pairs], documents)


def _quote_problems(quotes: list[tuple[str, str, str]], documents: dict[str, str]) -> list[str]:
    # Comparaison sans espaces, retours à la ligne ni traits d'union : une
    # citation copiée depuis le PDF ou depuis le texte stocké est retrouvée,
    # une citation inventée ou modifiée ne l'est pas.
    signatures = {name: content_signature(text) for name, text in documents.items()}
    problems = []
    for item_id, filename, quote in quotes:
        if filename not in documents:
            problems.append(f"{item_id} : {filename} n'est pas dans le corpus")
        elif content_signature(quote) not in signatures[filename]:
            problems.append(f"{item_id} : citation introuvable dans {filename} : « {quote[:60]}… »")
    return problems


def corpus_documents(settings) -> list[Document]:
    """Les documents tels qu'ils sont stockés : chargés puis nettoyés par les
    étapes de config.yaml (sans embedder ni base)."""
    from claimverify.factory import build_cleaner, build_loader  # import local : factory est lourde

    documents = build_loader(settings).load(CORPUS_DIR)
    return [c.document for c in build_cleaner(settings).clean(documents)]


def corpus_texts(settings) -> dict[str, str]:
    return {d.filename: d.text for d in corpus_documents(settings)}


def retrieval_targets(claims: list[GoldClaim], pairs: list[RetrievalPair]):
    """Chaque citation du gold set et du jeu de retrieval devient une cible
    (g02.1, g02.2 quand un claim en a plusieurs)."""
    from claimverify.retrieval_eval import Target

    targets = []
    for c in claims:
        for i, e in enumerate(c.evidence, start=1):
            suffix = f".{i}" if len(c.evidence) > 1 else ""
            targets.append(Target(f"{c.id}{suffix}", c.claim, e.filename, e.quote))
    return targets + [Target(p.id, p.claim, p.filename, p.quote) for p in pairs]


# Règle fixée AVANT la mesure, pour ne pas choisir le seuil après avoir vu les chiffres :
# une méthode remplace la recherche actuelle si elle gagne au moins MIN_NET_GAIN citations
# nettes au k du juge, sans qu'aucun document ne perde de preuves.
MIN_NET_GAIN = 4


def retrieval_report(results: dict[tuple[int, str], list], current_size: int, judge_k: int) -> str:
    """Le rapport en Markdown. `results` : (taille de chunk, méthode) -> résultats.
    La référence est la recherche actuelle : taille de config.yaml, méthode dense."""
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


def run_retrieval(args) -> None:
    from claimverify.factory import build_embedder
    from claimverify.indexing.chunking import FixedSizeChunker
    from claimverify.retrieval_eval import InMemoryIndex
    from claimverify.settings import load_settings

    settings = load_settings(args.config)
    documents = corpus_documents(settings)
    texts = {d.filename: d.text for d in documents}
    claims, pairs = load_gold(args.gold), load_retrieval_set(args.set)
    problems = check_gold(claims, texts) + check_retrieval_set(pairs, texts)
    if problems:
        sys.exit("Jeux d'évaluation invalides :\n  - " + "\n  - ".join(problems))

    targets = retrieval_targets(claims, pairs)
    chunker_cfg = settings.indexing.chunker
    sizes = sorted(set(args.chunk_sizes or []) | {chunker_cfg.chunk_size})
    methods = list(dict.fromkeys(["dense", *args.methods]))  # dense : la référence, toujours mesurée
    embedder = build_embedder(settings)
    reranker = None
    if "rerank" in methods:
        from claimverify.components.reranking import CrossEncoderReranker
        reranker = CrossEncoderReranker(device=settings.embedding.device)
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
    print("\n" + report + f"\nÉcrit dans {args.out}")


def main():
    from claimverify.settings import add_config_argument, load_settings

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-gold", help="Vérifie le gold set (aucun appel LLM).")
    check.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    add_config_argument(check)
    retrieval = commands.add_parser("retrieval", help="La recherche ramène-t-elle les preuves ? (aucun appel LLM)")
    retrieval.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    retrieval.add_argument("--set", type=Path, default=DEFAULT_RETRIEVAL_SET_PATH)
    retrieval.add_argument("--chunk-sizes", type=int, nargs="*", default=None,
                           help="Tailles de chunks à comparer, en plus de celle de config.yaml (ex. 256 510).")
    retrieval.add_argument("--methods", nargs="*", default=["dense"], choices=["dense", "bm25", "hybrid", "rerank"],
                           help="Méthodes de recherche à comparer à la recherche actuelle (dense).")
    retrieval.add_argument("--out", type=Path, default=Path("eval/results/retrieval.md"))
    add_config_argument(retrieval)
    args = parser.parse_args()

    if args.command == "retrieval":
        run_retrieval(args)
        return

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
