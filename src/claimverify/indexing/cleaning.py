"""
Nettoyage — réparer le texte extrait des PDF, sans toucher au contenu
=======================================================================

L'extraction PDF (pypdf) restitue la mise en page, pas le texte des auteurs :
mots coupés en fin de ligne, ligatures, numéros de page au milieu des phrases.
Ce module répare UNIQUEMENT ces artefacts. Il ne retire aucune section
(références, annexes) et ne décide jamais de ce qui est du contenu : le
corpus peut s'élargir à des documents qu'aucune règle spécifique ne prévoit.

Règles, dans cet ordre (PDF seulement ; un Markdown est écrit à la main) :
    1. numéros de page : dernière ligne d'une page, si elle vaut le numéro de
       cette page (une valeur de tableau n'est jamais touchée)
    2. NFKC : formes Unicode de compatibilité (ﬁ -> fi, x² -> x2, espace insécable -> espace)
    3. espaces : tabulations et espaces répétés -> un espace ; les retours à la ligne restent
    4. mots coupés en fin de ligne : recollés si le document contient le mot
       recollé ailleurs, sinon seul le retour à la ligne est retiré et le
       trait d'union reste (cross-encoder, non-parametric)

Garantie, vérifiée à chaque document : en ignorant espaces, retours à la
ligne et traits d'union, le texte nettoyé est identique au texte brut
(après NFKC), numéros de page retirés exceptés. Sinon : erreur.
"""

import re
import unicodedata
from collections import Counter
from typing import Protocol, runtime_checkable

from claimverify.contracts import CleanedDocument, Document
from claimverify.indexing.loading import PAGE_BREAK

_SPACES = re.compile(r"[^\S\n]+")              # tout blanc sauf le retour à la ligne
_SPACES_AROUND_NEWLINE = re.compile(r" ?\n ?")
_LINE_END_HYPHEN = re.compile(r"(\w+)-\n(\w+)")
_WORD = re.compile(r"\w+(?:-\w+)*")            # un mot composé (non-parametric) compte pour un


@runtime_checkable
class Cleaner(Protocol):
    """Interface : répare le texte des Documents, sans en retirer le contenu."""

    def clean(self, documents: list[Document]) -> list[CleanedDocument]: ...


class NoCleaner:
    """Implémentation : texte inchangé (pour comparer brut et nettoyé)."""

    def clean(self, documents: list[Document]) -> list[CleanedDocument]:
        return [CleanedDocument(document=_join_pages(d), characters_before=len(d.text))
                for d in documents]


class MinimalCleaner:
    """Implémentation : les 4 réparations ci-dessus, sur les PDF."""

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
    """Retire la dernière ligne de la page n si elle vaut exactement n."""
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
    """'rele-\\nvance' -> 'relevance' si 'relevance' apparaît ailleurs dans le
    texte (et pas 'rele-vance') ; sinon 'cross-\\nencoder' -> 'cross-encoder'.
    Le document lui-même tranche : aucun dictionnaire, aucune langue supposée."""
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
    """Le texte sans ce que le nettoyage a le droit de changer."""
    return re.sub(r"[\s-]", "", unicodedata.normalize("NFKC", text))


def check_no_content_lost(raw: str, cleaned: str, filename: str) -> None:
    if content_signature(raw) != content_signature(cleaned):
        raise RuntimeError(f"{filename} : le nettoyage a modifié le contenu (bug dans cleaning.py).")


def _join_pages(doc: Document) -> Document:
    # Sans nettoyage, le séparateur de pages devient un simple retour à la ligne.
    return doc.model_copy(update={"text": doc.text.replace(PAGE_BREAK, "\n")})
