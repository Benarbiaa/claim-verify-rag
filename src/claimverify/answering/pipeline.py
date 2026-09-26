"""
Pipeline complet — Étapes B + C + D enchaînées automatiquement
==================================================================

Exécute la boucle complète pour une (ou plusieurs) question(s) :
    question -> retrieval par document -> réponse brouillon (B)
             -> décomposition en claims (C)
             -> vérification de chaque claim (D)

Les étapes sont construites UNE SEULE FOIS à partir de config.yaml (voir
factory.py), puis enchaînées en mémoire via leurs interfaces : ce fichier ne
sait pas quel modèle, quelle base ou quelle bibliothèque chaque étape utilise.

Chaque run a son dossier runs/<run_id>/ : events.jsonl (la sortie de chaque étape,
voir events.py) et un rapport (report.json + report.md) avec :
    - la réponse brouillon, les claims, les verdicts
    - le temps de chaque étape (utile pour du benchmarking modèle/paramètres)
    - un résumé agrégé si plusieurs questions sont passées en une fois
    - la configuration complète utilisée (pour reproduire le run)

--db_url est facultatif si DB_URL est dans .env (voir config.py), et
--config vaut config.yaml par défaut.

Usage (une question) :
    python -m claimverify.answering.pipeline \
        --query "Does semantic chunking improve retrieval performance?"

Usage (plusieurs questions, fichier texte avec une question par ligne,
lignes vides et lignes commençant par # ignorées) :
    python -m claimverify.answering.pipeline \
        --questions_file eval_questions.txt
"""

import argparse
import json
import time

import psycopg2

from claimverify.config import add_db_url_argument
from claimverify.contracts import VERDICT_ICONS, VERDICT_LABELS
from claimverify.events import (
    ClaimsExtracted,
    ClaimVerified,
    DraftWritten,
    PassagesRetrieved,
    QuestionFinished,
    QuestionStarted,
    RunFinished,
    RunStarted,
)
from claimverify.factory import AnsweringStages, build_answering
from claimverify.reporting import Run
from claimverify.settings import LLMStageSettings, Settings, add_config_argument, load_settings


def run_single_question(query: str, stages: AnsweringStages, run: Run,
                        question_index: int = 1) -> dict:
    """Exécute B -> C -> D pour une seule question, émet un événement après
    chaque étape (et après chaque verdict), et retourne un dict complet
    (réponse, claims, verdicts, timings) pour le rapport."""
    timings = {}
    t0 = time.perf_counter()
    run.emit(QuestionStarted, question_index=question_index, question=query)

    # --- Étape B : réponse brouillon ---
    passages = stages.retriever.retrieve(query)
    docs_covered = sorted({p.filename for p in passages})
    t1 = time.perf_counter()
    run.emit(PassagesRetrieved, question_index=question_index, passages=passages, seconds=t1 - t0)

    draft = stages.drafter.draft(query, passages)
    t2 = time.perf_counter()
    run.emit(DraftWritten, question_index=question_index, draft=draft, seconds=t2 - t1)
    timings["retrieval_draft_seconds"] = round(t1 - t0, 2)
    timings["generation_draft_seconds"] = round(t2 - t1, 2)

    # --- Étape C : décomposition en claims ---
    claims = stages.decomposer.decompose(draft)
    t3 = time.perf_counter()
    run.emit(ClaimsExtracted, question_index=question_index, claims=claims, seconds=t3 - t2)
    timings["decomposition_seconds"] = round(t3 - t2, 2)

    # --- Étape D : vérification, un événement par verdict dès qu'il est prêt ---
    verdicts = []
    for position, verdict in enumerate(stages.verifier.verify(claims), 1):
        verdicts.append(verdict)
        run.emit(ClaimVerified, question_index=question_index, position=position,
                 total=len(claims), verdict=verdict)
    t4 = time.perf_counter()
    timings["verification_seconds"] = round(t4 - t3, 2)
    timings["total_seconds"] = round(t4 - t0, 2)

    counts = dict.fromkeys(VERDICT_LABELS, 0)
    for v in verdicts:
        counts[v.verdict] += 1
    run.emit(QuestionFinished, question_index=question_index, verdict_counts=counts,
             seconds=t4 - t0)

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


def describe_llm_stage(settings: Settings, stage: LLMStageSettings) -> str:
    return f"{stage.model} @ {settings.providers[stage.provider].base_url}"


def main():
    parser = argparse.ArgumentParser()
    add_db_url_argument(parser)
    add_config_argument(parser)
    parser.add_argument("--query", type=str, default=None,
                         help="Une seule question à traiter.")
    parser.add_argument("--questions_file", type=str, default=None,
                         help="Fichier texte avec une question par ligne, pour traiter "
                              "plusieurs questions en un seul run (benchmarking).")
    args = parser.parse_args()

    if not args.query and not args.questions_file:
        raise RuntimeError("Fournir soit --query, soit --questions_file.")

    settings = load_settings(args.config)
    a = settings.answering
    models = {
        "draft": describe_llm_stage(settings, a.drafter),
        "decompose": describe_llm_stage(settings, a.decomposer),
        "verify": describe_llm_stage(settings, a.verifier.judge),
    }
    for role, desc in models.items():
        print(f"LLM {role:<9}: {desc}")

    questions = load_questions(args)

    # Échoue ici, avant tout calcul, si une clé API manque.
    conn = psycopg2.connect(args.db_url)
    stages = build_answering(settings, conn)

    run = Run("answering")
    start = time.perf_counter()
    run.emit(RunStarted, config=settings.model_dump(),
             inputs={"config_file": str(args.config), "questions": questions})

    run_results = []
    try:
        for i, question in enumerate(questions, 1):
            run_results.append(run_single_question(question, stages, run, question_index=i))
    finally:
        conn.close()

    run_metadata = {
        "timestamp": run.run_id,
        "config_file": str(args.config),
        "models": models,
        "embedding_model": settings.embedding.model,
        "draft_top_k_per_doc": a.retriever.top_k_per_doc,
        "verify_top_k_per_doc": a.verifier.retriever.top_k_per_doc,
        "config": settings.model_dump(),  # tout config.yaml, pour reproduire le run
    }
    with open(run.dir / "report.json", "w", encoding="utf-8") as f:
        json.dump({"metadata": run_metadata, "results": run_results}, f, ensure_ascii=False, indent=2)
    with open(run.dir / "report.md", "w", encoding="utf-8") as f:
        f.write(build_markdown_report(run_results, run_metadata))

    run.emit(RunFinished, seconds=time.perf_counter() - start, summary={
        "questions": len(questions), "run_dir": str(run.dir),
    })

if __name__ == "__main__":
    main()