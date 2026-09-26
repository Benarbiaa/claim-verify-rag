"""
Vérification de claims — Étape D (le coeur du projet)
=========================================================

Pour chaque claim atomique (sortie de l'étape C) :
    1. Retrieval CIBLÉ ET PAR DOCUMENT (pas de réutilisation du cited_source
       du claim — on ignore délibérément d'où le claim brouillon prétendait
       venir, et on recherche indépendamment dans TOUT le corpus).
    2. Un juge — par défaut un LLM d'une AUTRE famille que celui qui a rédigé
       la réponse (answering.verifier.judge dans config.yaml) — rend un verdict :
       supporté / contredit / non vérifiable, avec justification et sources.

Le Verifier reçoit son Retriever et son Judge (voir la section Interfaces) ;
l'implémentation actuelle boucle avec LangGraph : retrieve -> judge -> claim
suivant, jusqu'à épuisement.

Usage :
    # 1) Décomposer une réponse en claims (étape C) et sauvegarder en JSON :
    python -m claimverify.answering.decomposition --draft_file draft.json --save_json claims.json

    # 2) Vérifier ces claims (--db_url facultatif si DB_URL est dans .env, voir config.py) :
    python -m claimverify.answering.verification --claims_file claims.json
"""

import argparse
import json
from typing import Protocol, TypedDict, runtime_checkable

import psycopg2
from langgraph.graph import END, StateGraph
from openai import BadRequestError

from claimverify.answering.retrieval import Retriever, format_evidence
from claimverify.config import add_db_url_argument
from claimverify.contracts import JUDGE_LABELS, VERDICT_ICONS, VERDICT_LABELS, Claim, Passage, Verdict
from claimverify.llm import LLM
from claimverify.settings import add_config_argument, load_settings

VERDICT_SYSTEM_PROMPT = """You are a rigorous claim verifier (fact-checker). You are given a claim
and a set of source passages, potentially from MULTIPLE different documents. Judge the claim using
ONLY these passages: a claim you believe is true but that no passage addresses is "unverifiable".

IMPORTANT: Always respond in English, matching the language of the claim and evidence.

Verdict definitions (pick exactly one):
- "supported": at least one source clearly states or strongly implies the claim, and no source
  states something incompatible with it.
- "contradicted": the sources state something incompatible with the claim (a different number,
  name, date, direction of effect...), and no source supports it.
- "contested": the sources disagree with EACH OTHER on this claim: at least one supports it and at
  least one states something incompatible with it. Name the documents on each side.
- "unverifiable": no passage addresses the claim's subject, for or against. Absence of evidence
  is not contradiction.

A source that discusses a different technique, dataset or setting does NOT contradict the claim:
contradiction requires incompatible statements about the same thing. For example, a paper that
proposes a complementary method is not evidence against another paper's result.

The source lists must match the verdict: "contradicted" needs at least one contradicting source,
"contested" needs at least one source on each side.

Respond ONLY with a valid JSON object, no text before or after, in this format:

{
  "verdict": "supported" | "contradicted" | "contested" | "unverifiable",
  "justification": "concise explanation, citing source documents by filename",
  "supporting_sources": ["filename.pdf", ...],
  "contradicting_sources": ["filename.pdf", ...]
}
"""


def debug_single_claim(claim_text: str, retriever: Retriever):
    """Affiche en détail (texte complet + scores) les chunks récupérés pour
    UN SEUL claim, sans appel LLM. Sert à diagnostiquer si un verdict
    "unverifiable" vient d'un problème de retrieval (le bon chunk n'a pas
    été récupéré) ou d'un problème de jugement LLM (le chunk était là mais
    mal évalué)."""
    passages = retriever.retrieve(claim_text)

    print("=" * 100)
    print(f"CLAIM : {claim_text}")
    print("=" * 100)
    for p in passages:
        print(f"\n[score={p.score:.4f}] {p.filename} (#{p.chunk_index}, {p.source_type})")
        print(f"{'-' * 80}")
        print(p.text)
    print("\n" + "=" * 100)
    print(f"Total : {len(passages)} chunks depuis {len({p.filename for p in passages})} document(s)")


