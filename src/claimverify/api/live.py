"""
Live runs — running the real pipeline from the UI
=================================================

The pipeline runs in a thread, with the existing code: factory.build_answering
and pipeline.run_single_question. One more sink (BroadcastSink) sends each
event to the subscribed browsers (Server-Sent Events, see app.py), next to the
terminal and events.jsonl: a live run is recorded like any other, and replays
later with no API call.

One live run at a time: Groq's free-tier limits are tight, and two runs in
parallel would share the same per-minute limit.
"""

import asyncio
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import openai
import psycopg2

from claimverify.answering.pipeline import build_markdown_report, describe_llm_stage, run_single_question
from claimverify.components.embedding import Embedder
from claimverify.events import Event, RunFinished, RunStarted
from claimverify.factory import build_answering, build_embedder
from claimverify.llm import LLMCallError
from claimverify.reporting import ConsoleSink, RecorderSink, Run
from claimverify.settings import Settings, load_settings

# Fallback when no recorded run can measure what a question costs.
DEFAULT_TOKENS_PER_QUESTION = 50_000
# Daily limit measured on this project (docs/design.md, section 8): it is what
# bounds the number of questions per day on the free tier.
DAILY_LIMIT_NOTE = "Groq free tier: the judge model (qwen/qwen3.8-27b) allows 200,000 tokens per day."


class LiveBusy(RuntimeError):
    """A live run is already in progress."""


class LiveUnavailable(RuntimeError):
    """The run cannot start (API key, database, config): a message for the user."""


@dataclass
class LiveRun:
    run_id: str
    question: str
    status: str = "running"            # running, finished, failed
    error: dict | None = None          # {"kind", "message"} when failed
    backlog: list[str] = field(default_factory=list)  # SSE messages already sent
    subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def publish(self, kind: str, data: dict) -> None:
        """Called from the pipeline's thread: keeps the message and sends it to subscribers."""
        message = f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        with self.lock:
            self.backlog.append(message)
            for loop, queue in self.subscribers:
                loop.call_soon_threadsafe(queue.put_nowait, message)

    def subscribe(self, loop: asyncio.AbstractEventLoop) -> tuple[list[str], asyncio.Queue]:
        """The messages already sent, and a queue for the next ones (no gap, no duplicate)."""
        queue: asyncio.Queue = asyncio.Queue()
        with self.lock:
            self.subscribers.append((loop, queue))
            return list(self.backlog), queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self.lock:
            self.subscribers = [(lp, q) for lp, q in self.subscribers if q is not queue]

    @property
    def done(self) -> bool:
        return self.status != "running"


class BroadcastSink:
    """Sink: each event of the run goes to the subscribed browsers."""

    def __init__(self, live: LiveRun):
        self.live = live

    def handle(self, event: Event) -> None:
        self.live.publish("pipeline", event.model_dump(mode="json"))


def describe_failure(error: Exception) -> dict:
    """A clear message for the UI, depending on what stopped the run."""
    cause = error.__cause__
    status = getattr(cause, "status_code", None)
    if isinstance(error, LLMCallError) and status == 413:
        return {"kind": "request_too_large",
                "message": "A request was larger than the provider's per-minute token limit. "
                           "Lower top_k_per_doc in the config and try again."}
    if isinstance(error, LLMCallError) and status == 429:
        return {"kind": "daily_limit",
                "message": "The provider asked to wait longer than max_wait_seconds, which "
                           "usually means the daily limit is reached. Try again later."}
    if isinstance(error, LLMCallError):
        return {"kind": "gave_up", "message": "An LLM call kept failing and the run gave up: "
                                              f"{cause or error}"}
    if isinstance(error, openai.APIError):
        return {"kind": "provider_error", "message": f"The provider rejected a request: {error}"}
    if isinstance(error, psycopg2.Error):
        return {"kind": "database", "message": f"Database error: {str(error).strip()}"}
    return {"kind": "unexpected", "message": f"{type(error).__name__}: {error}"}


