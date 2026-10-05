"""
Starting the UI
===============

    python -m claimverify.api.server                  runs/ + the UI on http://127.0.0.1:8000
    python -m claimverify.api.server --fixtures       adds the test runs (verdict "contested")
    python -m claimverify.api.server --no-live        replay only: no LLM call possible

While developing the UI: `npm run dev` in ui/ (Vite forwards /api to this
server).
"""

import argparse
from pathlib import Path

import uvicorn

import claimverify.config  # noqa: F401  (loads .env: API keys and DB_URL for live runs)
from claimverify.api.app import create_app
from claimverify.api.live import LiveRunner
from claimverify.api.runs import RunStore
from claimverify.reporting import RUNS_DIR

FIXTURES_DIR = Path("tests/fixtures/runs")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--runs_dir", type=Path, default=RUNS_DIR)
    parser.add_argument("--fixtures", action="store_true",
                        help=f"Also lists the test runs of {FIXTURES_DIR}.")
    parser.add_argument("--no-live", action="store_true",
                        help="Disables live runs (no LLM call from the UI).")
    args = parser.parse_args()

    roots = {"recorded": args.runs_dir}
    if args.fixtures:
        roots["fixture"] = FIXTURES_DIR
    live = None if args.no_live else LiveRunner(Path.cwd(), args.runs_dir)
    app = create_app(RunStore(roots), live, ui_dist=Path("ui/dist"))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
