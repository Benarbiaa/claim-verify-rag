"""
Lecture des dossiers de runs — ce que l'interface affiche
===========================================================

Un run est un dossier runs/<run_id>/ (voir reporting.py) : events.jsonl, et
pour le pipeline de réponse report.json. Ce module ne fait que les relire :
aucune logique du pipeline ici, seulement des résumés (verdicts, tokens,
durées) calculés à partir des événements enregistrés.

Plusieurs racines sont possibles, chacune avec sa "source" : "recorded" pour
les vrais runs (runs/), "fixture" pour les runs de test construits par
tests/fixtures/ (affichés comme tels dans l'interface).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from claimverify.events import Event
from claimverify.reporting import load_events

RUN_ID = re.compile(r"^\d{8}_\d{6}_(indexing|answering)$")
STAGE_TYPES = ("passages_retrieved", "draft_written", "claims_extracted", "claim_verified")


@dataclass(frozen=True)
class RunFolder:
    run_id: str
    path: Path
    source: str  # "recorded" ou "fixture"


class RunStore:
    """Les runs de une ou plusieurs racines ; relus seulement quand le fichier change."""

    def __init__(self, roots: dict[str, Path]):
        self.roots = roots  # source -> dossier
        self._cache: dict[Path, tuple[tuple[float, int], list[Event]]] = {}

    def folders(self) -> list[RunFolder]:
        found = []
        for source, root in self.roots.items():
            if root.is_dir():
                found += [RunFolder(p.name, p, source) for p in root.iterdir()
                          if p.is_dir() and RUN_ID.match(p.name) and (p / "events.jsonl").exists()]
        return sorted(found, key=lambda f: f.run_id, reverse=True)

    def find(self, run_id: str) -> RunFolder | None:
        return next((f for f in self.folders() if f.run_id == run_id), None)

    def events(self, folder: RunFolder) -> list[Event]:
        path = folder.path / "events.jsonl"
        stat = path.stat()
        key = (stat.st_mtime, stat.st_size)
        cached = self._cache.get(path)
        if cached and cached[0] == key:
            return cached[1]
        events = load_events(path)
        self._cache[path] = (key, events)
        return events

    def summary(self, folder: RunFolder) -> dict:
        try:
            return summarize(folder, self.events(folder))
        except (ValueError, OSError) as e:  # ligne illisible, fichier disparu...
            return {"run_id": folder.run_id, "source": folder.source,
                    "pipeline": folder.run_id.rsplit("_", 1)[1], "status": "unreadable",
                    "error": str(e).splitlines()[0]}

    def detail(self, folder: RunFolder) -> dict:
        events = self.events(folder)
        report = folder.path / "report.json"
        metadata = None
        if report.exists():
            with open(report, encoding="utf-8") as f:
                metadata = json.load(f).get("metadata")
        return {
            "summary": summarize(folder, events),
            "events": [e.model_dump(mode="json") for e in events],
            "report": metadata,
        }


def summarize(folder: RunFolder, events: list[Event]) -> dict:
    """Le résumé d'un run pour la liste : type, questions, verdicts, durée, tokens."""
    first = events[0] if events else None
    finished = next((e for e in events if e.type == "run_finished"), None)
    started = first.type == "run_started" if first else False
    usage = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "retries": 0, "waited_seconds": 0.0}
    for e in events:
        if e.type in STAGE_TYPES:
            for name in usage:
                usage[name] += getattr(e.usage, name)
    usage["waited_seconds"] = round(usage["waited_seconds"], 2)

    if finished:
        seconds = finished.seconds
    elif len(events) > 1:
        seconds = (events[-1].time - events[0].time).total_seconds()
    else:
        seconds = 0.0

    summary = {
        "run_id": folder.run_id,
        "source": folder.source,
        "pipeline": folder.run_id.rsplit("_", 1)[1],
        "status": "finished" if finished else "incomplete",
        "started_at": first.time.isoformat() if first else None,
        "seconds": round(seconds, 2),
        "config_file": first.inputs.get("config_file") if started else None,
        "usage": usage,
        "event_count": len(events),
    }
    if summary["pipeline"] == "answering":
        counts: dict[str, int] = {}
        for e in events:
            if e.type == "claim_verified":
                counts[e.verdict.verdict] = counts.get(e.verdict.verdict, 0) + 1
        summary |= {
            "questions": [e.question for e in events if e.type == "question_started"],
            "verdict_counts": counts,
            "claims": sum(len(e.claims) for e in events if e.type == "claims_extracted"),
        }
    else:
        docs = next((e for e in events if e.type == "documents_loaded"), None)
        built = next((e for e in events if e.type == "chunks_built"), None)
        summary |= {
            "corpus_dir": first.inputs.get("corpus_dir") if started else None,
            "documents": len(docs.documents) if docs else None,
            "chunks": len(built.chunks) if built else None,
        }
    return summary
