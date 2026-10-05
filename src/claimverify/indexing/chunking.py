"""
Chunking — Document to Chunk
============================

Fixed size with overlap (a deliberately simple baseline), measured in tokens
OF THE EMBEDDING MODEL: its limit (512 for bge) counts its own tokens, and
another unit (words, an LLM's tokenizer) gives other numbers. A chunk that is
too long would be truncated with no error: its end would never be embedded,
while the LLM would still read it as evidence.

A chunk's text is cut from the original text, at the tokens' positions: case,
punctuation and line breaks stay intact. A cut always falls on a blank, never
in the middle of a word.
"""

from typing import Protocol, runtime_checkable

from claimverify.contracts import Chunk, Document

CHUNK_SIZE_TOKENS = 400
CHUNK_OVERLAP_RATIO = 0.15  # 15%

Span = tuple[int, int]  # start and end of a token in the text (character positions)


@runtime_checkable
class Tokenizer(Protocol):
    """Interface: where each token of a text starts and ends (without special
    tokens). BgeEmbedder provides it: counting is done with the model that will embed."""

    def token_spans(self, text: str) -> list[Span]: ...

    def max_tokens(self) -> int:
        """Text tokens the model reads at most (its limit, minus its special tokens)."""
        ...


@runtime_checkable
class Chunker(Protocol):
    """Interface: cuts Documents into Chunks (without embedding)."""

    def chunk(self, documents: list[Document]) -> list[Chunk]: ...


class FixedSizeChunker:
    """Implementation: windows of `chunk_size` tokens, with overlap."""

    def __init__(self, tokenizer: Tokenizer, chunk_size: int = CHUNK_SIZE_TOKENS,
                 overlap_ratio: float = CHUNK_OVERLAP_RATIO):
        self.tokenizer = tokenizer
        self.chunk_size = chunk_size
        self.overlap_ratio = overlap_ratio

    def chunk(self, documents: list[Document]) -> list[Chunk]:
        # Checked before cutting: beyond it, the model would silently truncate
        # every chunk, and its end would never be embedded.
        limit = self.tokenizer.max_tokens()
        if self.chunk_size > limit:
            raise ValueError(f"chunk_size = {self.chunk_size} tokens, but the embedding model "
                             f"only reads {limit} per chunk: lower indexing.chunker.chunk_size.")
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
    """Windows (start, end in characters, number of tokens) of at most
    `chunk_size` tokens. Each window starts and ends on a word boundary (a
    blank between two tokens), except a "word" longer than `chunk_size` (a
    URL, a long number), cut at the limit."""
    n = len(spans)
    # Token i starts a word if a blank separates it from the previous one.
    word_start = [i == 0 or spans[i][0] > spans[i - 1][1] for i in range(n)]
    overlap = int(chunk_size * overlap_ratio)

    windows, start = [], 0
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            # Step back to the start of a word, so as not to cut it in two.
            cut = next((j for j in range(end, start, -1) if word_start[j]), end)
            end = cut
        windows.append((spans[start][0], spans[end - 1][1], end - start))
        if end == n:
            break
        # The next one starts `overlap` tokens earlier, at the start of a word;
        # it always moves forward, even if the window is shorter than the overlap.
        back = max(end - overlap, start + 1)
        start = next((j for j in range(back, start, -1) if word_start[j]), back)
    return windows
