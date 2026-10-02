"""
Chargement du corpus — PDF et Markdown vers Document
======================================================
"""

import hashlib
from pathlib import Path
from typing import Protocol, runtime_checkable

from pypdf import PdfReader

from claimverify.contracts import Document

# Entre deux pages : un saut de page, pas une ligne vide (qui ressemblerait à
# une fin de paragraphe au milieu d'une phrase). Le nettoyage (cleaning.py)
# s'en sert pour repérer les numéros de page, puis le retire.
PAGE_BREAK = "\f"


@runtime_checkable
class Loader(Protocol):
    """Interface : lit un corpus et le convertit en Documents."""

    def load(self, corpus_dir: Path) -> list[Document]: ...


class FileLoader:
    """Implémentation : fichiers PDF et Markdown d'un dossier."""

    def load(self, corpus_dir: Path) -> list[Document]:
        return load_corpus(corpus_dir)


def parse_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return PAGE_BREAK.join(pages)


def parse_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_corpus(corpus_dir: Path) -> list[Document]:
    """Lit chaque fichier PDF ou Markdown du dossier et le convertit en Document."""
    documents = []
    for path in sorted(corpus_dir.iterdir()):
        if path.suffix.lower() == ".pdf":
            text = parse_pdf(path)
            source_type = "peer_reviewed_paper"
        elif path.suffix.lower() == ".md":
            text = parse_markdown(path)
            source_type = "blog_post"  # à ajuster si le .md n'est pas un article de blog
        else:
            continue

        doc_id = hashlib.sha1(path.name.encode()).hexdigest()[:12]
        documents.append(Document(
            doc_id=doc_id,
            filename=path.name,
            source_type=source_type,
            text=text,
        ))
    return documents
