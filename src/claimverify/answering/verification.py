"""
Vérification de claims — Étape D (le coeur du projet)
=========================================================

Pour chaque claim atomique (sortie de l'étape C) :
    1. Retrieval CIBLÉ ET PAR DOCUMENT (pas de réutilisation du cited_source
       du claim — on ignore délibérément d'où le claim brouillon prétendait
       venir, et on recherche indépendamment dans TOUT le corpus).
    2. Un appel LLM séparé — par défaut un modèle d'une AUTRE famille que
       celui qui a rédigé la réponse (rôle "verify", voir llm.py) — juge : supporté / contredit / non vérifiable,
       avec justification et citation des sources utilisées pour le verdict.

Orchestré avec LangGraph : un noeud retrieval -> un noeud verdict -> boucle
sur la liste de claims jusqu'à épuisement.

Prérequis :
    pip install openai python-dotenv psycopg2-binary sentence-transformers langgraph

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
from pydantic import ValidationError
from sentence_transformers import SentenceTransformer

from claimverify.answering.retrieval import Retriever, format_evidence
from claimverify.components.embedding import embed_query, load_embedding_model
from claimverify.components.store import search_per_document
from claimverify.config import add_db_url_argument
from claimverify.contracts import VERDICT_ICONS, VERDICT_LABELS, Claim, Passage, Verdict
from claimverify.llm import LLM, get_llm  # modèle du rôle "verify", voir llm.py

TOP_K_PER_DOC = 2

VERDICT_SYSTEM_PROMPT = """You are a rigorous claim verifier (fact-checker). You are given a claim
and a set of source passages, potentially from MULTIPLE different documents. Your task: judge
whether the claim is supported, contradicted, or unverifiable based on these passages.

IMPORTANT: Always respond in English, matching the language of the claim and evidence.

Strict verdict definitions:
- "supported": at least one source clearly states or strongly implies the claim, AND no retrieved
  source contradicts it.
- "contradicted": at least one source states something that conflicts with the claim, even if
  other sources support it elsewhere (the conflict must be flagged).
- "unverifiable": none of the retrieved sources speak to the claim's subject, either for or
  against. Do not confuse this with "contradicted": absence of evidence is not opposition.

Important: if sources contradict EACH OTHER on this claim (e.g. one document supports it, another
contradicts it), the verdict must be "contradicted", and the justification must explicitly name
the documents that disagree.

Respond ONLY with a valid JSON object, no text before or after, in this format:

{
  "verdict": "supported" | "contradicted" | "unverifiable",
  "justification": "concise explanation, citing source documents by filename",
  "supporting_sources": ["filename.pdf", ...],
  "contradicting_sources": ["filename.pdf", ...]
}
"""


def debug_single_claim(claim_text: str, db_url: str):
    """Affiche en détail (texte complet + scores) les chunks récupérés pour
    UN SEUL claim, sans appel LLM. Sert à diagnostiquer si un verdict
    "unverifiable" vient d'un problème de retrieval (le bon chunk n'a pas
    été récupéré) ou d'un problème de jugement LLM (le chunk était là mais
    mal évalué)."""
    print("Chargement du modèle d'embedding...")
    embed_model = load_embedding_model(device="cuda")

    conn = psycopg2.connect(db_url)
    query_embedding = embed_query(embed_model, claim_text)
    passages = search_per_document(conn, query_embedding, top_k_per_doc=TOP_K_PER_DOC)
    conn.close()

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
# État du graphe LangGraph
# ---------------------------------------------------------------------------

class VerificationState(TypedDict):
    claims: list[Claim]         # claims à vérifier (sortie de l'étape C)
    current_index: int          # index du claim en cours de traitement
    verdicts: list[Verdict]     # verdicts accumulés
    # ressources partagées, injectées une fois au démarrage
    embed_model: SentenceTransformer
    db_conn: object
    llm: LLM                     # modèle du rôle "verify"
    current_evidence: str        # preuve récupérée pour le claim courant (état intermédiaire)


# ---------------------------------------------------------------------------
# Noeuds du graphe
# ---------------------------------------------------------------------------

def retrieve_node(state: VerificationState) -> dict:
    claim = state["claims"][state["current_index"]]
    query_embedding = embed_query(state["embed_model"], claim.claim)
    passages = search_per_document(state["db_conn"], query_embedding)
    evidence = format_evidence(passages)
    print(f"  [{claim.id}] retrieval : {len(passages)} chunks récupérés depuis "
          f"{len({p.filename for p in passages})} document(s)")
    return {"current_evidence": evidence}


def judge_with_llm(llm: LLM, claim: Claim, evidence: str) -> Verdict:
    """Demande un verdict au LLM pour un claim, à partir des passages déjà mis en forme."""
    user_message = f"""Claim to verify:
