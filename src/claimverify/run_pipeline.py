"""
Pipeline complet — Étapes B + C + D enchaînées automatiquement
==================================================================

Exécute la boucle complète pour une (ou plusieurs) question(s) :
    question -> retrieval par document -> réponse brouillon (B)
             -> décomposition en claims (C)
             -> vérification de chaque claim (D)

Charge le modèle d'embedding, la connexion DB, et les LLM (un par rôle) UNE SEULE
FOIS (plutôt que 3x en lançant chaque script séparément), et enchaîne
directement en mémoire — plus besoin de copier-coller des fichiers .txt/.json
entre les étapes.

Produit un rapport horodaté (JSON + Markdown) dans reports/, avec :
    - la réponse brouillon, les claims, les verdicts
    - le temps de chaque étape (utile pour du benchmarking modèle/paramètres)
    - un résumé agrégé si plusieurs questions sont passées en une fois

Prérequis :
    pip install openai python-dotenv psycopg2-binary sentence-transformers langgraph

--db_url est facultatif si DB_URL est dans .env (voir config.py).

Usage (une question) :
    python -m claimverify.run_pipeline \
        --query "Does semantic chunking improve retrieval performance?"

Usage (plusieurs questions, fichier texte avec une question par ligne,
lignes vides et lignes commençant par # ignorées) :
    python -m claimverify.run_pipeline \
        --questions_file eval_questions.txt
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from claimverify.config import add_db_url_argument
from claimverify.contracts import VERDICT_ICONS, VERDICT_LABELS
from claimverify.draft_answer import (
    TOP_K_PER_DOC as DRAFT_TOP_K_PER_DOC,
    generate_draft_answer,
)
from claimverify.decompose_claims import decompose_into_claims
from claimverify.llm import LLM, ROLES, get_llm
from claimverify.verify_claims import build_graph, TOP_K_PER_DOC as VERIFY_TOP_K_PER_DOC
from claimverify.retrieval import embed_query, load_embedding_model, search_per_document

# Rapports écrits dans ./reports relatif au répertoire courant (racine du repo
# quand on passe par le Makefile).
REPORTS_DIR = Path.cwd() / "reports"


def run_single_question(query: str, embed_model, conn, llms: dict[str, LLM],
                         draft_top_k: int, verify_graph) -> dict:
    """Exécute B -> C -> D pour une seule question et retourne un dict complet
    (réponse, claims, verdicts, timings) pour le rapport."""
    timings = {}
    t0 = time.perf_counter()

    # --- Étape B : réponse brouillon ---
    query_embedding = embed_query(embed_model, query)
    passages = search_per_document(conn, query_embedding, draft_top_k)
    docs_covered = sorted({p.filename for p in passages})

    t1 = time.perf_counter()
    draft = generate_draft_answer(llms["draft"], query, passages)
    t2 = time.perf_counter()
    timings["retrieval_draft_seconds"] = round(t1 - t0, 2)
    timings["generation_draft_seconds"] = round(t2 - t1, 2)

    # --- Étape C : décomposition en claims ---
    claims = decompose_into_claims(llms["decompose"], draft)
    t3 = time.perf_counter()
    timings["decomposition_seconds"] = round(t3 - t2, 2)

    # --- Étape D : vérification de chaque claim ---
    initial_state = {
        "claims": claims,
        "current_index": 0,
        "verdicts": [],
        "embed_model": embed_model,
        "db_conn": conn,
        "llm": llms["verify"],
        "current_evidence": "",
    }
    final_state = verify_graph.invoke(initial_state)
    verdicts = final_state["verdicts"]
    t4 = time.perf_counter()
    timings["verification_seconds"] = round(t4 - t3, 2)
    timings["total_seconds"] = round(t4 - t0, 2)

    counts = dict.fromkeys(VERDICT_LABELS, 0)
    for v in verdicts:
        counts[v.verdict] += 1

    # Le rapport est du JSON : on y met les contrats sous forme de dicts.
    return {
        "query": query,
        "draft_answer_docs_covered": docs_covered,
        "draft_answer": draft.text,
        "claims": [c.model_dump() for c in claims],
        "verdicts": [v.model_dump() for v in verdicts],
        "verdict_counts": counts,
        "timings": timings,
    }


def load_questions(args) -> list[str]:
    if args.query:
        return [args.query]

    with open(args.questions_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f]
    return [line for line in lines if line and not line.startswith("#")]


def build_markdown_report(run_results: list[dict], run_metadata: dict) -> str:
    lines = [
        f"# Pipeline Run Report — {run_metadata['timestamp']}",
        "",
        f"- Draft model: `{run_metadata['models']['draft']}`",
        f"- Decomposition model: `{run_metadata['models']['decompose']}`",
        f"- Verifier model: `{run_metadata['models']['verify']}`",
        f"- Embedding model: `{run_metadata['embedding_model']}`",
        f"- Draft retrieval: top-{run_metadata['draft_top_k_per_doc']} per document",
        f"- Verification retrieval: top-{run_metadata['verify_top_k_per_doc']} per document",
        f"- Questions run: {len(run_results)}",
        "",
    ]

    total_counts = dict.fromkeys(VERDICT_LABELS, 0)
    total_claims = 0
    for r in run_results:
        for k, v in r["verdict_counts"].items():
            total_counts[k] += v
        total_claims += len(r["claims"])

    if len(run_results) > 1:
        lines += [
            "## Aggregate summary",
            "",
            f"- Total claims across all questions: {total_claims}",
        ]
        for label in VERDICT_LABELS:
            n = total_counts[label]
            lines.append(f"- {label.capitalize()}: {n} ({100 * n / max(total_claims, 1):.0f}%)")
        lines.append("")

    for i, r in enumerate(run_results, 1):
        lines += [
            f"## Question {i}: {r['query']}",
            "",
            f"**Draft answer sources:** {', '.join(r['draft_answer_docs_covered'])}",
            "",
            f"**Timings:** retrieval {r['timings']['retrieval_draft_seconds']}s · "
            f"draft generation {r['timings']['generation_draft_seconds']}s · "
            f"decomposition {r['timings']['decomposition_seconds']}s · "
            f"verification {r['timings']['verification_seconds']}s · "
            f"**total {r['timings']['total_seconds']}s**",
            "",
            "**Verdicts:** "
            + ", ".join(f"{r['verdict_counts'][label]} {label}" for label in VERDICT_LABELS)
            + f" (out of {len(r['claims'])} claims)",
            "",
            "### Draft answer",
            "",
            r["draft_answer"],
            "",
            "### Claim verdicts",
            "",
        ]
        for v in r["verdicts"]:
            icon = VERDICT_ICONS[v["verdict"]]
            lines.append(f"- [{icon}] **{v['verdict'].upper()}** — {v['claim']}")
            lines.append(f"  - {v['justification']}")
            if v.get("contradicting_sources"):
                lines.append(f"  - Contradicting sources: {v['contradicting_sources']}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    add_db_url_argument(parser)
    parser.add_argument("--query", type=str, default=None,
                         help="Une seule question à traiter.")
    parser.add_argument("--questions_file", type=str, default=None,
                         help="Fichier texte avec une question par ligne, pour traiter "
                              "plusieurs questions en un seul run (benchmarking).")
    parser.add_argument("--draft_top_k_per_doc", type=int, default=DRAFT_TOP_K_PER_DOC)
    args = parser.parse_args()

    if not args.query and not args.questions_file:
        raise RuntimeError("Fournir soit --query, soit --questions_file.")

    # Un LLM par rôle (voir llm.py). Échoue ici, avant de charger quoi que ce
    # soit, si une clé API manque.
    llms = {role: get_llm(role) for role in ROLES}
    for role, llm in llms.items():
        print(f"LLM {role:<9}: {llm.describe()}")

    questions = load_questions(args)

    print("Chargement du modèle d'embedding...")
    embed_model = load_embedding_model(device="cuda")  # "cpu" si pas de GPU

    conn = psycopg2.connect(args.db_url)
    verify_graph = build_graph()

    run_results = []
    for i, question in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] {question}")
        result = run_single_question(
            question, embed_model, conn, llms, args.draft_top_k_per_doc, verify_graph
        )
        print(f"  -> {result['verdict_counts']} in {result['timings']['total_seconds']}s")
        run_results.append(result)

    conn.close()

    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_metadata = {
        "timestamp": timestamp,
        "models": {role: llm.describe() for role, llm in llms.items()},
        "embedding_model": "BAAI/bge-base-en-v1.5",
        "draft_top_k_per_doc": args.draft_top_k_per_doc,
        "verify_top_k_per_doc": VERIFY_TOP_K_PER_DOC,
    }

    json_path = REPORTS_DIR / f"report_{timestamp}.json"
    md_path = REPORTS_DIR / f"report_{timestamp}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"metadata": run_metadata, "results": run_results}, f, ensure_ascii=False, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(build_markdown_report(run_results, run_metadata))

    print(f"\nRapport sauvegardé :\n  {json_path}\n  {md_path}")


if __name__ == "__main__":
    main()