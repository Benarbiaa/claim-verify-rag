"""
Retrieval côté réponse — question vers Passages
=================================================

La recherche elle-même (SQL pgvector) est dans components/store.py, et
l'embedding de la requête dans components/embedding.py. Le retriever les
reçoit tous les deux : il ne crée ni modèle ni connexion.

Deux implémentations, choisies dans config.yaml (type) :
    pgvector  par le sens seulement (embeddings)
    hybrid    par le sens ET par les mots (BM25), classements fusionnés
et, en option (rerank), un RerankingRetriever qui enveloppe l'une ou l'autre :
il lui demande plus de candidats par document, puis les fait relire par un
cross-encodeur et garde les meilleurs.
"""

from functools import cached_property
from typing import Protocol, runtime_checkable

from claimverify.components.embedding import Embedder
from claimverify.components.lexical import Bm25Index, reciprocal_rank_fusion
from claimverify.components.reranking import Reranker
from claimverify.components.store import (
    TOP_K_PER_DOC,
    load_chunk_texts,
    rank_all_per_document,
    search_per_document,
)
from claimverify.contracts import Passage


@runtime_checkable
class Retriever(Protocol):
    """Interface : trouve les passages du corpus pertinents pour un texte."""

    def retrieve(self, query: str) -> list[Passage]: ...


class PgvectorRetriever:
    """Implémentation : top-k PAR document dans pgvector (chaque source est représentée)."""

    def __init__(self, embedder: Embedder, conn, top_k_per_doc: int = TOP_K_PER_DOC):
        self.embedder = embedder
        self.conn = conn
        self.top_k_per_doc = top_k_per_doc

    def retrieve(self, query: str) -> list[Passage]:
        return search_per_document(self.conn, self.embedder.embed_query(query), self.top_k_per_doc)


class HybridRetriever:
    """Implémentation : top-k PAR document, après fusion de deux classements.

    Dans un même article, tous les chunks parlent du même sujet : les scores
    d'embedding sont très proches, et le détail qui fait la preuve (un chiffre,
    un nom) pèse à peine. BM25 classe par les mots exacts, pondérés par leur
    rareté dans le corpus. Les deux classements de chaque document sont
    fusionnés par leurs rangs (reciprocal_rank_fusion, sans poids à régler).
    Mesuré sur 44 citations (make eval-retrieval) : la preuve est dans les 2
    premiers passages de son document pour 31/44, contre 23/44 par le sens seul.

    L'index BM25 est construit au premier appel depuis les chunks stockés, puis
    gardé : il faut un nouveau retriever après une réindexation (c'est le cas,
    la factory en construit un par run)."""

    def __init__(self, embedder: Embedder, conn, top_k_per_doc: int = TOP_K_PER_DOC):
        self.embedder = embedder
        self.conn = conn
        self.top_k_per_doc = top_k_per_doc

    @cached_property
    def _lexical(self) -> tuple[Bm25Index, list[tuple[str, int]]]:
        rows = load_chunk_texts(self.conn)
        return Bm25Index([text for _, _, text in rows]), [(f, i) for f, i, _ in rows]

    def retrieve(self, query: str) -> list[Passage]:
        dense = rank_all_per_document(self.conn, self.embedder.embed_query(query))
        bm25, keys = self._lexical
        words = dict(zip(keys, bm25.scores(query), strict=True))

        results = []
        for filename, passages in dense.items():
            by_meaning = [p.chunk_index for p in passages]
            by_words = sorted(by_meaning, key=lambda i: words.get((filename, i), 0.0), reverse=True)
            best = reciprocal_rank_fusion([by_meaning, by_words])[:self.top_k_per_doc]
            chosen = {p.chunk_index: p for p in passages}
            results += [chosen[i] for i in best]  # le score affiché reste le cosinus

        results.sort(key=lambda p: p.score, reverse=True)
        return results


class RerankingRetriever:
    """Enveloppe un retriever : ses `candidates` meilleurs passages par document
    sont relus par un cross-encodeur (le claim et le passage ENSEMBLE), qui
    garde les `top_k_per_doc` qui répondent le mieux.

    La recherche trouve la preuve parmi ses candidats sans bien la classer
    (scores d'embedding serrés dans un même article) ; le reranker la classe.
    Mesuré sur 44 citations (make eval-retrieval) : la preuve est dans les 2
    premiers passages de son document pour 37/44 avec hybrid + reranker,
    31/44 avec hybrid seul, 23/44 par le sens seul."""

    def __init__(self, base: Retriever, reranker: Reranker, top_k_per_doc: int = TOP_K_PER_DOC):
        self.base = base          # construit pour ramener `candidates` passages par document
        self.reranker = reranker
        self.top_k_per_doc = top_k_per_doc

    def retrieve(self, query: str) -> list[Passage]:
        by_doc: dict[str, list[Passage]] = {}
        for p in self.base.retrieve(query):
            by_doc.setdefault(p.filename, []).append(p)

        results = []
        for passages in by_doc.values():
            scores = self.reranker.scores(query, [p.text for p in passages])
            order = sorted(range(len(passages)), key=lambda j: scores[j], reverse=True)
            results += [passages[j] for j in order[:self.top_k_per_doc]]

        results.sort(key=lambda p: p.score, reverse=True)  # le score affiché reste le cosinus
        return results


def format_evidence(passages: list[Passage]) -> str:
    blocks = []
    for p in passages:
        blocks.append(f"[Source: {p.filename} | chunk #{p.chunk_index} | type: {p.source_type}]\n{p.text}")
    return "\n\n---\n\n".join(blocks)
