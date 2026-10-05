"""
Cleaning — repairing text extracted from PDFs, without touching the content
===========================================================================

PDF extraction (pypdf) gives back the layout, not the authors' text: words
split at line ends, ligatures, page numbers in the middle of sentences. This
module repairs ONLY these artifacts. It removes no section (references,
appendices) and never decides what is content: the corpus may grow to
documents no specific rule foresees.

Rules, in this order (PDF only; a Markdown file is written by hand):
    1. page numbers: the last line of a page, if it equals that page's
       number (a table value is never touched)
    2. NFKC: Unicode compatibility forms (ﬁ -> fi, x² -> x2, no-break space -> space)
    3. spaces: tabs and repeated spaces -> one space; line breaks stay
    4. words split at line ends: joined if the document uses the joined word
       elsewhere, otherwise only the line break goes and the hyphen stays
       (cross-encoder, non-parametric)

Guarantee, checked on every document: ignoring spaces, line breaks and
hyphens, the cleaned text equals the raw text (after NFKC), removed page
numbers aside. Otherwise: an error.
"""

import re
import unicodedata
from collections import Counter
from typing import Protocol, runtime_checkable

from claimverify.contracts import CleanedDocument, Document
from claimverify.indexing.loading import PAGE_BREAK

_SPACES = re.compile(r"[^\S\n]+")              # any blank except a line break
_SPACES_AROUND_NEWLINE = re.compile(r" ?\n ?")
_LINE_END_HYPHEN = re.compile(r"(\w+)-\n(\w+)")
_WORD = re.compile(r"\w+(?:-\w+)*")            # a compound word (non-parametric) counts as one


@runtime_checkable
class Cleaner(Protocol):
    """Interface: repairs the text of Documents, without removing content."""

    def clean(self, documents: list[Document]) -> list[CleanedDocument]: ...


class NoCleaner:
    """Implementation: text unchanged (to compare raw and cleaned)."""

    def clean(self, documents: list[Document]) -> list[CleanedDocument]:
        return [CleanedDocument(document=_join_pages(d), characters_before=len(d.text))
                for d in documents]


class MinimalCleaner:
    """Implementation: the 4 repairs above, on PDFs."""

    def clean(self, documents: list[Document]) -> list[CleanedDocument]:
        return [clean_document(d) for d in documents]


def clean_document(doc: Document) -> CleanedDocument:
    if not doc.filename.lower().endswith(".pdf"):
        return CleanedDocument(document=doc, characters_before=len(doc.text))

    pages = doc.text.split(PAGE_BREAK)
    pages, page_numbers = remove_page_numbers(pages)
    raw = "\n".join(pages)

    text = unicodedata.normalize("NFKC", raw)
    nfkc = sum(1 for ch in raw if unicodedata.normalize("NFKC", ch) != ch)
    text = collapse_spaces(text)
    text, joined, kept = rejoin_line_end_hyphens(text)

    check_no_content_lost(raw, text, doc.filename)
    return CleanedDocument(
        document=doc.model_copy(update={"text": text}),
        characters_before=len(doc.text),
        changes={"page_numbers": page_numbers, "nfkc": nfkc,
                 "hyphens_joined": joined, "hyphens_kept": kept},
    )


def remove_page_numbers(pages: list[str]) -> tuple[list[str], int]:
    """Removes the last line of page n if it is exactly n."""
    cleaned, removed = [], 0
    for number, page in enumerate(pages, start=1):
        lines = page.rstrip().split("\n")
        if lines[-1].strip() == str(number):
            lines, removed = lines[:-1], removed + 1
        cleaned.append("\n".join(lines))
    return cleaned, removed


def collapse_spaces(text: str) -> str:
    text = _SPACES.sub(" ", text)
    return _SPACES_AROUND_NEWLINE.sub("\n", text).strip()


def rejoin_line_end_hyphens(text: str) -> tuple[str, int, int]:
    """'rele-\\nvance' -> 'relevance' if 'relevance' appears elsewhere in the
    text (and 'rele-vance' does not); otherwise 'cross-\\nencoder' -> 'cross-encoder'.
    The document itself decides: no dictionary, no assumed language."""
    seen = Counter(w.lower() for w in _WORD.findall(text))
    counts = {"joined": 0, "kept": 0}

    def repair(m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        if seen[(a + b).lower()] and not seen[f"{a}-{b}".lower()]:
            counts["joined"] += 1
            return a + b
        counts["kept"] += 1
        return f"{a}-{b}"

    text = _LINE_END_HYPHEN.sub(repair, text)
    return text, counts["joined"], counts["kept"]


def content_signature(text: str) -> str:
    """The text without what the cleaning is allowed to change."""
    return re.sub(r"[\s-]", "", unicodedata.normalize("NFKC", text))


def check_no_content_lost(raw: str, cleaned: str, filename: str) -> None:
    if content_signature(raw) != content_signature(cleaned):
        raise RuntimeError(f"{filename}: the cleaning changed the content (a bug in cleaning.py).")


def _join_pages(doc: Document) -> Document:
    # Without cleaning, the page separator becomes a plain line break.
    return doc.model_copy(update={"text": doc.text.replace(PAGE_BREAK, "\n")})
