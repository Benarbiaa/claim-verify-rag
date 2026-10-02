from itertools import pairwise

import pytest

from claimverify.components import store
from claimverify.components.store import replace_chunks
from claimverify.contracts import Chunk, Document
from claimverify.indexing.chunking import FixedSizeChunker, Tokenizer, token_windows
from fakes import PieceTokenizer, WordTokenizer


def doc(text: str) -> Document:
    return Document(doc_id="abc123", filename="a.pdf", source_type="peer_reviewed_paper", text=text)


def words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def test_the_fakes_are_tokenizers():
    assert isinstance(WordTokenizer(), Tokenizer) and isinstance(PieceTokenizer(), Tokenizer)


def test_short_text_is_a_single_chunk_kept_exactly_as_written():
    text = "Semantic Chunking,\nrevisited:  a Study."
    [c] = FixedSizeChunker(WordTokenizer(), chunk_size=400).chunk([doc(text)])
    assert c.text == text and c.tokens == 5


def test_windows_respect_size_and_overlap_and_lose_nothing():
    text = words(1000)
    chunks = FixedSizeChunker(WordTokenizer(), chunk_size=100, overlap_ratio=0.2).chunk([doc(text)])
    split = [c.text.split() for c in chunks]

    assert all(len(c) <= 100 for c in split)
    assert [c.tokens for c in chunks] == [len(c) for c in split]
    # consecutive chunks share exactly `overlap` tokens
    for prev, nxt in pairwise(split):
        assert prev[-20:] == nxt[:20]
    # nothing is lost at either end
    assert split[0][0] == "w0" and split[-1][-1] == "w999"


def test_a_cut_never_falls_inside_a_word():
    # "abcdefg" is 3 pieces (abc|def|g): a blind cut at 3 tokens would give "abc abcdef"
    text = "abc abcdefg abc abcdefg abc"
    chunks = FixedSizeChunker(PieceTokenizer(), chunk_size=3, overlap_ratio=0.0).chunk([doc(text)])

    assert [c.text for c in chunks] == ["abc", "abcdefg", "abc", "abcdefg", "abc"]
    assert all(c.tokens <= 3 for c in chunks)


def test_a_word_longer_than_a_chunk_is_cut_at_the_limit():
    # a URL or a long number has no blank to cut at: the limit wins
    [first, second] = token_windows(PieceTokenizer().token_spans("x" * 18), chunk_size=4, overlap_ratio=0.0)
    assert first == (0, 12, 4) and second == (12, 18, 2)


def test_every_chunk_is_a_slice_of_the_original_text():
    text = "First Line,\nsecond line.\n\n" * 40
    chunks = FixedSizeChunker(PieceTokenizer(), chunk_size=25, overlap_ratio=0.15).chunk([doc(text)])
    assert len(chunks) > 1 and all(c.text in text for c in chunks)


def test_a_chunk_size_above_the_models_limit_is_refused():
    # 512 would become 514 with the model's own [CLS] and [SEP]: silently truncated
    chunker = FixedSizeChunker(WordTokenizer(), chunk_size=512)
    with pytest.raises(ValueError, match="n'en lit que 510"):
        chunker.chunk([doc(words(10))])


def test_empty_text_gives_no_chunks():
    assert FixedSizeChunker(WordTokenizer()).chunk([doc("")]) == []


def test_chunks_get_ids_and_metadata_but_no_embedding():
    chunks = FixedSizeChunker(WordTokenizer(), chunk_size=400).chunk([doc(words(1000))])

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
