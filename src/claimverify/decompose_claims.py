"""
Décomposition en claims atomiques — Étape C
==============================================

Prend une réponse brouillon (texte généré à l'étape B) et la décompose en
une liste de claims atomiques, indépendants et vérifiables individuellement.

Aucun retrieval ici : c'est une transformation de texte pure, via un second
appel LLM dédié à cette seule tâche (séparé de la génération de la réponse,
pour garder chaque étape testable indépendamment).

Prérequis :
    pip install openai python-dotenv

Usage (en important la fonction depuis un autre script) :
    from claimverify.decompose_claims import decompose_into_claims
    from claimverify.llm import get_llm
    claims = decompose_into_claims(get_llm("decompose"), draft_answer_text)

Usage (en standalone, pour tester sur un texte donné) :
    python -m claimverify.decompose_claims --answer_file draft_answer_output.txt
"""

import argparse
import json

from claimverify.llm import LLM, get_llm  # modèle du rôle "decompose", voir llm.py

DECOMPOSITION_SYSTEM_PROMPT = """You are a factual claim extractor. Your only task is to decompose
a text into a list of atomic claims (individual factual assertions).

IMPORTANT: Always output claims in English, regardless of the language of the input text. The
source corpus is in English, and the embedding model used for retrieval is English-optimized —
claims in another language will retrieve poorly. If the input text is not in English, translate
each extracted claim into English as you extract it.

Strict rules:
1. Each claim must be a SINGLE verifiable factual assertion — no compound sentences joined by
   "and", "but", "while", etc. If a sentence contains multiple facts, split it into multiple claims.
2. Each claim must be self-contained: resolve pronouns and references ("this method", "it") to the
   actual subject they refer to, based on the surrounding context.
3. Ignore sentences that are not factual assertions: meta-commentary ("According to the provided
   passages...", "In summary..."), transitions, or vague statements of uncertainty with no factual
   content of their own.
4. If the source text cites a source in brackets (e.g. [filename.pdf | chunk #N]) for a claim,
   carry that citation into the claim's "cited_source" field. If several claims come from the same
   source sentence, they all inherit the same citation.
5. If a claim has no explicit citation in the text, set "cited_source" to null.

Respond ONLY with a valid JSON object, no text before or after, in this format:

{
  "claims": [
    {"id": "c1", "claim": "...", "cited_source": "... or null"},
    {"id": "c2", "claim": "...", "cited_source": "... or null"}
  ]
}
"""


def decompose_into_claims(llm: LLM, draft_answer: str) -> list[dict]:
    """Envoie la réponse brouillon au LLM et retourne la liste de claims parsée."""
    raw_text = llm.chat(
        [
            {"role": "system", "content": DECOMPOSITION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Text to decompose:\n\n{draft_answer}"},
        ],
        json_mode=True,
    )

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Le modèle n'a pas retourné du JSON valide.\nRéponse brute :\n{raw_text}"
        ) from e

    claims = parsed.get("claims", [])
    if not claims:
        raise RuntimeError(f"Aucun claim extrait. Réponse brute :\n{raw_text}")

    return claims


def print_claims(claims: list[dict]):
    print(f"\n{len(claims)} claims extraits :\n")
    for c in claims:
        source = c.get("cited_source") or "(aucune source citée)"
        print(f"  [{c['id']}] {c['claim']}")
        print(f"        source: {source}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--answer_file", type=str, required=True,
                         help="Fichier texte contenant la réponse brouillon à décomposer.")
    parser.add_argument("--save_json", type=str, default=None,
                         help="Chemin optionnel pour sauvegarder les claims en JSON "
                              "(à utiliser ensuite comme entrée de verify_claims.py).")
    args = parser.parse_args()

    llm = get_llm("decompose")

    with open(args.answer_file, "r", encoding="utf-8") as f:
        draft_answer = f.read()

    print(f"Décomposition en claims atomiques ({llm.describe()})...")
    claims = decompose_into_claims(llm, draft_answer)
    print_claims(claims)

    if args.save_json:
        with open(args.save_json, "w", encoding="utf-8") as f:
            json.dump({"claims": claims}, f, ensure_ascii=False, indent=2)
        print(f"Claims sauvegardés dans {args.save_json}")


if __name__ == "__main__":
    main()  