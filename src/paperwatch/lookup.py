"""Fetch bibliographic metadata from Crossref and arXiv (no API keys needed)."""

from __future__ import annotations

import difflib
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from paperwatch import __version__

log = logging.getLogger(__name__)

TIMEOUT = 20
ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass
class Paper:
    title: str
    authors: list[str] = field(default_factory=list)  # family names, in order
    year: str = ""
    journal: str = ""
    doi: str = ""
    arxiv: str = ""


class NotFound(Exception):
    pass


def _user_agent(email: Optional[str]) -> str:
    ua = f"paperwatch/{__version__} (https://github.com/loukesio/paperwatch"
    if email:
        ua += f"; mailto:{email}"  # puts us in Crossref's "polite" pool
    return ua + ")"


def _get(url: str, email: Optional[str]) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _user_agent(email)})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NotFound(url) from e
        raise


def _family(name: str) -> str:
    """Best-effort family name from a full name ("Jane Q. Doe" -> "Doe")."""
    name = name.strip()
    if "," in name:
        return name.split(",", 1)[0].strip()
    parts = name.split()
    return parts[-1] if parts else name


def _crossref_to_paper(msg: dict) -> Paper:
    title = (msg.get("title") or [""])[0]
    authors = []
    for a in msg.get("author") or []:
        fam = a.get("family") or a.get("name") or ""
        if fam:
            authors.append(fam if a.get("family") else _family(fam))
    year = ""
    for key in ("issued", "published-print", "published-online", "published", "created"):
        parts = (msg.get(key) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            year = str(parts[0][0])
            break
    journal = (msg.get("container-title") or [""])[0]
    short = (msg.get("short-container-title") or [""])[0]
    return Paper(
        title=title,
        authors=authors,
        year=year,
        journal=short or journal,
        doi=msg.get("DOI", ""),
    )


def crossref_by_doi(doi: str, email: Optional[str] = None) -> Paper:
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    data = json.loads(_get(url, email))
    return _crossref_to_paper(data["message"])


def arxiv_by_id(arxiv_id: str, email: Optional[str] = None) -> Paper:
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"id_list": re.sub(r"v\d+$", "", arxiv_id), "max_results": 1}
    )
    root = ET.fromstring(_get(url, email))
    entry = root.find(f"{ATOM}entry")
    if entry is None or entry.find(f"{ATOM}title") is None:
        raise NotFound(arxiv_id)
    title = " ".join((entry.findtext(f"{ATOM}title") or "").split())
    if not title or title.lower() == "error":
        raise NotFound(arxiv_id)
    authors = [_family(a.findtext(f"{ATOM}name") or "") for a in entry.findall(f"{ATOM}author")]
    published = entry.findtext(f"{ATOM}published") or ""
    doi = entry.findtext("{http://arxiv.org/schemas/atom}doi") or ""
    return Paper(
        title=title,
        authors=[a for a in authors if a],
        year=published[:4],
        journal="arXiv",
        doi=doi,
        arxiv=re.sub(r"v\d+$", "", arxiv_id),
    )


def _norm(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def crossref_by_title(title: str, email: Optional[str] = None, min_ratio: float = 0.9) -> Paper:
    """Search Crossref by title and accept only a near-exact title match."""
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query.bibliographic": title, "rows": 5}
    )
    items = json.loads(_get(url, email))["message"].get("items", [])
    want = _norm(title)
    best, best_ratio = None, 0.0
    for item in items:
        cand = _norm((item.get("title") or [""])[0])
        ratio = difflib.SequenceMatcher(None, want, cand).ratio()
        if ratio > best_ratio:
            best, best_ratio = item, ratio
    if best is None or best_ratio < min_ratio:
        raise NotFound(f"no confident title match for {title!r} (best {best_ratio:.2f})")
    return _crossref_to_paper(best)


def _doi_variants(doi: str):
    """Text extraction sometimes glues the next word onto a DOI ("...2649-2Received")."""
    yield doi
    trimmed = re.sub(r"(?<=\d)[A-Z][a-z]+$", "", doi)
    if trimmed != doi:
        yield trimmed


def lookup(doi: Optional[str] = None, arxiv: Optional[str] = None,
           title_guess: Optional[str] = None, email: Optional[str] = None,
           title_search: bool = True) -> Paper:
    if doi:
        m = re.match(r"10\.48550/arxiv\.(.+)$", doi, re.IGNORECASE)
        if m:  # arXiv-issued DOI: arXiv has better metadata than Crossref here
            return arxiv_by_id(m.group(1), email)
        for variant in _doi_variants(doi):
            try:
                return crossref_by_doi(variant, email)
            except NotFound:
                continue
        raise NotFound(doi)
    if arxiv:
        return arxiv_by_id(arxiv, email)
    if title_guess and title_search:
        return crossref_by_title(title_guess, email)
    raise NotFound("no identifier")
