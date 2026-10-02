"""
Runs de test pour l'interface — un run "contested" qui n'existe pas encore en vrai
==================================================================================

Aucun vrai run ne contient encore de verdict "contested" (ni "contradicted",
ni "error"). Ce script construit un run de réponse qui montre les cinq
verdicts, pour tester l'interface et la présenter : c'est une FIXTURE,
affichée comme telle (source "fixture", voir api/runs.py).

    - Les passages sont de vrais chunks du corpus (data/corpus, découpés avec
      la config actuelle) : aucun texte de source n'est inventé.
    - La question, le brouillon, les claims et les réponses du juge sont
      écrits à la main. Les verdicts passent quand même par le vrai code du
      juge (judge_with_llm, avec un faux LLM) : ils respectent le contrat
      Verdict, et une réponse invalide y devient "error".
    - Les durées, tokens et attentes sont plausibles mais inventés.

Usage (pas de réseau, pas de GPU, pas de base) :
    python tests/fixtures/make_fixture_runs.py

Le run produit est versionné (tests/fixtures/runs/) : c'est lui la référence,
lue par les tests de l'interface. Ce script choisit ses passages par
(fichier, numéro de chunk) dans le découpage d'ALORS (512 mots). Depuis le
découpage en tokens, ces numéros désignent d'autres textes : avant de le
relancer, il faut re-choisir les passages pour qu'ils collent aux claims.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from claimverify.answering.verification import judge_with_llm
from claimverify.contracts import VERDICT_LABELS, Claim, Draft, Passage
from claimverify.events import (
    ClaimsExtracted,
    ClaimVerified,
    DraftWritten,
    LLMWaiting,
    PassagesRetrieved,
    QuestionFinished,
    QuestionStarted,
    RunFinished,
    RunStarted,
    Usage,
)
from claimverify.factory import build_chunker
from claimverify.indexing.loading import FileLoader
from claimverify.settings import load_settings
from fakes import fake_llm

RUN_ID = "20260101_090000_answering"
OUT = Path(__file__).parent / "runs" / RUN_ID
CONFIG_FILE = "experiments/smoke_k1.yaml"
START = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)

LUMBER = "lumberchunker-emnlp2024.pdf"
VECTARA = "vectara-semantic-chunking-naacl2025.pdf"
LEWIS = "lewis-rag-neurips2020.pdf"
ANTHROPIC = "anthropic-contextual-retrieval.md"

QUESTION = "Is it worth chunking documents by meaning instead of by fixed size?"

# (fichier, chunk_index, score) : le retrieval du brouillon, top-2 par document
DRAFT_PASSAGES = [(VECTARA, 5, 0.874), (VECTARA, 1, 0.861), (LUMBER, 5, 0.842), (LUMBER, 1, 0.829),
                  (ANTHROPIC, 0, 0.781), (ANTHROPIC, 1, 0.752), (LEWIS, 0, 0.703), (LEWIS, 9, 0.688)]

DRAFT = (
    "It depends on the documents, and the two papers that test it disagree.\n\n"
    "* LumberChunker asks a language model to find the paragraph where the content starts "
    "diverging, and reports better retrieval than every baseline on narrative books"
    "【lumberchunker-emnlp2024.pdf | chunk #1】【lumberchunker-emnlp2024.pdf | chunk #5】.\n"
    "* The NAACL 2025 study finds that on real-world documents fixed-size chunking often "
    "performed better, and recommends semantic chunking for practical RAG applications"
    "【vectara-semantic-chunking-naacl2025.pdf | chunk #5】.\n\n"
    "An LLM-based chunker is also more expensive and slower than recursive chunking"
    "【vectara-semantic-chunking-naacl2025.pdf | chunk #1】. Most production RAG systems today use "
    "semantic chunking."
)

# claim, source citée par le brouillon, passages lus par le juge (top-1 par document),
# réponse brute du juge, usage (tokens in, tokens out, secondes d'appel), attentes avant l'appel
CLAIMS = [
    ("LumberChunker asks a language model to find the paragraph where the content starts diverging.",
     f"{LUMBER} | chunk #1", [(LUMBER, 1, 0.884), (VECTARA, 4, 0.701), (ANTHROPIC, 1, 0.655), (LEWIS, 0, 0.612)],
     {"verdict": "supported",
      "justification": f"{LUMBER} describes exactly this procedure: the model receives a series of "
                       "continuous paragraphs and determines the paragraph where the content starts "
                       "diverging. The other passages do not discuss LumberChunker.",
      "supporting_sources": [LUMBER], "contradicting_sources": []},
     (3412, 162, 1.1), []),
    ("Chunking documents by meaning retrieves better passages than fixed-size chunking.",
     f"{LUMBER} | chunk #5", [(VECTARA, 5, 0.871), (LUMBER, 5, 0.846), (ANTHROPIC, 0, 0.702), (LEWIS, 9, 0.633)],
     {"verdict": "contested",
      "justification": f"The sources disagree. {LUMBER} reports that LumberChunker, which segments "
                       "text into semantically coherent chunks, shows superior performance compared to "
                       f"all baselines, including recursive chunking. {VECTARA} finds that on "
                       "non-synthetic datasets fixed-size chunking often performed better and calls it "
                       "the more efficient and reliable choice. The two papers test different "
                       "documents (narrative books vs. real-world retrieval datasets).",
      "supporting_sources": [LUMBER], "contradicting_sources": [VECTARA]},
     (3987, 241, 1.4), [29.0]),
    ("The NAACL 2025 study recommends semantic chunking for practical RAG applications.",
     f"{VECTARA} | chunk #5", [(VECTARA, 5, 0.902), (LUMBER, 5, 0.721), (ANTHROPIC, 1, 0.640), (LEWIS, 0, 0.598)],
     {"verdict": "contradicted",
      "justification": f"{VECTARA} concludes the opposite: its results suggest that fixed-size "
                       "chunking remains a more efficient and reliable choice for practical RAG "
                       "applications.",
      "supporting_sources": [], "contradicting_sources": [VECTARA]},
     (3620, 118, 0.9), [31.0]),
    ("An LLM-based chunker is more expensive and slower than recursive chunking.",
     f"{VECTARA} | chunk #1", [(LUMBER, 5, 0.867), (VECTARA, 1, 0.790), (ANTHROPIC, 1, 0.688), (LEWIS, 9, 0.601)],
     {"verdict": "supported",
      "justification": f"{LUMBER} states that LumberChunker requires an LLM, which renders it more "
                       "expensive and slower than traditional methods like recursive chunking. The "
                       f"cited source, {VECTARA}, discusses the computational cost of semantic "
                       "chunking but not LLM-based chunkers.",
      "supporting_sources": [LUMBER], "contradicting_sources": []},
     (3841, 157, 1.2), [28.0, 4.0]),
    ("Most production RAG systems today use semantic chunking.",
     None, [(ANTHROPIC, 0, 0.744), (VECTARA, 1, 0.731), (LUMBER, 1, 0.662), (LEWIS, 0, 0.640)],
     {"verdict": "unverifiable",
      "justification": "None of the passages says what production RAG systems use in practice; they "
                       "evaluate chunking methods on benchmarks.",
      "supporting_sources": [], "contradicting_sources": []},
     (3552, 96, 0.8), [33.0]),
    ("It depends on the documents.",
     None, [(VECTARA, 4, 0.712), (LUMBER, 5, 0.705), (ANTHROPIC, 0, 0.611), (LEWIS, 9, 0.577)],
     '{"verdict": "supported", "justification": "Both papers tie the result to the kind of docu',
     (3490, 1000, 6.3), [30.0]),
]
STAGE_SECONDS = {"retrieve": 3.9, "draft": 2.2, "decompose": 3.0}
DRAFT_USAGE = Usage(calls=1, tokens_in=6214, tokens_out=402, seconds=2.2)
DECOMPOSE_USAGE = Usage(calls=1, tokens_in=560, tokens_out=610, retries=1, waited_seconds=2.0, seconds=3.0)


def chunk_texts() -> dict[tuple[str, int], tuple[str, str]]:
    settings = load_settings(ROOT / CONFIG_FILE)
    documents = FileLoader().load(ROOT / "data" / "corpus")
    return {(c.filename, c.chunk_index): (c.text, c.source_type)
            for c in build_chunker(settings).chunk(documents)}


def main() -> None:
    sys.exit("Les passages de ce script viennent du découpage en mots (512 mots), remplacé par le "
             "découpage en tokens : re-choisir les passages avant de régénérer (voir l'en-tête). "
             "Le run versionné dans tests/fixtures/runs/ reste la référence.")
    texts = chunk_texts()
    settings = load_settings(ROOT / CONFIG_FILE)
    judge_model = settings.answering.verifier.judge.model

    def passage(filename: str, index: int, score: float) -> Passage:
        text, source_type = texts[(filename, index)]
        return Passage(filename=filename, source_type=source_type, chunk_index=index, text=text,
                       score=score)

    clock = START
    events = []

    def emit(event_type, advance: float = 0.0, **fields):
        nonlocal clock
        clock += timedelta(seconds=advance)
        events.append(event_type(run_id=RUN_ID, pipeline="answering", time=clock, **fields))

    emit(RunStarted, config=settings.model_dump(),
         inputs={"config_file": CONFIG_FILE, "questions": [QUESTION]})
    emit(QuestionStarted, question_index=1, question=QUESTION)
    passages = [passage(*p) for p in DRAFT_PASSAGES]
    emit(PassagesRetrieved, STAGE_SECONDS["retrieve"], question_index=1, passages=passages,
         seconds=STAGE_SECONDS["retrieve"])
    emit(DraftWritten, STAGE_SECONDS["draft"], question_index=1, seconds=STAGE_SECONDS["draft"],
         draft=Draft(question=QUESTION, text=DRAFT, passages=passages), usage=DRAFT_USAGE)
    emit(LLMWaiting, 0.8, question_index=1, role="decompose", model=settings.answering.decomposer.model,
         seconds=2.0, attempt=1, reason="server_error")
    claims = [Claim(id=f"c{i}", claim=c[0], cited_source=c[1]) for i, c in enumerate(CLAIMS, 1)]
    emit(ClaimsExtracted, STAGE_SECONDS["decompose"] - 0.8, question_index=1, claims=claims,
         seconds=STAGE_SECONDS["decompose"], usage=DECOMPOSE_USAGE)

    counts = dict.fromkeys(VERDICT_LABELS, 0)
    for position, (claim, (_, _, read, answer, (t_in, t_out, secs), waits)) in enumerate(
            zip(claims, CLAIMS), 1):
        for attempt, wait in enumerate(waits, 1):
            emit(LLMWaiting, 0.6 if attempt == 1 else 0.4, question_index=1, role="verify",
                 model=judge_model, seconds=wait, attempt=attempt, reason="rate_limit")
            clock += timedelta(seconds=wait)
        raw = answer if isinstance(answer, str) else json.dumps(answer)
        verdict = judge_with_llm(fake_llm(raw, model=judge_model), claim, [passage(*p) for p in read])
        counts[verdict.verdict] += 1
        emit(ClaimVerified, secs, question_index=1, position=position, total=len(claims),
             verdict=verdict, usage=Usage(calls=1, tokens_in=t_in, tokens_out=t_out,
                                          retries=len(waits), waited_seconds=sum(waits),
                                          seconds=round(secs + sum(waits), 2)))

    total = (clock - START).total_seconds()
    emit(QuestionFinished, question_index=1, verdict_counts=counts, seconds=total)
    emit(RunFinished, summary={"questions": 1, "run_dir": f"runs/{RUN_ID}", "fixture": True},
         seconds=total)

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "events.jsonl", "w", encoding="utf-8") as f:
        f.writelines(e.model_dump_json() + "\n" for e in events)
    print(f"{OUT.relative_to(ROOT)}: {len(events)} events, verdicts {counts}")


if __name__ == "__main__":
    main()