class LiveRunner:
    def __init__(self, project_root: Path, runs_dir: Path, db_url: str | None = None):
        self.project_root = project_root
        self.runs_dir = runs_dir
        self.db_url = db_url if db_url is not None else os.getenv("DB_URL")
        self.runs: dict[str, LiveRun] = {}
        self._embedders: dict[tuple, Embedder] = {}  # the model loads only once
        self._lock = threading.Lock()

    # --- what the UI shows before starting ---------------------------------------------

    def config_files(self) -> list[str]:
        files = [p for p in [self.project_root / "config.yaml"] if p.exists()]
        files += sorted((self.project_root / "experiments").glob("*.yaml"))
        return [str(p.relative_to(self.project_root)) for p in files]

    def info(self, recorded_summaries: list[dict]) -> dict:
        per_question = [
            (s["usage"]["tokens_in"] + s["usage"]["tokens_out"]) / len(s["questions"])
            for s in recorded_summaries
            if s.get("pipeline") == "answering" and s.get("status") == "finished"
            and s.get("source") == "recorded" and s.get("questions")
        ]
        configs = []
        for name in self.config_files():
            try:
                settings = load_settings(self.project_root / name)
            except Exception as e:  # noqa: BLE001 (invalid config: shown, not runnable)
                configs.append({"file": name, "error": str(e).splitlines()[0]})
                continue
            configs.append({"file": name, "models": _models(settings),
                            "missing_keys": _missing_keys(settings)})
        running = next((r for r in self.runs.values() if not r.done), None)
        return {
            "configs": configs,
            "database_configured": bool(self.db_url),
            "estimate": {
                "tokens_per_question": round(sum(per_question) / len(per_question))
                if per_question else DEFAULT_TOKENS_PER_QUESTION,
                "basis_runs": len(per_question),
                "daily_limit_note": DAILY_LIMIT_NOTE,
            },
            "running": running.run_id if running else None,
        }

    # --- starting a run ---------------------------------------------------------------

    def start(self, question: str, config_file: str) -> LiveRun:
        question = question.strip()
        if not question:
            raise LiveUnavailable("Type a question first.")
        if config_file not in self.config_files():
            raise LiveUnavailable(f"Unknown config file: {config_file}")
        with self._lock:
            if any(not r.done for r in self.runs.values()):
                raise LiveBusy("A live run is already in progress. Wait for it to finish.")
            settings = load_settings(self.project_root / config_file)
            missing = _missing_keys(settings)
            if missing:
                raise LiveUnavailable(f"Missing API key(s) in .env: {', '.join(missing)}")
            if not self.db_url:
                raise LiveUnavailable("DB_URL is not set in .env.")
            try:
                conn = psycopg2.connect(self.db_url)
            except psycopg2.Error as e:
                raise LiveUnavailable("Cannot reach the database. Is it running "
                                      f"(docker compose up -d)? {str(e).strip()}") from e
            try:
                stages = build_answering(settings, conn, embedder=self._embedder(settings))
            except Exception as e:
                conn.close()
                raise LiveUnavailable(str(e)) from e

            run = Run("answering", runs_dir=self.runs_dir, sinks=[])
            live = LiveRun(run.run_id, question)
            run.sinks = [ConsoleSink(), RecorderSink(run.events_path), BroadcastSink(live)]
            self.runs[run.run_id] = live
        threading.Thread(target=self._run, name=f"live-{run.run_id}", daemon=True,
                         args=(live, run, stages, settings, config_file, conn)).start()
        return live

    def _run(self, live: LiveRun, run: Run, stages, settings: Settings, config_file: str, conn) -> None:
        # Same flow as pipeline.main(), for one question.
        start = time.perf_counter()
        try:
            run.emit(RunStarted, config=settings.model_dump(),
                     inputs={"config_file": config_file, "questions": [live.question]})
            result = run_single_question(live.question, stages, run, question_index=1)
            metadata = _report_metadata(run, settings, config_file, stages)
            with open(run.dir / "report.json", "w", encoding="utf-8") as f:
                json.dump({"metadata": metadata, "results": [result]}, f, ensure_ascii=False, indent=2)
            with open(run.dir / "report.md", "w", encoding="utf-8") as f:
                f.write(build_markdown_report([result], metadata))
            run.emit(RunFinished, seconds=time.perf_counter() - start,
                     summary={"questions": 1, "run_dir": str(run.dir)})
            live.status = "finished"
            live.publish("end", {"status": "finished"})
        except Exception as e:  # noqa: BLE001 (any stop must reach the browser)
            live.error = describe_failure(e)
            live.status = "failed"
            live.publish("failed", live.error)
        finally:
            stages.meter.on_wait = None
            conn.close()

    def _embedder(self, settings: Settings) -> Embedder:
        key = (settings.embedding.type, settings.embedding.model, settings.embedding.device)
        if key not in self._embedders:
            self._embedders[key] = build_embedder(settings)
        return self._embedders[key]


def _llm_stages(settings: Settings) -> dict:
    a = settings.answering
    return {"draft": a.drafter, "decompose": a.decomposer, "verify": a.verifier.judge}


def _models(settings: Settings) -> dict:
    return {role: stage.model for role, stage in _llm_stages(settings).items()}


def _missing_keys(settings: Settings) -> list[str]:
    envs = {settings.providers[s.provider].api_key_env for s in _llm_stages(settings).values()}
    return sorted(env for env in envs if not os.getenv(env))


def _report_metadata(run: Run, settings: Settings, config_file: str, stages) -> dict:
    # The same fields pipeline.main() writes to report.json.
    a = settings.answering
    return {
        "timestamp": run.run_id,
        "config_file": config_file,
        "models": {role: describe_llm_stage(settings, stage)
                   for role, stage in _llm_stages(settings).items()},
        "embedding_model": settings.embedding.model,
        "draft_top_k_per_doc": a.retriever.top_k_per_doc,
        "verify_top_k_per_doc": a.verifier.retriever.top_k_per_doc,
        "config": settings.model_dump(),
        "usage": {role: u.model_dump() for role, u in stages.meter.totals_by_role().items()},
    }
