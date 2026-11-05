"""Find identifiers (DOI / arXiv ID) and a candidate title inside a PDF."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
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
    r"^paper$|^article$|^manuscript|^pii:|^doi:|^s\d{4}-|^\d+$|"
    r"graphics output|^rplots?\b|^figure\b|^fig\.?\s*\d|^plot\b|^chart\b|^page\.html$)",
    re.IGNORECASE,
)

# PDFs written by plotting libraries are figures, never papers. R's pdf() device sets
# Creator "R" / Producer "R 4.x.y" / Title "R Graphics Output"; ggsave()/cairo_pdf() and
# many Python tools write through cairo; matplotlib names itself.
_PLOT_PRODUCER_RE = re.compile(
    r"^R(\s+\d[\d.]*)?$|matplotlib|^cairo\b|plotly|kaleido|gnuplot|graphpad|bokeh|"
    r"seaborn|^vega|^ggplot",
    re.IGNORECASE,
)

# How many different DOIs / arXiv IDs from the page text we are willing to try.
MAX_TEXT_CANDIDATES = 5


@dataclass
class Identifiers:
    doi: Optional[str] = None
    arxiv: Optional[str] = None
    title_guess: Optional[str] = None
    source: str = ""  # where the ID was found, for logging
    # Set when the file is clearly not a paper (e.g. an R / matplotlib figure).
    skip_reason: str = ""
    # IDs found in the page text. A DOI in the text may belong to a cited paper rather
    # than to this one, so these must be checked against `text` before renaming.
    text_dois: list[str] = field(default_factory=list)
    text_arxivs: list[str] = field(default_factory=list)
    text: str = ""


def clean_doi(raw: str) -> str:
    doi = raw.strip()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.IGNORECASE)
    # Trim trailing punctuation that is almost never part of a DOI.
    doi = doi.rstrip(".,;:'’”/")
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


def find_all_dois(text: str, limit: int = MAX_TEXT_CANDIDATES) -> list[str]:
    out: list[str] = []
    for m in DOI_RE.finditer(text or ""):
        doi = clean_doi(m.group(1))
        if doi and doi.lower() not in (d.lower() for d in out):
            out.append(doi)
            if len(out) >= limit:
                break
    return out


def find_all_arxivs(text: str, limit: int = MAX_TEXT_CANDIDATES) -> list[str]:
    out: list[str] = []
    for m in ARXIV_TEXT_RE.finditer(text or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
            if len(out) >= limit:
                break
    return out


def figure_reason(reader) -> str:
    """Non-empty if the PDF was written by a plotting tool (so it is a figure, not a paper)."""
    try:
        meta = reader.metadata or {}
    except Exception:
        return ""
    for key in ("/Producer", "/Creator"):
        val = " ".join(str(meta.get(key) or "").split())
        if val and _PLOT_PRODUCER_RE.search(val):
            return f"looks like a figure, not a paper (made by {val})"
    title = str(meta.get("/Title") or "")
    if re.search(r"graphics output", title, re.IGNORECASE):
        return f"looks like a figure, not a paper (title {title!r})"
    return ""


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

    0. figures made by R / matplotlib / cairo are skipped outright
    1. DOI in PDF metadata / XMP
    2. arXiv ID in the file name (e.g. "2401.12345v2.pdf")
    3. arXiv stamp on page 1 ("arXiv:2401.12345v2 [cs.LG] ...")
    4. DOIs, then arXiv IDs, in the text of pages 1-2 -- returned as *candidates*
       (`text_dois` / `text_arxivs`) that the caller must verify with `title_in_text`
    5. a title guess (metadata title or largest text on page 1) as the fallback
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

    reason = figure_reason(reader)
    if reason:
        ids.skip_reason = reason
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

    # IDs in the text: keep all candidates (page 1 first). The caller checks each one
    # against the text, because the first DOI on a page is often a reference.
    ids.text = "\n".join(texts)
    for text in texts:
        for doi in find_all_dois(text):
            if doi.lower() not in (d.lower() for d in ids.text_dois):
                ids.text_dois.append(doi)
        for arx in find_all_arxivs(text):
            if arx not in ids.text_arxivs:
                ids.text_arxivs.append(arx)
    del ids.text_dois[MAX_TEXT_CANDIDATES:]
    del ids.text_arxivs[MAX_TEXT_CANDIDATES:]
    if ids.text_dois:
        ids.doi = ids.text_dois[0]
    elif ids.text_arxivs:
        ids.arxiv = ids.text_arxivs[0]
    if ids.doi or ids.arxiv:
        ids.source = "page text"

    # Always compute a title guess too: it is the fallback if no text ID checks out.
    ids.title_guess = _metadata_title(reader)
    if not ids.title_guess and reader.pages:
        ids.title_guess = _largest_font_text(reader.pages[0])
    if ids.title_guess and not ids.source:
        ids.source = "title guess"
    return ids


def _norm_words(s: str) -> list[str]:
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"<[^>]+>", " ", s)            # Crossref titles may carry <i>, <sub>...
    s = re.sub(r"-\s*\n\s*", "", s)           # words hyphenated across lines
    return re.findall(r"[a-z0-9]+", s.lower())


def title_in_text(title: str, text: str, min_coverage: float = 0.8) -> bool:
    """True if `title` plausibly appears in `text` (the paper's own first pages).

    Used to reject a DOI that belongs to a cited paper: the cited paper's title is
    almost never printed on this PDF's first pages, while the PDF's own title is.
    """
    t_words = _norm_words(title)
    x_words = _norm_words(text)
    if not t_words or not x_words:
        return False
    # pypdf sometimes drops spaces ("Amplifiersofselection"), so also compare squashed.
    if "".join(t_words) in "".join(x_words):
        return True
    significant = [w for w in t_words if len(w) > 3]
    if len(significant) < 3:
        return False
    x_set = set(x_words)
    hits = sum(w in x_set for w in significant)
    return hits / len(significant) >= min_coverage


def author_in_text(family: str, text: str) -> bool:
    """True if an author's family name (e.g. "van der Walt", "Mendoza-Revilla") is in `text`."""
    name = _norm_words(family)
    words = _norm_words(text)
    if not name or not words:
        return False
    return "".join(name) in "".join(words) if len(name) > 1 else name[0] in set(words)
