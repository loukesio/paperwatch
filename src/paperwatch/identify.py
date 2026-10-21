"""Find identifiers (DOI / arXiv ID) and a candidate title inside a PDF."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# DOI: "10." + registrant code + "/" + suffix. The suffix may contain almost anything,
# so we stop at whitespace and quote/angle characters and trim trailing punctuation after.
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>{}|\\^`]+)", re.IGNORECASE)

# New-style arXiv IDs (2007+): 2401.12345 or 0704.0001, optional version.
ARXIV_NEW = r"\d{4}\.\d{4,5}(?:v\d+)?"
# Old-style arXiv IDs: hep-th/9901001, math.GT/0309136
ARXIV_OLD = r"[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?"

# The vertical stamp arXiv adds to every PDF: "arXiv:2401.12345v2 [cs.LG] 3 Jan 2024"
ARXIV_STAMP_RE = re.compile(rf"arXiv:\s*({ARXIV_NEW}|{ARXIV_OLD})\s*\[[^\]]+\]", re.IGNORECASE)
ARXIV_TEXT_RE = re.compile(rf"arXiv:\s*({ARXIV_NEW}|{ARXIV_OLD})", re.IGNORECASE)
ARXIV_FILENAME_RE = re.compile(rf"^(?:arxiv[_\-. ]?)?({ARXIV_NEW})$", re.IGNORECASE)

# Titles that PDF producers put in the metadata but that are not real titles.
_JUNK_TITLE_RE = re.compile(
    r"(^untitled|^microsoft (word|powerpoint)|\.(docx?|tex|dvi|pdf|indd|qxd)\b|^layout \d|"
    r"^paper$|^article$|^manuscript|^pii:|^doi:|^s\d{4}-|^\d+$)",
    re.IGNORECASE,
)


@dataclass
class Identifiers:
    doi: Optional[str] = None
    arxiv: Optional[str] = None
    title_guess: Optional[str] = None
    source: str = ""  # where the ID was found, for logging


def clean_doi(raw: str) -> str:
    doi = raw.strip()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.IGNORECASE)
    # Trim trailing punctuation that is almost never part of a DOI.
    doi = doi.rstrip(".,;:'’”")
    # Drop unbalanced closing brackets, e.g. "(doi:10.1000/xyz)".
    for open_c, close_c in ("()", "[]"):
        while doi.endswith(close_c) and doi.count(close_c) > doi.count(open_c):
            doi = doi[:-1]
    return doi


def strip_arxiv_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id)


def find_doi(text: str) -> Optional[str]:
    m = DOI_RE.search(text or "")
    return clean_doi(m.group(1)) if m else None


def find_arxiv(text: str, stamp_only: bool = False) -> Optional[str]:
    rx = ARXIV_STAMP_RE if stamp_only else ARXIV_TEXT_RE
    m = rx.search(text or "")
    return m.group(1) if m else None


def arxiv_from_filename(path: Path) -> Optional[str]:
    m = ARXIV_FILENAME_RE.match(path.stem.strip())
    return m.group(1) if m else None


def _metadata_strings(reader) -> list[str]:
    out: list[str] = []
    try:
        meta = reader.metadata or {}
        for key in ("/doi", "/DOI", "/prism:doi", "/Subject", "/Keywords", "/WPS-ARTICLEDOI"):
            val = meta.get(key)
            if val:
                out.append(str(val))
    except Exception as e:  # malformed metadata is common
        log.debug("metadata read failed: %s", e)
    try:
        xmp = reader.xmp_metadata
        if xmp is not None:
            out.append(xmp.rdf_root.toxml() if hasattr(xmp, "rdf_root") else str(xmp))
    except Exception as e:
        log.debug("xmp read failed: %s", e)
    return out


def _metadata_title(reader) -> Optional[str]:
    try:
        title = (reader.metadata or {}).get("/Title")
    except Exception:
        return None
    if not title:
        return None
    title = " ".join(str(title).split())
    if len(title) < 15 or len(title.split()) < 3 or _JUNK_TITLE_RE.search(title):
        return None
    return title


def _largest_font_text(page) -> Optional[str]:
    """Best-effort: the text drawn with the biggest font on page 1 is usually the title."""
    chunks: list[tuple[float, str]] = []

    def visitor(text, cm, tm, font_dict, font_size):
        if not text or not text.strip():
            return
        try:
            size = abs(float(font_size) * float(tm[3]) * float(cm[3]))
        except Exception:
            return
        chunks.append((round(size, 1), text))

    try:
        page.extract_text(visitor_text=visitor)
    except Exception:
        return None
    if not chunks:
        return None
    biggest = max(s for s, _ in chunks)
    title = " ".join(t.strip() for s, t in chunks if s >= biggest - 0.5)
    title = " ".join(title.split())
    if len(title) < 15 or len(title) > 300 or len(title.split()) < 3:
        return None
    return title


def identify(path: Path, max_pages: int = 2) -> Identifiers:
    """Extract the best identifier we can find. Order of trust:

    1. DOI in PDF metadata / XMP
    2. arXiv ID in the file name (e.g. "2401.12345v2.pdf")
    3. arXiv stamp on page 1 ("arXiv:2401.12345v2 [cs.LG] ...")
    4. first DOI in the text of page 1, then page 2
    5. any arXiv ID in the text
    6. otherwise a title guess (metadata title or largest text on page 1) for a search
    """
    from pypdf import PdfReader

    ids = Identifiers()
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            log.info("%s is encrypted; only checking the file name", path.name)
            ids.arxiv = arxiv_from_filename(path)
            ids.source = "filename" if ids.arxiv else ""
            return ids

    for s in _metadata_strings(reader):
        doi = find_doi(s)
        if doi:
            ids.doi, ids.source = doi, "pdf metadata"
            return ids

    arx = arxiv_from_filename(path)
    if arx:
        ids.arxiv, ids.source = arx, "filename"
        return ids

    texts: list[str] = []
    for i, page in enumerate(reader.pages[:max_pages]):
        try:
            texts.append(page.extract_text() or "")
        except Exception as e:
            log.debug("text extraction failed on page %d: %s", i + 1, e)
            texts.append("")

    if texts:
        arx = find_arxiv(texts[0], stamp_only=True)
        if arx:
            ids.arxiv, ids.source = arx, "arXiv stamp"
            return ids

    for i, text in enumerate(texts):
        doi = find_doi(text)
        if doi:
            ids.doi, ids.source = doi, f"text of page {i + 1}"
            return ids

    for i, text in enumerate(texts):
        arx = find_arxiv(text)
        if arx:
            ids.arxiv, ids.source = arx, f"text of page {i + 1}"
            return ids

    ids.title_guess = _metadata_title(reader)
    if not ids.title_guess and reader.pages:
        ids.title_guess = _largest_font_text(reader.pages[0])
    if ids.title_guess:
        ids.source = "title guess"
    return ids
