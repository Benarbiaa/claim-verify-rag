"""
Stockage vectoriel pgvector — composant partagé par les deux pipelines
========================================================================

L'indexation écrit les chunks (setup_db, store_chunks), la réponse les
recherche (search_global, search_per_document). Tout le SQL est ici :
changer de base vectorielle ne toucherait que ce module.

Prérequis : Postgres avec l'extension pgvector (CREATE EXTENSION IF NOT EXISTS vector;).
"""

from psycopg2.extras import execute_values

from claimverify.components.embedding import EMBEDDING_DIM
from claimverify.contracts import Chunk, Passage

TOP_K_PER_DOC = 2


# ---------------------------------------------------------------------------
# Écriture (pipeline d'indexation)
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
        # Index approximatif pour la recherche par similarité (IVFFlat).
        # À créer après avoir inséré des données pour de meilleures perfs
        # (nécessite un minimum de lignes pour être efficace, mais fonctionne
        # aussi bien pour un petit corpus de test).
        cur.execute("""
            CREATE INDEX IF NOT EXISTS chunks_embedding_idx
            ON chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 10);
        """)
    conn.commit()


def store_chunks(conn, chunks: list[Chunk]):
    # Vérifié avant de toucher la base : un chunk sans embedding vient d'une
    # étape d'embedding sautée ou défaillante, c'est elle qu'il faut signaler.
    missing = [c.chunk_id for c in chunks if c.embedding is None]
    if missing:
        raise ValueError(
            f"{len(missing)} chunk(s) sans embedding (ex. {missing[0]}) : "
            "lancer embed_chunks avant store_chunks."
        )

    rows = [
        (c.chunk_id, c.doc_id, c.filename, c.source_type, c.chunk_index, c.text, c.embedding)
        for c in chunks
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO chunks (chunk_id, doc_id, filename, source_type, chunk_index, text, embedding)
            VALUES %s
            ON CONFLICT (chunk_id) DO UPDATE SET
                text = EXCLUDED.text,
                embedding = EXCLUDED.embedding;
            """,
            rows,
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Recherche (pipeline de réponse)
# ---------------------------------------------------------------------------

def search_global(conn, query_embedding, top_k: int = 5) -> list[Passage]:
    """Recherche globale (top-k toutes sources confondues). Risque : un
    document dominant peut monopoliser les résultats et masquer des sources
    contradictoires pertinentes mais moins bien classées globalement. Utile
    pour comparaison/debug (voir query_check.py --per_document), mais ne
    doit PAS être utilisé pour la génération de réponse ni la vérification
    de claims — voir search_per_document ci-dessous."""
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
    """Récupère le top-k pour CHAQUE document du corpus plutôt qu'un top-k
    global. Garantit que chaque source a une chance d'être représentée,
    même si un document domine systématiquement le score de similarité
    pour une requête donnée (ex. Vectara vs LumberChunker sur les questions
    de chunking sémantique)."""
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


def _to_passage(row) -> Passage:
    """Convertit une ligne SQL (filename, source_type, chunk_index, text, score)."""
    filename, source_type, chunk_index, text, score = row
    return Passage(filename=filename, source_type=source_type, chunk_index=chunk_index,
                   text=text, score=score)

