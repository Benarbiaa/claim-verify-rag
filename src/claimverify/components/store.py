"""
Stockage vectoriel pgvector — composant partagé par les deux pipelines
========================================================================

L'indexation écrit les chunks (setup_db, replace_chunks), la réponse les
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
        # Pas d'index vectoriel : recherche exacte. À quelques centaines de
        # chunks, comparer la requête à chaque ligne prend quelques ms.
        # L'ancien index IVFFlat (créé sur une table vide, 1 seule liste
        # parcourue) faisait disparaître des documents entiers de
        # search_per_document, le filtre filename étant appliqué après la
        # recherche approximative. On le supprime des bases existantes.
        cur.execute("DROP INDEX IF EXISTS chunks_embedding_idx;")
    conn.commit()


def replace_chunks(conn, chunks: list[Chunk]):
    """Remplace TOUT le contenu de la table par ces chunks : après une
    indexation, la table contient exactement le corpus indexé. Sinon les
    lignes d'un fichier retiré ou renommé, ou les derniers chunks d'un
    document qui en produit moins qu'avant, resteraient cherchables."""
    # Vérifiés avant de toucher la base. Liste vide : mauvais --corpus_dir
    # ou dossier vide, on viderait la table pour rien.
    if not chunks:
        raise ValueError("Aucun chunk à stocker : vérifier --corpus_dir. La table n'est pas modifiée.")
    # Un chunk sans embedding vient d'une étape d'embedding sautée ou
    # défaillante, c'est elle qu'il faut signaler.
    missing = [c.chunk_id for c in chunks if c.embedding is None]
    if missing:
        raise ValueError(
            f"{len(missing)} chunk(s) sans embedding (ex. {missing[0]}) : "
            "lancer embed_chunks avant replace_chunks."
        )

    rows = [
        (c.chunk_id, c.doc_id, c.filename, c.source_type, c.chunk_index, c.text, c.embedding)
        for c in chunks
    ]
    # DELETE et INSERT dans une seule transaction (un seul commit) : en cas
    # d'échec, Postgres annule tout et l'ancienne table reste intacte ; une
    # recherche pendant l'indexation voit l'ancienne table complète.
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


def rank_all_per_document(conn, query_embedding) -> dict[str, list[Passage]]:
    """TOUS les chunks de chaque document, du plus au moins similaire (cosinus).
    Sert à la recherche hybride, qui fusionne ce classement avec celui de BM25 :
    il lui faut le classement complet, pas seulement le top-k. Sans LIMIT :
    raisonnable à cette taille de corpus (quelques centaines de chunks)."""
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
    """(filename, chunk_index, texte) de chaque chunk : de quoi construire l'index BM25."""
    with conn.cursor() as cur:
        cur.execute("SELECT filename, chunk_index, text FROM chunks ORDER BY filename, chunk_index;")
        return cur.fetchall()


def _to_passage(row) -> Passage:
    """Convertit une ligne SQL (filename, source_type, chunk_index, text, score)."""
    filename, source_type, chunk_index, text, score = row
    return Passage(filename=filename, source_type=source_type, chunk_index=chunk_index,
                   text=text, score=score)

