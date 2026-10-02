import pytest

from claimverify.components import store
from claimverify.components.store import replace_chunks
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


def chunk(embedding=None):
    return Chunk(chunk_id="abc123_0000", doc_id="abc123", filename="a.pdf",
                 source_type="peer_reviewed_paper", chunk_index=0, text="x", embedding=embedding)


def test_store_refuses_chunks_without_embedding_before_touching_the_database():
    # conn=None: the check must fail first, so no database is ever used
    with pytest.raises(ValueError, match="sans embedding"):
        replace_chunks(None, [chunk()])


def test_store_refuses_an_empty_list_instead_of_emptying_the_table():
    with pytest.raises(ValueError, match="Aucun chunk"):
        replace_chunks(None, [])


class RecordingConnection:
    """Records the SQL sent and the commits, in order."""

    def __init__(self):
        self.log = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.log.append(sql.split()[0].upper())

    def commit(self):
        self.log.append("COMMIT")


def test_store_replaces_the_whole_table_in_one_transaction(monkeypatch):
    # execute_values needs a real psycopg2 cursor: record its INSERT instead
    monkeypatch.setattr(store, "execute_values",
                        lambda cur, sql, rows: cur.log.append(sql.split()[0].upper()))
    conn = RecordingConnection()
    replace_chunks(conn, [chunk(embedding=[1.0, 0.0])])

    # old rows go first, and nothing is committed between the delete and the insert
    assert conn.log == ["DELETE", "INSERT", "COMMIT"]
