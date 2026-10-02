"""
Embedding — composant partagé par les deux pipelines
======================================================

L'indexation embedde les chunks, la réponse embedde les questions et les
claims : les deux DOIVENT utiliser le même modèle, sinon les vecteurs ne
sont plus comparables et le retrieval se dégrade sans erreur visible.
"""

from functools import cached_property
from typing import Protocol, runtime_checkable

from sentence_transformers import SentenceTransformer

from claimverify.contracts import Chunk

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
EMBEDDING_DIM = 768  # dimension de sortie de bge-base-en-v1.5


@runtime_checkable
class Embedder(Protocol):
    """Interface : transforme du texte en vecteurs comparables entre eux."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Pour les passages à indexer."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Pour une question ou un claim à rechercher."""
        ...


class BgeEmbedder:
    """Implémentation : bge-base-en-v1.5 en local (sentence-transformers)."""

    def __init__(self, model_name: str = EMBEDDING_MODEL, device: str = "cuda"):
        self.model_name = model_name
        self.device = device

    @cached_property
    def model(self) -> SentenceTransformer:
        # Chargé au premier usage seulement : créer l'objet ne coûte rien.
        return SentenceTransformer(self.model_name, device=self.device)

    def token_spans(self, text: str) -> list[tuple[int, int]]:
        """Positions de chaque token de CE modèle dans le texte : le chunker
        mesure avec le tokenizer qui lira les chunks (voir chunking.py)."""
        return self.model.tokenizer(text, add_special_tokens=False,
                                    return_offsets_mapping=True)["offset_mapping"]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, batch_size=32, show_progress_bar=True,
                                       normalize_embeddings=True)
        return [e.tolist() for e in embeddings]

    def embed_query(self, text: str) -> list[float]:
        return embed_query(self.model, text)


def embed_query(model: SentenceTransformer, text: str):
    instructed = f"Represent this sentence for searching relevant passages: {text}"
    return model.encode(instructed, normalize_embeddings=True).tolist()


def embed_chunks(chunks: list[Chunk], embedder: Embedder) -> list[Chunk]:
    """Retourne de NOUVEAUX chunks avec leur embedding : la liste reçue n'est pas modifiée."""
    embeddings = embedder.embed_texts([c.text for c in chunks])
    return [
        chunk.model_copy(update={"embedding": embedding})
        for chunk, embedding in zip(chunks, embeddings)
    ]
