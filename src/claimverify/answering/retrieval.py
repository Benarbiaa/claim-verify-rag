"""
Retrieval côté réponse — question vers Passages
=================================================

La recherche elle-même (SQL pgvector) est dans components/store.py, et
l'embedding de la requête dans components/embedding.py. Le retriever les
reçoit tous les deux : il ne crée ni modèle ni connexion.
"""

from typing import Protocol, runtime_checkable

from claimverify.components.embedding import Embedder
from claimverify.components.store import TOP_K_PER_DOC, search_per_document
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


def format_evidence(passages: list[Passage]) -> str:
    blocks = []
    for p in passages:
        blocks.append(f"[Source: {p.filename} | chunk #{p.chunk_index} | type: {p.source_type}]\n{p.text}")
    return "\n\n---\n\n".join(blocks)
