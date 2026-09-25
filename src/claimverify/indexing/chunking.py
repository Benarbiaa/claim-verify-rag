"""
Chunking — Document vers Chunk
================================

Taille fixe avec chevauchement (baseline volontairement simple).
"""

import re

from claimverify.contracts import Chunk, Document

CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_RATIO = 0.15  # 15%


def simple_tokenize(text: str) -> list[str]:
    # Découpage naïf par mots ; suffisant pour une baseline de chunking par
    # nombre de tokens approximatif. À remplacer par un vrai tokenizer
    # (ex. tiktoken) si besoin de précision.
    return re.findall(r"\S+", text)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_TOKENS,
               overlap_ratio: float = CHUNK_OVERLAP_RATIO) -> list[str]:
    words = simple_tokenize(text)
    overlap = int(chunk_size * overlap_ratio)
    step = chunk_size - overlap

    chunks = []
    for start in range(0, len(words), step):
        chunk_words = words[start:start + chunk_size]
        if not chunk_words:
            break
        chunks.append(" ".join(chunk_words))
        if start + chunk_size >= len(words):
            break
    return chunks


def build_chunks(documents: list[Document]) -> list[Chunk]:
    """Découpe chaque document en Chunk (sans embedding : c'est l'étape suivante)."""
    all_chunks = []
    for doc in documents:
        pieces = chunk_text(doc.text)
        for i, piece in enumerate(pieces):
            all_chunks.append(Chunk(
                chunk_id=f"{doc.doc_id}_{i:04d}",
                doc_id=doc.doc_id,
                filename=doc.filename,
                source_type=doc.source_type,
                chunk_index=i,
                text=piece,
            ))
    return all_chunks
