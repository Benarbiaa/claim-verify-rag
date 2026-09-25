"""
Configuration partagée — chargement du .env et URL de la base
=============================================================

Le .env est chargé ici, une seule fois, pour tous les scripts du package.
load_dotenv n'écrase pas les variables déjà définies : une variable exportée
dans le shell reste prioritaire sur le .env.

Résolution de l'URL de la base, du plus spécifique au plus général :
    --db_url  ->  DB_URL (shell ou .env)
"""

import argparse
import os

from dotenv import load_dotenv

load_dotenv()


def add_db_url_argument(parser: argparse.ArgumentParser) -> None:
    """Ajoute --db_url, facultatif si DB_URL est défini (shell ou .env)."""
    default = os.getenv("DB_URL")
    parser.add_argument(
        "--db_url", type=str, default=default, required=default is None,
        help="URL PostgreSQL, ex. postgresql://rag_user:admin@localhost:5432/ragdb "
             "(défaut : DB_URL dans .env)",
    )
