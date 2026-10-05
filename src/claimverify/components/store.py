"""
pgvector storage — a component shared by both pipelines
=======================================================

Indexing writes the chunks (setup_db, replace_chunks), answering searches them
(search_per_document, rank_all_per_document, search_global). All the SQL is
here: switching vector databases would only touch this module.

Requires: Postgres with the pgvector extension (CREATE EXTENSION IF NOT EXISTS vector;).
"""

from psycopg2.extras import execute_values

from claimverify.components.embedding import EMBEDDING_DIM
from claimverify.contracts import Chunk, Passage

TOP_K_PER_DOC = 2


# ---------------------------------------------------------------------------
# Writing (indexing pipeline)
# ---------------------------------------------------------------------------

def setup_db(conn):
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                source_type TEXT NOT NULL,
                chunk_index INT NOT NULL,
                text TEXT NOT NULL,
                embedding VECTOR({EMBEDDING_DIM})
            );
        """)
        # No vector index: exact search. With a few hundred chunks, comparing
        # the query with every row takes a few ms. The former IVFFlat index
        # (built on an empty table, searching a single list) made whole
        # documents disappear from search_per_document, since the filename
        # filter applied after the approximate search. Existing databases
        # get it dropped.
        cur.execute("DROP INDEX IF EXISTS chunks_embedding_idx;")
    conn.commit()


def replace_chunks(conn, chunks: list[Chunk]):
    """Replaces ALL the table's content with these chunks: after an
    ingest, the table holds exactly the corpus just indexed. Otherwise the
    rows of a removed or renamed file, or the last chunks of a document that
    now yields fewer, would stay searchable."""
    # Checked before touching the database. An empty list: a wrong
    # --corpus_dir or an empty folder, which would empty the table for nothing.
    if not chunks:
        raise ValueError("No chunk to store: check --corpus_dir. The table is not modified.")
    # A chunk without an embedding comes from a skipped or failed embedding
    # step: that is what must be reported.
    missing = [c.chunk_id for c in chunks if c.embedding is None]
    if missing:
        raise ValueError(
            f"{len(missing)} chunk(s) without an embedding (e.g. {missing[0]}): "
            "run embed_chunks before replace_chunks."
        )

    rows = [
        (c.chunk_id, c.doc_id, c.filename, c.source_type, c.chunk_index, c.text, c.embedding)
        for c in chunks
    ]
    # DELETE and INSERT in a single transaction (one commit): on failure,
    # Postgres rolls everything back and the old table stays intact; a search
    # during the ingest sees the complete old table.
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chunks;")
        execute_values(
            cur,
            """
            INSERT INTO chunks (chunk_id, doc_id, filename, source_type, chunk_index, text, embedding)
            VALUES %s;
            """,
            rows,
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Searching (answering pipeline)
# ---------------------------------------------------------------------------

def search_global(conn, query_embedding, top_k: int = 5) -> list[Passage]:
    """Global search (top-k across all sources). Risk: a dominant document can
    take every slot and hide relevant contradicting sources that rank lower
    overall. Useful to compare and debug (see query_check.py without
    --per_document), but NOT to be used for drafting or claim verification:
    see search_per_document below."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT filename, source_type, chunk_index, text,
                   1 - (embedding <=> %s::vector) AS cosine_similarity
            FROM chunks
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
            """,
            (query_embedding, query_embedding, top_k),
        )
        return [_to_passage(row) for row in cur.fetchall()]


def search_per_document(conn, query_embedding,
                        top_k_per_doc: int = TOP_K_PER_DOC) -> list[Passage]:
    """Fetches the top-k of EACH document of the corpus instead of a global
    top-k. Guarantees that every source gets a chance to be represented, even
    if one document always dominates the similarity score for a query (e.g.
    Vectara vs LumberChunker on semantic chunking questions)."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT filename FROM chunks;")
        filenames = [row[0] for row in cur.fetchall()]

        all_results = []
        for filename in filenames:
            cur.execute(
                """
                SELECT filename, source_type, chunk_index, text,
                       1 - (embedding <=> %s::vector) AS cosine_similarity
                FROM chunks
                WHERE filename = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """,
                (query_embedding, filename, query_embedding, top_k_per_doc),
            )
            all_results.extend(_to_passage(row) for row in cur.fetchall())

        all_results.sort(key=lambda p: p.score, reverse=True)
        return all_results


def rank_all_per_document(conn, query_embedding) -> dict[str, list[Passage]]:
    """ALL the chunks of each document, from most to least similar (cosine).
    Used by the hybrid search, which merges this ranking with BM25's: it needs
    the full ranking, not just the top-k. No LIMIT: reasonable at this corpus
    size (a few hundred chunks)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT filename, source_type, chunk_index, text,
                   1 - (embedding <=> %s::vector) AS cosine_similarity
            FROM chunks
            ORDER BY filename, embedding <=> %s::vector;
            """,
            (query_embedding, query_embedding),
        )
        ranked: dict[str, list[Passage]] = {}
        for row in cur.fetchall():
            passage = _to_passage(row)
            ranked.setdefault(passage.filename, []).append(passage)
        return ranked


def load_chunk_texts(conn) -> list[tuple[str, int, str]]:
    """(filename, chunk_index, text) of each chunk: what the BM25 index is built from."""
    with conn.cursor() as cur:
        cur.execute("SELECT filename, chunk_index, text FROM chunks ORDER BY filename, chunk_index;")
        return cur.fetchall()


def _to_passage(row) -> Passage:
    """Converts an SQL row (filename, source_type, chunk_index, text, score)."""
    filename, source_type, chunk_index, text, score = row
    return Passage(filename=filename, source_type=source_type, chunk_index=chunk_index,
                   text=text, score=score)

