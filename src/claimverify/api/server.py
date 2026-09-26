"""
Lancer l'interface
==================

    python -m claimverify.api.server                  runs/ + interface sur http://127.0.0.1:8000
    python -m claimverify.api.server --fixtures       ajoute les runs de test (verdict "contested")
    python -m claimverify.api.server --no-live        rejeu seulement : aucun appel LLM possible

Pendant le développement de l'interface : `npm run dev` dans ui/ (Vite
redirige /api vers ce serveur).
"""

import argparse
from pathlib import Path

import uvicorn

import claimverify.config  # noqa: F401  (charge .env : clés API et DB_URL pour le mode direct)
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
                        help=f"Affiche aussi les runs de test de {FIXTURES_DIR}.")
    parser.add_argument("--no-live", action="store_true",
                        help="Désactive le mode direct (aucun appel LLM depuis l'interface).")
    args = parser.parse_args()

    roots = {"recorded": args.runs_dir}
    if args.fixtures:
        roots["fixture"] = FIXTURES_DIR
    live = None if args.no_live else LiveRunner(Path.cwd(), args.runs_dir)
    app = create_app(RunStore(roots), live, ui_dist=Path("ui/dist"))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