"{claim.claim}"

Source passages (from multiple documents, evaluated independently of the source originally
cited by the claim):

{evidence}
"""
    raw_text = llm.chat(
        [
            {"role": "system", "content": VERDICT_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        json_mode=True,
    )

    identity = {
        "claim_id": claim.id,
        "claim": claim.claim,
        "original_cited_source": claim.cited_source,
        "verifier": f"llm_judge:{llm.model}",
    }
    try:
        return Verdict(**identity, **json.loads(raw_text))
    except (json.JSONDecodeError, TypeError, ValidationError):
        # Réponse inexploitable (JSON invalide, verdict inconnu, champ manquant).
        return Verdict(
            **identity,
            verdict="unverifiable",
            justification=f"Erreur de parsing JSON du LLM. Réponse brute : {raw_text[:200]}",
        )


def verdict_node(state: VerificationState) -> dict:
    claim = state["claims"][state["current_index"]]
    verdict = judge_with_llm(state["llm"], claim, state["current_evidence"])
    print(f"  [{claim.id}] verdict : {verdict.verdict.upper()}")

    return {
        "verdicts": state["verdicts"] + [verdict],
        "current_index": state["current_index"] + 1,
    }


def should_continue(state: VerificationState) -> str:
    return "retrieve" if state["current_index"] < len(state["claims"]) else "end"


# ---------------------------------------------------------------------------
# Construction du graphe
# ---------------------------------------------------------------------------

def build_graph():
    graph = StateGraph(VerificationState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("verdict", verdict_node)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "verdict")
    graph.add_conditional_edges("verdict", should_continue, {"retrieve": "retrieve", "end": END})

    return graph.compile()


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
        return judge_with_llm(self.llm, claim, format_evidence(passages))


@runtime_checkable
class Verifier(Protocol):
    """Interface : rend un verdict pour chaque claim."""

    def verify(self, claims: list[Claim]) -> list[Verdict]: ...


class VerifierState(TypedDict):
    claims: list[Claim]
    current_index: int
    passages: list[Passage]      # passages du claim en cours
    verdicts: list[Verdict]


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
    print(f"Total : {len(verdicts)} claims — "
          f"{counts['supported']} supportés, "
          f"{counts['contradicted']} contredits, "
          f"{counts['unverifiable']} non vérifiables\n")

    for v in verdicts:
        print(f"[{VERDICT_ICONS[v.verdict]}] {v.claim_id} — {v.verdict.upper()}")
        print(f"    Claim : {v.claim}")
        print(f"    Justification : {v.justification}")
        if v.contradicting_sources:
            print(f"    Sources en contradiction : {v.contradicting_sources}")
        print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--claims_file", type=str, default=None,
                         help="Fichier JSON contenant les claims (sortie de decomposition.py).")
    add_db_url_argument(parser)
    parser.add_argument("--save_json", type=str, default=None,
                         help="Chemin optionnel pour sauvegarder les verdicts en JSON.")
    parser.add_argument("--debug_claim", type=str, default=None,
                         help="Mode debug : affiche les chunks bruts récupérés pour CE texte de "
                              "claim (sans appel LLM), au lieu de lancer la vérification complète.")
    args = parser.parse_args()

    if args.debug_claim:
        debug_single_claim(args.debug_claim, args.db_url)
        return

    if not args.claims_file:
        raise RuntimeError("--claims_file est requis en dehors du mode --debug_claim.")

    llm = get_llm("verify")

    with open(args.claims_file, "r", encoding="utf-8") as f:
        claims_data = json.load(f)
    raw_claims = claims_data["claims"] if "claims" in claims_data else claims_data
    claims = [Claim.model_validate(c) for c in raw_claims]

    print("Chargement du modèle d'embedding...")
    embed_model = load_embedding_model(device="cuda")  # "cpu" si pas de GPU

    conn = psycopg2.connect(args.db_url)

    graph = build_graph()

    print(f"\nVérification de {len(claims)} claims ({llm.describe()})...\n")
    initial_state: VerificationState = {
        "claims": claims,
        "current_index": 0,
        "verdicts": [],
        "embed_model": embed_model,
        "db_conn": conn,
        "llm": llm,
        "current_evidence": "",
    }

    final_state = graph.invoke(initial_state)
    conn.close()

    print_summary(final_state["verdicts"])

    if args.save_json:
        with open(args.save_json, "w", encoding="utf-8") as f:
            json.dump([v.model_dump() for v in final_state["verdicts"]], f,
                      ensure_ascii=False, indent=2)
        print(f"Verdicts sauvegardés dans {args.save_json}")


if __name__ == "__main__":
    main()