# ---------------------------------------------------------------------------
# Jugement d'un claim par un LLM
# ---------------------------------------------------------------------------

def judge_with_llm(llm: LLM, claim: Claim, passages: list[Passage]) -> Verdict:
    """Demande un verdict au LLM pour un claim, au vu des passages.

    Une réponse inexploitable donne le verdict "error" (jamais "unverifiable",
    qui est une conclusion sur les sources) : JSON invalide ou tronqué, verdict
    inconnu, champ manquant, sources incohérentes avec le verdict, ou JSON
    rejeté par le fournisseur lui-même. La réponse brute est gardée.
    """
    user_message = f"""Claim to verify:
"{claim.claim}"

Source passages (from multiple documents, evaluated independently of the source originally
cited by the claim):

{format_evidence(passages)}
"""
    identity = {
        "claim_id": claim.id,
        "claim": claim.claim,
        "original_cited_source": claim.cited_source,
        "verifier": f"llm_judge:{llm.model}",
        "evidence": passages,
    }
    raw_text = ""
    try:
        raw_text = llm.chat(
            [
                {"role": "system", "content": VERDICT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            json_mode=True,
        ) or ""
        data = json.loads(raw_text)
        if not isinstance(data, dict) or data.get("verdict") not in JUDGE_LABELS:
            raise ValueError(f"verdict absent ou hors des {len(JUDGE_LABELS)} verdicts du juge")
        return Verdict(**identity, **data)
    except BadRequestError as e:
        # En mode JSON, Groq peut rejeter lui-même une réponse qui n'est pas du
        # JSON valide (souvent tronquée). Les autres erreurs 400 restent des erreurs.
        if "json_validate_failed" not in str(e):
            raise
        reason, raw_text = "JSON rejeté par le fournisseur", str(e)
    except (json.JSONDecodeError, TypeError, ValueError) as e:  # ValidationError en hérite
        reason = f"{type(e).__name__}: {str(e).splitlines()[0]}"
    return Verdict(
        **identity,
        verdict="error",
        justification=f"Réponse du juge inexploitable ({reason}). Réponse brute : {raw_text[:300]}",
    )


# ---------------------------------------------------------------------------
# Interfaces Judge et Verifier, et leurs implémentations
# ---------------------------------------------------------------------------
# Le Verifier fait "pour chaque claim : chercher des passages, puis juger".
# Il REÇOIT un Retriever et un Judge : on peut remplacer l'un, l'autre, ou
# tout le Verifier. L'état du graphe ne contient que des données.

@runtime_checkable
class Judge(Protocol):
    """Interface : rend un verdict sur un claim, au vu de passages."""

    def judge(self, claim: Claim, passages: list[Passage]) -> Verdict: ...


class LLMJudge:
    """Implémentation : un LLM (rôle "verify" de llm.py) avec VERDICT_SYSTEM_PROMPT."""

    def __init__(self, llm: LLM):
        self.llm = llm

    def judge(self, claim: Claim, passages: list[Passage]) -> Verdict:
        return judge_with_llm(self.llm, claim, passages)


@runtime_checkable
class Verifier(Protocol):
    """Interface : rend un verdict pour chaque claim."""

    def verify(self, claims: list[Claim]) -> list[Verdict]: ...


class VerifierState(TypedDict):
    claims: list[Claim]
    current_index: int
    passages: list[Passage]      # passages du claim en cours
    verdicts: list[Verdict]


def should_continue(state: VerifierState) -> str:
    return "retrieve" if state["current_index"] < len(state["claims"]) else "end"


class LangGraphVerifier:
    """Implémentation : boucle LangGraph retrieve -> judge sur chaque claim."""

    def __init__(self, retriever: Retriever, judge: Judge):
        self.retriever = retriever
        self.judge = judge
        self.graph = self._build_graph()

    def _build_graph(self):
        def retrieve(state: VerifierState) -> dict:
            claim = state["claims"][state["current_index"]]
            return {"passages": self.retriever.retrieve(claim.claim)}

        def judge(state: VerifierState) -> dict:
            claim = state["claims"][state["current_index"]]
            verdict = self.judge.judge(claim, state["passages"])
            return {"verdicts": state["verdicts"] + [verdict],
                    "current_index": state["current_index"] + 1}

        graph = StateGraph(VerifierState)
        graph.add_node("retrieve", retrieve)
        graph.add_node("judge", judge)
        graph.set_entry_point("retrieve")
        graph.add_edge("retrieve", "judge")
        graph.add_conditional_edges("judge", should_continue, {"retrieve": "retrieve", "end": END})
        return graph.compile()

    def verify(self, claims: list[Claim]) -> list[Verdict]:
        if not claims:
            return []
        initial: VerifierState = {"claims": claims, "current_index": 0,
                                  "passages": [], "verdicts": []}
        # 2 étapes par claim (retrieve + judge) : la limite par défaut de
        # LangGraph (25 étapes) ferait planter une réponse de plus de 12 claims.
        return self.graph.invoke(initial, {"recursion_limit": 2 * len(claims) + 5})["verdicts"]


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def print_summary(verdicts: list[Verdict]):
    counts = dict.fromkeys(VERDICT_LABELS, 0)
    for v in verdicts:
        counts[v.verdict] += 1

    print("\n" + "=" * 100)
    print("RÉSUMÉ DE LA VÉRIFICATION")
    print("=" * 100)
    detail = ", ".join(f"{n} {label}" for label, n in counts.items() if n)
    print(f"Total : {len(verdicts)} claims — {detail}\n")

    for v in verdicts:
        print(f"[{VERDICT_ICONS[v.verdict]}] {v.claim_id} — {v.verdict.upper()}")
        print(f"    Claim : {v.claim}")
        print(f"    Justification : {v.justification}")
        if v.contradicting_sources:
            print(f"    Sources en contradiction : {v.contradicting_sources}")
        print()


def main():
    # Import local : factory importe ce module, l'importer en tête serait circulaire.
    from claimverify.factory import build_embedder, build_retriever, build_verifier

    parser = argparse.ArgumentParser()
    parser.add_argument("--claims_file", type=str, default=None,
                         help="Fichier JSON contenant les claims (sortie de decomposition.py).")
    add_db_url_argument(parser)
    add_config_argument(parser)
    parser.add_argument("--save_json", type=str, default=None,
                         help="Chemin optionnel pour sauvegarder les verdicts en JSON.")
    parser.add_argument("--debug_claim", type=str, default=None,
                         help="Mode debug : affiche les chunks bruts récupérés pour CE texte de "
                              "claim (sans appel LLM), au lieu de lancer la vérification complète.")
    args = parser.parse_args()

    settings = load_settings(args.config)
    conn = psycopg2.connect(args.db_url)

    if args.debug_claim:
        retriever = build_retriever(settings.answering.verifier.retriever, build_embedder(settings),
                                    conn, "answering.verifier.retriever")
        debug_single_claim(args.debug_claim, retriever)
        conn.close()
        return

    if not args.claims_file:
        raise RuntimeError("--claims_file est requis en dehors du mode --debug_claim.")

    with open(args.claims_file, "r", encoding="utf-8") as f:
        claims_data = json.load(f)
    raw_claims = claims_data["claims"] if "claims" in claims_data else claims_data
    claims = [Claim.model_validate(c) for c in raw_claims]

    verifier = build_verifier(settings, build_embedder(settings), conn)
    print(f"\nVérification de {len(claims)} claims ({settings.answering.verifier.judge.model})...\n")
    verdicts = verifier.verify(claims)
    conn.close()

    print_summary(verdicts)

    if args.save_json:
        with open(args.save_json, "w", encoding="utf-8") as f:
            json.dump([v.model_dump() for v in verdicts], f, ensure_ascii=False, indent=2)
        print(f"Verdicts sauvegardés dans {args.save_json}")


if __name__ == "__main__":
    main()