"""Rename a single PDF: identify -> look up -> build name -> rename."""

from __future__ import annotations

import fnmatch
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from paperwatch.config import Config
from paperwatch.identify import Identifiers, author_in_text, identify, title_in_text
from paperwatch.lookup import NotFound, Paper, lookup
from paperwatch.naming import build_name, unique_path

log = logging.getLogger(__name__)


@dataclass
class Result:
    source: Path
    target: Optional[Path] = None
    paper: Optional[Paper] = None
    reason: str = ""

    @property
    def renamed(self) -> bool:
        return self.target is not None and self.target != self.source


def is_pdf(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(1024).lstrip().startswith(b"%PDF")
    except OSError:
        return False


IGNORE_FILE = ".paperwatchignore"


def excluded(path: Path, cfg: Config) -> str:
    """Why `path` must be left alone ("" if it may be renamed)."""
    path = path.expanduser().absolute()
    for folder in path.parents:
        if (folder / IGNORE_FILE).exists():
            return f"excluded ({IGNORE_FILE} in {folder})"
    full = path.as_posix()
    for pat in cfg.exclude or []:
        if fnmatch.fnmatch(full, pat) or ("/" not in pat and any(fnmatch.fnmatch(part, pat) for part in path.parts)):
            return f"excluded (matches {pat!r})"
    return ""


def process(path: Path, cfg: Config, dry_run: bool = False) -> Result:
    res = Result(source=path)
    why = excluded(path, cfg)
    if why:
        res.reason = why
        return res
    if not is_pdf(path):
        res.reason = "not a PDF"
        return res

    try:
        ids = identify(path)
    except Exception as e:
        res.reason = f"could not read PDF: {e}"
        return res

    if ids.skip_reason:
        res.reason = ids.skip_reason
        return res
    if not (ids.doi or ids.arxiv or ids.title_guess):
        res.reason = "no DOI, arXiv ID or title found"
        return res
    log.debug("%s: doi=%s arxiv=%s text_dois=%s title=%r (from %s)",
              path.name, ids.doi, ids.arxiv, ids.text_dois, ids.title_guess, ids.source)

    try:
        if ids.text_dois or ids.text_arxivs:
            paper = _verified_text_lookup(path, ids, cfg)
        elif not (ids.doi or ids.arxiv):
            if not cfg.title_search:
                raise NotFound("no DOI or arXiv ID (title search is off)")
            paper = _verified_title_search(ids, cfg)
        else:
            paper = lookup(ids.doi, ids.arxiv, ids.title_guess, email=cfg.email,
                           title_search=cfg.title_search)
    except NotFound as e:
        res.reason = f"metadata not found ({e})"
        return res
    except Exception as e:  # network down, rate limited, bad XML...
        res.reason = f"lookup failed: {e}"
        return res

    if not paper.title:
        res.reason = "metadata has no title"
        return res
    res.paper = paper

    stem = build_name(paper, cfg.template, cfg.max_length, cfg.ascii_only, cfg.space)
    if not stem:
        res.reason = "empty file name"
        return res

    folder = cfg.move_to or path.parent
    target = unique_path(folder / f"{stem}.pdf", current=path)
    res.target = target
    if target == path or dry_run:
        return res

    folder.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))
    return res


def _verified_text_lookup(path: Path, ids: Identifiers, cfg: Config) -> Paper:
    """Try each DOI / arXiv ID found in the page text and keep the first whose title is
    actually printed in the PDF. A DOI on page 1 is often a reference to another paper;
    without this check the file would be renamed after the cited paper."""
    rejected: list[str] = []
    candidates = [("doi", d) for d in ids.text_dois] + [("arxiv", a) for a in ids.text_arxivs]
    for kind, ident in candidates:
        try:
            paper = lookup(doi=ident, email=cfg.email) if kind == "doi" \
                else lookup(arxiv=ident, email=cfg.email)
        except NotFound:
            rejected.append(f"{ident} (not found)")
            continue
        if paper.title and title_in_text(paper.title, ids.text):
            return paper
        log.debug("%s: %s is %r, which is not in the PDF text -- probably a reference",
                  path.name, ident, paper.title)
        rejected.append(f"{ident} (title not in PDF)")
    if ids.title_guess and cfg.title_search:
        try:
            return _verified_title_search(ids, cfg)
        except NotFound as e:
            rejected.append(str(e))
    raise NotFound("no DOI in the text matches this PDF: " + "; ".join(rejected))


def _verified_title_search(ids: Identifiers, cfg: Config) -> Paper:
    """Crossref title search, accepted only if the match's first author is named in the PDF.

    A title search can always find *some* record with a similar title (a cheat sheet called
    "Data transformation with dplyr", a form, a book chapter...). Requiring the first
    author's surname to be printed in the file rules those out."""
    paper = lookup(title_guess=ids.title_guess, email=cfg.email, title_search=True)
    if not paper.authors:
        raise NotFound(f"title match {paper.title!r} has no authors, not trusting it")
    if not author_in_text(paper.authors[0], ids.text):
        raise NotFound(f"title match {paper.title!r} by {paper.authors[0]}, "
                       f"but that author is not named in this PDF")
    return paper
