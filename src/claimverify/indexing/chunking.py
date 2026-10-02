"""
Chunking — Document vers Chunk
================================

Taille fixe avec chevauchement (baseline volontairement simple), mesurée en
tokens DU MODÈLE D'EMBEDDING : sa limite (512 pour bge) compte ses propres
tokens, et un autre découpage (mots, tokenizer d'un LLM) donne d'autres
nombres. Un chunk trop long serait tronqué sans erreur : sa fin ne serait
jamais embeddée, alors que le LLM la lirait comme preuve.

Le texte d'un chunk est découpé dans le texte original, aux positions des
tokens : casse, ponctuation et retours à la ligne restent intacts. Une coupe
tombe toujours sur un blanc, jamais au milieu d'un mot.
"""

from typing import Protocol, runtime_checkable

from claimverify.contracts import Chunk, Document

CHUNK_SIZE_TOKENS = 400
CHUNK_OVERLAP_RATIO = 0.15  # 15%

Span = tuple[int, int]  # début et fin d'un token dans le texte (positions de caractères)


@runtime_checkable
class Tokenizer(Protocol):
    """Interface : où commence et finit chaque token d'un texte (sans tokens
    spéciaux). BgeEmbedder la fournit : on compte avec le modèle qui embeddera."""

    def token_spans(self, text: str) -> list[Span]: ...

    def max_tokens(self) -> int:
        """Tokens de texte que le modèle lit au plus (sa limite, moins ses tokens spéciaux)."""
        ...


@runtime_checkable
class Chunker(Protocol):
    """Interface : découpe des Documents en Chunks (sans embedding)."""

    def chunk(self, documents: list[Document]) -> list[Chunk]: ...


class FixedSizeChunker:
    """Implémentation : fenêtres de `chunk_size` tokens, avec chevauchement."""

    def __init__(self, tokenizer: Tokenizer, chunk_size: int = CHUNK_SIZE_TOKENS,
                 overlap_ratio: float = CHUNK_OVERLAP_RATIO):
        self.tokenizer = tokenizer
        self.chunk_size = chunk_size
        self.overlap_ratio = overlap_ratio

    def chunk(self, documents: list[Document]) -> list[Chunk]:
        # Vérifié avant de découper : au-delà, le modèle tronquerait chaque
        # chunk en silence, et sa fin ne serait jamais embeddée.
        limit = self.tokenizer.max_tokens()
        if self.chunk_size > limit:
            raise ValueError(f"chunk_size = {self.chunk_size} tokens, mais le modèle d'embedding "
                             f"n'en lit que {limit} par chunk : réduire indexing.chunker.chunk_size.")
        all_chunks = []
        for doc in documents:
            windows = token_windows(self.tokenizer.token_spans(doc.text),
                                    self.chunk_size, self.overlap_ratio)
            for i, (start, end, tokens) in enumerate(windows):
                all_chunks.append(Chunk(
                    chunk_id=f"{doc.doc_id}_{i:04d}",
                    doc_id=doc.doc_id,
                    filename=doc.filename,
                    source_type=doc.source_type,
                    chunk_index=i,
                    text=doc.text[start:end],
                    tokens=tokens,
                ))
        return all_chunks


def token_windows(spans: list[Span], chunk_size: int,
                  overlap_ratio: float) -> list[tuple[int, int, int]]:
    """Fenêtres (début, fin en caractères, nombre de tokens) d'au plus
    `chunk_size` tokens. Chaque fenêtre commence et finit sur une frontière
    de mot (un blanc entre deux tokens), sauf un "mot" plus long que
    `chunk_size` (une URL, une suite de chiffres), coupé à la limite."""
    n = len(spans)
    # Le token i commence un mot si un blanc le sépare du précédent.
    word_start = [i == 0 or spans[i][0] > spans[i - 1][1] for i in range(n)]
    overlap = int(chunk_size * overlap_ratio)

    windows, start = [], 0
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            # Reculer jusqu'au début d'un mot, pour ne pas le couper en deux.
            cut = next((j for j in range(end, start, -1) if word_start[j]), end)
            end = cut
        windows.append((spans[start][0], spans[end - 1][1], end - start))
        if end == n:
            break
        # La suivante reprend `overlap` tokens plus tôt, au début d'un mot ;
        # elle avance toujours, même si la fenêtre est plus courte que l'overlap.
        back = max(end - overlap, start + 1)
        start = next((j for j in range(back, start, -1) if word_start[j]), back)
    return windows
