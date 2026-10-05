"""
Loading the corpus — PDF and Markdown to Document
=================================================
"""

import hashlib
from pathlib import Path
from typing import Protocol, runtime_checkable

from pypdf import PdfReader

from claimverify.contracts import Document

# Between two pages: a form feed, not a blank line (which would look like the end
# of a paragraph in the middle of a sentence). The cleaner (cleaning.py) uses it
# to find page numbers, then removes it.
PAGE_BREAK = "\f"


@runtime_checkable
class Loader(Protocol):
    """Interface: reads a corpus and turns it into Documents."""

    def load(self, corpus_dir: Path) -> list[Document]: ...


class FileLoader:
    """Implementation: the PDF and Markdown files of a folder."""

    def load(self, corpus_dir: Path) -> list[Document]:
        return load_corpus(corpus_dir)


def parse_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return PAGE_BREAK.join(pages)


def parse_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_corpus(corpus_dir: Path) -> list[Document]:
    """Reads each PDF or Markdown file of the folder and turns it into a Document."""
    documents = []
    for path in sorted(corpus_dir.iterdir()):
        if path.suffix.lower() == ".pdf":
            text = parse_pdf(path)
            source_type = "peer_reviewed_paper"
        elif path.suffix.lower() == ".md":
            text = parse_markdown(path)
            source_type = "blog_post"  # to adjust if a .md file is not a blog post
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
