"""
Shared configuration — loading .env and the database URL
========================================================

.env is loaded here, once, for every script of the package. load_dotenv does
not overwrite variables that are already set: a variable exported in the
shell takes precedence over .env.

Database URL, from the most specific to the most general:
    --db_url  ->  DB_URL (shell or .env)
"""

import argparse
import os

from dotenv import load_dotenv

load_dotenv()


def add_db_url_argument(parser: argparse.ArgumentParser) -> None:
    """Adds --db_url, optional when DB_URL is set (shell or .env)."""
    default = os.getenv("DB_URL")
    parser.add_argument(
        "--db_url", type=str, default=default, required=default is None,
        help="PostgreSQL URL, e.g. postgresql://rag_user:admin@localhost:5432/ragdb "
             "(default: DB_URL in .env)",
    )
