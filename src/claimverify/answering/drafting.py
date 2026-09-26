"""
Génération de réponse brouillon — Étape B
============================================

Boucle : question -> retrieval PAR DOCUMENT (chaque source du corpus a une
chance d'être représentée, voir components/store.py) -> génération d'une
réponse par le drafter (answering.drafter dans config.yaml), en citant les
sources utilisées. La clé API du fournisseur choisi se met dans .env.

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
from claimverify.config import add_db_url_argument
from claimverify.contracts import Draft, Passage
from claimverify.llm import LLM
from claimverify.settings import add_config_argument, load_settings


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
  [vectara-semantic-chunking-naacl2025.pdf].
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
    # Import local : factory importe ce module, l'importer en tête serait circulaire.
    from claimverify.factory import build_drafter, build_embedder, build_retriever

    parser = argparse.ArgumentParser()
    add_db_url_argument(parser)
    add_config_argument(parser)
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--save_to", type=str, default=None,
                         help="Chemin optionnel pour sauvegarder le brouillon en JSON "
                              "(entrée de decomposition --draft_file).")
    args = parser.parse_args()

    settings = load_settings(args.config)
    drafter = build_drafter(settings)

    conn = psycopg2.connect(args.db_url)
    retriever = build_retriever(settings.answering.retriever, build_embedder(settings), conn,
                                "answering.retriever")
    passages = retriever.retrieve(args.query)
    conn.close()

    docs_covered = sorted({p.filename for p in passages})
    print(f"\n{len(passages)} chunks récupérés depuis {len(docs_covered)} document(s) :")
    for doc in docs_covered:
        print(f"  - {doc}")

    print(f"\nGénération de la réponse brouillon ({settings.answering.drafter.model})...\n")
    draft = drafter.draft(args.query, passages)

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