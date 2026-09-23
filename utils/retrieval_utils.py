"""
Module partagé de retrieval — utilisé par draft_answer.py, verify_claims.py,
et query_check.py.

Centralise la logique d'embedding de requête et de recherche par document,
pour garantir que TOUTE étape du pipeline qui interroge le corpus (pas
seulement la vérification) ait une chance de voir chaque source, plutôt que
de laisser un document dominer systématiquement le retrieval global à cause
de scores de similarité plus élevés.
"""

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
TOP_K_PER_DOC = 2


def load_embedding_model(device: str = "cuda") -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL, device=device)


def embed_query(model: SentenceTransformer, text: str):
    instructed = f"Represent this sentence for searching relevant passages: {text}"
    return model.encode(instructed, normalize_embeddings=True).tolist()


def search_global(conn, query_embedding, top_k: int = 5):
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
        return cur.fetchall()


def search_per_document(conn, query_embedding, top_k_per_doc: int = TOP_K_PER_DOC):
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
            all_results.extend(cur.fetchall())

        all_results.sort(key=lambda row: row[4], reverse=True)
        return all_results


def format_evidence(results) -> str:
    blocks = []
    for filename, source_type, chunk_index, text, score in results:
        blocks.append(f"[Source: {filename} | chunk #{chunk_index} | type: {source_type}]\n{text}")
    return "\n\n---\n\n".join(blocks)