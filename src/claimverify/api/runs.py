"""
Reading run folders — what the UI shows
=======================================

A run is a folder runs/<run_id>/ (see reporting.py): events.jsonl, plus
report.json for the answering pipeline. This module only reads them back: no
pipeline logic here, only summaries (verdicts, tokens, durations) computed
from the recorded events.

Several roots are possible, each with its "source": "recorded" for real runs
(runs/), "fixture" for the test runs built by tests/fixtures/ (shown as such
in the UI).
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
    source: str  # "recorded" or "fixture"


class RunStore:
    """The runs of one or more roots; read again only when the file changes."""

    def __init__(self, roots: dict[str, Path]):
        self.roots = roots  # source -> folder
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
        except (ValueError, OSError) as e:  # unreadable line, file gone...
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
    """A run's summary for the list: type, questions, verdicts, duration, tokens."""
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
