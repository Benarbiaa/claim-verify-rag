"""
Embedding — a component shared by both pipelines
================================================

Indexing embeds the chunks, answering embeds the questions and the claims:
both MUST use the same model, or the vectors are no longer comparable and
retrieval degrades with no visible error.
"""

from functools import cached_property
from typing import Protocol, runtime_checkable

from sentence_transformers import SentenceTransformer

from claimverify.contracts import Chunk

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
EMBEDDING_DIM = 768  # output dimension of bge-base-en-v1.5


@runtime_checkable
class Embedder(Protocol):
    """Interface: turns text into vectors comparable with each other."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """For the passages to index."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """For a question or a claim to search for."""
        ...


class BgeEmbedder:
    """Implementation: bge-base-en-v1.5, run locally (sentence-transformers)."""

    def __init__(self, model_name: str = EMBEDDING_MODEL, device: str = "cuda"):
        self.model_name = model_name
        self.device = device

    @cached_property
    def model(self) -> SentenceTransformer:
        # Loaded on first use only: creating the object costs nothing.
        return SentenceTransformer(self.model_name, device=self.device)

    def token_spans(self, text: str) -> list[tuple[int, int]]:
        """Where each token of THIS model sits in the text: the chunker measures
        with the tokenizer that will read the chunks (see chunking.py)."""
        # verbose=False: a whole document exceeds the model's limit, which is
        # expected here (it is measured to be cut, not embedded).
        return self.model.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True,
                                    verbose=False)["offset_mapping"]

    def max_tokens(self) -> int:
        # The model's limit (512 positions for bge) minus what it adds around
        # the text itself ([CLS] and [SEP]).
        return self.model.max_seq_length - self.model.tokenizer.num_special_tokens_to_add()

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
    """Returns NEW chunks with their embedding: the list received is not modified."""
    embeddings = embedder.embed_texts([c.text for c in chunks])
    return [
        chunk.model_copy(update={"embedding": embedding})
        for chunk, embedding in zip(chunks, embeddings)
    ]
