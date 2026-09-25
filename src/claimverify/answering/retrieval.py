"""
Retrieval côté réponse — mise en forme des passages pour les prompts
======================================================================

La recherche elle-même (SQL pgvector) est dans components/store.py, et
l'embedding de la requête dans components/embedding.py.
"""

from claimverify.contracts import Passage


def format_evidence(passages: list[Passage]) -> str:
    blocks = []
    for p in passages:
        blocks.append(f"[Source: {p.filename} | chunk #{p.chunk_index} | type: {p.source_type}]\n{p.text}")
    return "\n\n---\n\n".join(blocks)