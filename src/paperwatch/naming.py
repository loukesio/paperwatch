"""Turn paper metadata into a safe, cross-platform file name."""

from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path

from paperwatch.lookup import Paper

DEFAULT_TEMPLATE = "{author}_{year}_{title}"
DEFAULT_SPACE = " "

# Characters illegal on Windows (the strictest of the three OSes) plus control chars.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def clean_text(s: str, ascii_only: bool = False) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")  # Crossref titles may contain <i>, <sub>, mathml...
    s = html.unescape(s)
    s = unicodedata.normalize("NFC", s)
    if ascii_only:
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.replace(":", " -").replace("/", "-")
    s = _ILLEGAL.sub("", s)
    return " ".join(s.split())


def respace(s: str, space: str) -> str:
    """Replace the spaces inside a field: "Array programming" -> "Array-programming"."""
    if space == " ":
        return s
    s = s.replace(" & ", " and ")
    s = re.sub(r"\s+-\s+", " ", s)  # "Title - subtitle" (from a colon) -> "Title subtitle"
    s = re.sub(r"\s+", space, s)
    if space:
        s = re.sub(f"(?:{re.escape(space)}){{2,}}", space, s)
    return s


def format_authors(authors: list[str]) -> str:
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]} & {authors[1]}"
    return f"{authors[0]} et al."


def build_name(paper: Paper, template: str = DEFAULT_TEMPLATE, max_length: int = 150,
               ascii_only: bool = False, space: str = DEFAULT_SPACE) -> str:
    """Return the new file stem (no extension).

    `space` replaces spaces inside the fields (" " keeps them); separators written in the
    template itself are left as they are.
    """
    space = _ILLEGAL.sub("", space)
    fields = {
        "author": paper.authors[0] if paper.authors else "",
        "authors": format_authors(paper.authors),
        "year": paper.year,
        "title": paper.title,
        "journal": paper.journal,
        "doi": paper.doi.replace("/", "_"),
        "arxiv": paper.arxiv.replace("/", "_"),
    }
    fields = {k: respace(clean_text(v, ascii_only), space) for k, v in fields.items()}
    name = template.format(**fields)

    # Collapse separators left behind by empty fields, e.g. "Smith__Title" -> "Smith_Title"
    # and "Smith - - Title" -> "Smith - Title".
    name = re.sub(r"(\s*[_\-]\s*)(?:[_\-]\s*)+", lambda m: m.group(1), name)
    name = re.sub(r"\s{2,}", " ", name)
    name = re.sub(r"\s*_\s*", "_", name).strip(" _-.")

    if len(name) > max_length:
        cut = name[:max_length]
        # cut at the last word boundary, if there is one in the second half
        boundary = max(cut.rfind(" "), cut.rfind(space) if space else -1)
        if boundary > max_length // 2:
            cut = cut[:boundary]
        name = cut.rstrip(" _-.,")
    if name.upper() in _WINDOWS_RESERVED:
        name = f"_{name}"
    return name


def unique_path(target: Path, current: Path | None = None) -> Path:
    """Avoid clobbering an existing file: "name.pdf" -> "name (2).pdf"."""
    if not target.exists() or (current is not None and _same_file(target, current)):
        return target
    i = 2
    while True:
        cand = target.with_name(f"{target.stem} ({i}){target.suffix}")
        if not cand.exists():
            return cand
        i += 1


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve() or a.samefile(b)
    except OSError:
        return False
