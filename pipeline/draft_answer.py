"""
Génération de réponse brouillon — Étape B
============================================

Boucle : question -> retrieval PAR DOCUMENT (chaque source du corpus a une
chance d'être représentée, voir retrieval_utils.py) -> génération d'une
réponse via Gemini, en citant les sources utilisées.

Pas encore de décomposition en claims ni de vérification à ce stade — on
valide seulement que la boucle "question -> réponse ancrée dans le corpus"
fonctionne, avant d'ajouter la couche agentique par-dessus.

Prérequis :
    pip install openai python-dotenv

    Variable dans le fichier .env :
    GROQ_API_KEY=...

Usage :
    python draft_answer.py --db_url postgresql://rag_user:admin@localhost:5432/ragdb \
        --query "Does semantic chunking improve retrieval performance?"
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.retrieval_utils import embed_query, format_evidence, load_embedding_model, search_per_document

load_dotenv()  # doit être appelé AVANT la lecture de LLM_MODEL ci-dessous

# LLM_MODEL est lu depuis .env (LLM_MODEL=...), avec cette valeur par défaut
# si non définie. Garder ça configurable évite d'éditer le code à chaque
# dépréciation de modèle côté Groq (déjà arrivé deux fois sur ce projet).
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")  # modèle Groq utilisé pour la génération
TOP_K_PER_DOC = 2  # top-k PAR document, pas top-k global — voir retrieval_utils.py

SYSTEM_PROMPT = """You are an assistant that answers questions ONLY using the provided source
passages. Strict rules:
- IMPORTANT: Always answer in English, regardless of the language of the question. The source
  corpus is in English, and downstream retrieval steps depend on embeddings staying in English —
  do not translate your answer into another language.
- Only use information present in the provided passages.
- If the passages don't fully answer the question, say so explicitly.
- The passages may come from MULTIPLE different sources/papers that do not necessarily agree with
  each other. If passages from different sources seem to contradict each other, state that clearly
  and explain the disagreement instead of arbitrarily picking a side or ignoring one source.
- Cite the source of each claim by naming the document in brackets, e.g.
  [Is Semantic Chunking Worth the Computational Cost?.pdf].
- Be concise and factual. Do not add knowledge beyond what's in the provided passages.
"""


def generate_draft_answer(client: OpenAI, query: str, context: str) -> str:
    user_message = f"""Source passages (from multiple documents, treat each source independently
and note any disagreement between them):

{context}

---

Question: {query}
"""
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_url", type=str, required=True)
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--top_k_per_doc", type=int, default=TOP_K_PER_DOC)
    parser.add_argument("--save_to", type=str, default=None,
                         help="Chemin optionnel pour sauvegarder la réponse brouillon en texte brut "
                              "(pratique pour l'enchaîner directement avec decompose_claims.py).")
    args = parser.parse_args()

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("La variable d'environnement GROQ_API_KEY n'est pas définie.")

    print("Chargement du modèle d'embedding...")
    embed_model = load_embedding_model(device="cuda")  # "cpu" si pas de GPU

    conn = psycopg2.connect(args.db_url)
    query_embedding = embed_query(embed_model, args.query)
    results = search_per_document(conn, query_embedding, args.top_k_per_doc)
    conn.close()

    docs_covered = sorted(set(r[0] for r in results))
    print(f"\n{len(results)} chunks récupérés depuis {len(docs_covered)} document(s) :")
    for doc in docs_covered:
        print(f"  - {doc}")

    context = format_evidence(results)

    print("\nGénération de la réponse brouillon...\n")
    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    answer = generate_draft_answer(client, args.query, context)

    print("=" * 100)
    print(f"QUESTION : {args.query}")
    print("=" * 100)
    print(answer)
    print("=" * 100)

    if args.save_to:
        with open(args.save_to, "w", encoding="utf-8") as f:
            f.write(answer)
        print(f"\nRéponse sauvegardée dans {args.save_to}")


if __name__ == "__main__":
    main()