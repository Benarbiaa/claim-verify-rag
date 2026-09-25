import pytest

from claimverify.components.store import store_chunks
from claimverify.contracts import Chunk, Document
from claimverify.indexing.chunking import build_chunks, chunk_text


def test_short_text_is_single_chunk():
    text = " ".join(f"w{i}" for i in range(100))
    chunks = chunk_text(text, chunk_size=512, overlap_ratio=0.15)
    assert chunks == [text]


def test_chunks_respect_size_and_overlap():
    words = [f"w{i}" for i in range(1000)]
    chunks = chunk_text(" ".join(words), chunk_size=100, overlap_ratio=0.2)
    split = [c.split() for c in chunks]

    assert all(len(c) <= 100 for c in split)
    # consecutive chunks share exactly `overlap` words
    for prev, nxt in zip(split, split[1:]):
        assert prev[-20:] == nxt[:20]
    # nothing is lost at the end
    assert split[-1][-1] == "w999"


def test_empty_text_gives_no_chunks():
    assert chunk_text("") == []


def test_build_chunks_turns_documents_into_chunks():
    text = " ".join(f"w{i}" for i in range(1000))
    doc = Document(doc_id="abc123", filename="a.pdf", source_type="peer_reviewed_paper", text=text)
    chunks = build_chunks([doc])

    assert all(isinstance(c, Chunk) for c in chunks)
    assert [c.chunk_id for c in chunks] == ["abc123_0000", "abc123_0001", "abc123_0002"]
    assert all(c.filename == "a.pdf" and c.embedding is None for c in chunks)


def test_store_refuses_chunks_without_embedding_before_touching_the_database():
    chunk = Chunk(chunk_id="abc123_0000", doc_id="abc123", filename="a.pdf",
                  source_type="peer_reviewed_paper", chunk_index=0, text="x")
    # conn=None: the check must fail first, so no database is ever used
    with pytest.raises(ValueError, match="sans embedding"):
        store_chunks(None, [chunk])
