"""
Évaluation du retrieval — la recherche ramène-t-elle la preuve ?
=================================================================

Avant même que le juge lise quoi que ce soit, la recherche doit lui apporter
le passage qui contient la preuve. Pour chaque paire claim -> citation (gold
set et jeu de retrieval), on classe TOUS les chunks du document de la
citation par similarité au claim, comme le fait la recherche par document, et
on note le RANG du premier chunk qui contient la citation :

    rang 1 : la preuve est dans le meilleur chunk du document
    rang 3 : elle n'est vue qu'avec top_k_per_doc >= 3

Un seul passage donne donc le rappel pour tous les k (1, 2, 3, 5...). Une
citation à cheval sur deux chunks n'est "trouvée" qu'en partie : on note aussi
le rang du premier chunk qui en contient un morceau.

C'est une borne BASSE : un autre chunk peut dire la même chose autrement
(un résultat repris dans la conclusion), ce qui suffit au juge mais n'est pas
détectable automatiquement.

La recherche se fait EN MÉMOIRE (produit scalaire des vecteurs normalisés,
c'est-à-dire la similarité cosinus de pgvector) : comparer des tailles de
chunks ne touche pas la table réelle. Aucun appel LLM.
"""

import math
import unicodedata
from dataclasses import dataclass

from claimverify.components.lexical import Bm25Index, reciprocal_rank_fusion
from claimverify.contracts import Chunk, Document

K_VALUES = (1, 2, 3, 5)
METHODS = ("dense", "bm25", "hybrid")


@dataclass(frozen=True)
class Target:
    """Ce qu'on cherche : la citation `quote` de `filename`, pour le claim `claim`."""
    id: str
    claim: str
    filename: str
    quote: str


@dataclass(frozen=True)
class Found:
    target: Target
    rank: int | None          # rang du premier chunk contenant toute la citation
    rank_partial: int | None  # rang du premier chunk en contenant au moins un morceau
    chunks_in_doc: int
    score: float | None       # similarité du chunk au rang `rank` (ou partiel)


# --- Où est la citation dans le document ? ------------------------------------------------

def quote_spans(text: str, quote: str) -> list[tuple[int, int]]:
    """Positions (début, fin) de CHAQUE occurrence de la citation dans le texte
    original, en ignorant espaces, retours à la ligne et traits d'union, comme
    le vérificateur du gold set. Un article répète souvent une phrase (résumé,
    introduction) : la preuve est vue si l'UNE d'elles est ramenée."""
    signature, positions = [], []
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKC", ch):
            if not c.isspace() and c != "-":
                signature.append(c)
                positions.append(i)
    wanted = "".join(c for c in unicodedata.normalize("NFKC", quote) if not c.isspace() and c != "-")
    joined, spans, start = "".join(signature), [], 0
    while wanted and (start := joined.find(wanted, start)) >= 0:
        spans.append((positions[start], positions[start + len(wanted) - 1] + 1))
        start += 1
    return spans


def chunk_spans(text: str, chunks: list[Chunk]) -> list[tuple[int, int]]:
    """Position de chaque chunk dans son document : un chunk est une tranche
    exacte du texte, dans l'ordre (voir chunking.py)."""
    spans, cursor = [], 0
    for c in chunks:
        start = text.find(c.text, cursor)
        if start < 0:
            raise ValueError(f"{c.chunk_id} n'est pas une tranche de son document")
        spans.append((start, start + len(c.text)))
        cursor = start + 1  # les chunks se chevauchent : le suivant commence après le début
    return spans


# --- La recherche, en mémoire ------------------------------------------------------------

class InMemoryIndex:
    """Les chunks d'un corpus, classés par document comme le fait
    search_per_document, mais sans base de données, selon trois méthodes :

        dense   par le sens : cosinus des embeddings (la recherche actuelle)
        bm25    par les mots : BM25, poids des mots calculés sur TOUT le corpus
        hybrid  les deux classements fusionnés par leurs rangs (RRF)"""

    def __init__(self, documents: list[Document], chunks: list[Chunk], embedder):
        self.embedder = embedder
        self.texts = {d.filename: d.text for d in documents}
        self.vectors = embedder.embed_texts([c.text for c in chunks])
        self.bm25 = Bm25Index([c.text for c in chunks])
        # par document : (indice du chunk dans `chunks`, sa position dans le texte)
        self.by_doc: dict[str, list[tuple[int, tuple[int, int]]]] = {}
        for d in documents:
            mine = [i for i, c in enumerate(chunks) if c.filename == d.filename]
            spans = chunk_spans(d.text, [chunks[i] for i in mine])
            self.by_doc[d.filename] = list(zip(mine, spans, strict=True))

    def ranking(self, claim: str, filename: str, method: str = "dense") -> list[tuple[tuple[int, int], float]]:
        """(position, score) de chaque chunk du document, du meilleur au moins bon."""
        if method not in METHODS:
            raise ValueError(f"méthode inconnue {method!r} (disponibles : {METHODS})")
        items = self.by_doc[filename]
        query = self.embedder.embed_query(claim)
        dense = {i: sum(a * b for a, b in zip(query, self.vectors[i], strict=True)) for i, _ in items}
        lexical = self.bm25.scores(claim)
        words = {i: lexical[i] for i, _ in items}
        span = dict(items)

        def by_score(scores: dict[int, float]) -> list[int]:
            return sorted(scores, key=lambda i: scores[i], reverse=True)

        if method == "dense":
            return [(span[i], dense[i]) for i in by_score(dense)]
        if method == "bm25":
            return [(span[i], words[i]) for i in by_score(words)]
        fused = reciprocal_rank_fusion([by_score(dense), by_score(words)])
        return [(span[i], dense[i]) for i in fused]  # score affiché : le cosinus, pour comparer

    def find(self, target: Target, method: str = "dense") -> Found:
        quotes = quote_spans(self.texts[target.filename], target.quote)
        if not quotes:
            raise ValueError(f"{target.id} : citation introuvable dans {target.filename}")
        ranking = self.ranking(target.claim, target.filename, method)
        rank = rank_partial = score = None
        for r, ((start, end), s) in enumerate(ranking, start=1):
            if rank_partial is None and any(start < q_end and q_start < end for q_start, q_end in quotes):
                rank_partial, score = r, s
            if any(start <= q_start and q_end <= end for q_start, q_end in quotes):
                rank, score = r, s
                break
        return Found(target, rank, rank_partial, len(ranking), score)


# --- Résumés -------------------------------------------------------------------------

def recall_at(found: list[Found], k: int, partial: bool = False) -> int:
    """Nombre de citations dont le chunk est dans les k premiers de son document."""
    def rank(f: Found) -> int | None:
        return f.rank_partial if partial else f.rank
    return sum(1 for f in found if rank(f) is not None and rank(f) <= k)


def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de confiance à 95 % d'une proportion mesurée sur peu
    d'exemples (Wilson) : 9/11 -> environ 52 % à 95 %."""
    if n == 0:
        return 0.0, 1.0
    p = hits / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, center - half), min(1.0, center + half)


def paired_changes(before: list[Found], after: list[Found], k: int) -> tuple[list[str], list[str]]:
    """Comparaison citation par citation entre deux réglages : (gagnées, perdues) au rang k."""
    def hit(f: Found) -> bool:
        return f.rank is not None and f.rank <= k
    old = {f.target.id: hit(f) for f in before}
    gained = [f.target.id for f in after if hit(f) and not old[f.target.id]]
    lost = [f.target.id for f in after if not hit(f) and old[f.target.id]]
    return gained, lost
