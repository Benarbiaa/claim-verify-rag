"""
Génération de réponse brouillon — Étape B
============================================

Boucle : question -> retrieval PAR DOCUMENT (chaque source du corpus a une
chance d'être représentée, voir components/store.py) -> génération d'une
réponse via le LLM du rôle "draft" (voir llm.py), en citant les sources utilisées.

Pas encore de décomposition en claims ni de vérification à ce stade — on
valide seulement que la boucle "question -> réponse ancrée dans le corpus"
fonctionne, avant d'ajouter la couche agentique par-dessus.

Prérequis :
    pip install openai python-dotenv

    Variable dans le fichier .env :
    GROQ_API_KEY=...        (+ DRAFT_MODEL / DRAFT_BASE_URL optionnels, voir llm.py)

Usage (--db_url facultatif si DB_URL est dans .env, voir config.py) :
    python -m claimverify.answering.drafting \
        --query "Does semantic chunking improve retrieval performance?" --save_to draft.json

Le fichier sauvegardé est un Draft (voir contracts.py) : question, réponse et
passages utilisés, relisible par decomposition --draft_file.
"""

import argparse
from typing import Protocol, runtime_checkable

import psycopg2

from claimverify.answering.retrieval import format_evidence
from claimverify.components.embedding import embed_query, load_embedding_model
from claimverify.components.store import search_per_document
from claimverify.config import add_db_url_argument
from claimverify.contracts import Draft, Passage
from claimverify.llm import LLM, get_llm  # modèle du rôle "draft", voir llm.py

TOP_K_PER_DOC = 2  # top-k PAR document, pas top-k global — voir components/store.py


@runtime_checkable
class Drafter(Protocol):
    """Interface : rédige une réponse à la question à partir des passages."""

    def draft(self, question: str, passages: list[Passage]) -> Draft: ...


class LLMDrafter:
    """Implémentation : un LLM (rôle "draft" de llm.py) avec SYSTEM_PROMPT ci-dessous."""

    def __init__(self, llm: LLM):
        self.llm = llm

    def draft(self, question: str, passages: list[Passage]) -> Draft:
        return generate_draft_answer(self.llm, question, passages)

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


def generate_draft_answer(llm: LLM, query: str, passages: list[Passage]) -> Draft:
    user_message = f"""Source passages (from multiple documents, treat each source independently
and note any disagreement between them):

{format_evidence(passages)}

---

Question: {query}
"""
    answer = llm.chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ])
    return Draft(question=query, text=answer, passages=passages)


def main():
    parser = argparse.ArgumentParser()
    add_db_url_argument(parser)
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--top_k_per_doc", type=int, default=TOP_K_PER_DOC)
    parser.add_argument("--save_to", type=str, default=None,
                         help="Chemin optionnel pour sauvegarder le brouillon en JSON "
                              "(entrée de decomposition --draft_file).")
    args = parser.parse_args()

    llm = get_llm("draft")

    print("Chargement du modèle d'embedding...")
    embed_model = load_embedding_model(device="cuda")  # "cpu" si pas de GPU

    conn = psycopg2.connect(args.db_url)
    query_embedding = embed_query(embed_model, args.query)
    passages = search_per_document(conn, query_embedding, args.top_k_per_doc)
    conn.close()

    docs_covered = sorted({p.filename for p in passages})
    print(f"\n{len(passages)} chunks récupérés depuis {len(docs_covered)} document(s) :")
    for doc in docs_covered:
        print(f"  - {doc}")

    print(f"\nGénération de la réponse brouillon ({llm.describe()})...\n")
    draft = generate_draft_answer(llm, args.query, passages)

    print("=" * 100)
    print(f"QUESTION : {args.query}")
    print("=" * 100)
    print(draft.text)
    print("=" * 100)

    if args.save_to:
        with open(args.save_to, "w", encoding="utf-8") as f:
            f.write(draft.model_dump_json(indent=2))
        print(f"\nBrouillon sauvegardé dans {args.save_to}")


if __name__ == "__main__":
    main()