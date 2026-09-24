from claimverify.ingest import chunk_text


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
