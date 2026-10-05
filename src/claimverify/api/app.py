"""
The UI's API — recorded runs, and live runs
===========================================

    GET  /api/runs                  the list of runs (summaries)
    GET  /api/runs/{run_id}         one run: summary, all its events, report metadata
    GET  /api/live                  what to know before starting (configs, estimated cost)
    POST /api/live                  runs the real pipeline on a question (LLM calls!)
    GET  /api/live/{run_id}/stream  the events of a live run, as Server-Sent Events

Replaying a recorded run happens entirely in the browser, from its events: no
API call. Only POST /api/live calls the LLMs.

If ui/dist exists (npm run build), the UI is served from the same address.
"""

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from claimverify.api.live import LiveBusy, LiveRunner, LiveUnavailable
from claimverify.api.runs import RunStore

KEEPALIVE_SECONDS = 15  # a regular SSE comment: a 60 s wait does not drop the connection


class LiveRequest(BaseModel):
    question: str
    config_file: str = "config.yaml"


def create_app(store: RunStore, live: LiveRunner | None = None, ui_dist: Path | None = None) -> FastAPI:
    app = FastAPI(title="claim-verify-rag")

    def with_live_status(summary: dict) -> dict:
        run = live.runs.get(summary["run_id"]) if live else None
        if run and summary.get("status") != "finished":
            summary = summary | {"status": run.status, "error": run.error}
        return summary

    @app.get("/api/runs")
    def list_runs() -> list[dict]:
        return [with_live_status(store.summary(f)) for f in store.folders()]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        folder = store.find(run_id)
        if not folder:
            raise HTTPException(404, f"No run named {run_id}")
        try:
            detail = store.detail(folder)
        except ValueError as e:
            raise HTTPException(422, f"events.jsonl could not be read: {str(e).splitlines()[0]}") from e
        detail["summary"] = with_live_status(detail["summary"])
        return detail

    @app.get("/api/live")
    def live_info() -> dict:
        if not live:
            return {"enabled": False}
        summaries = [store.summary(f) for f in store.folders()]
        return {"enabled": True, **live.info(summaries)}

    @app.post("/api/live", status_code=201)
    def start_live(request: LiveRequest) -> dict:
        if not live:
            raise HTTPException(403, "Live mode is disabled on this server.")
        try:
            run = live.start(request.question, request.config_file)
        except LiveBusy as e:
            raise HTTPException(409, str(e)) from e
        except LiveUnavailable as e:
            raise HTTPException(400, str(e)) from e
        return {"run_id": run.run_id}

    @app.get("/api/live/{run_id}/stream")
    async def stream_live(run_id: str, request: Request) -> StreamingResponse:
        run = live.runs.get(run_id) if live else None
        if not run:
            raise HTTPException(404, f"No live run named {run_id}")

        async def messages():
            backlog, queue = run.subscribe(asyncio.get_running_loop())
            try:
                for message in backlog:
                    yield message
                closed = any(m.startswith(("event: end", "event: failed")) for m in backlog)
                while not closed:
                    if await request.is_disconnected():
                        break
                    try:
                        message = await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
                    except TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    yield message
                    closed = message.startswith(("event: end", "event: failed"))
            finally:
                run.unsubscribe(queue)

        return StreamingResponse(messages(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    if ui_dist and (ui_dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=ui_dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            file = (ui_dist / path).resolve()
            if path and file.is_file() and ui_dist.resolve() in file.parents:
                return FileResponse(file)
            return FileResponse(ui_dist / "index.html")  # the UI's own routes (/runs/...)

    return app
