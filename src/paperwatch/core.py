"""Rename a single PDF: identify -> look up -> build name -> rename."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from paperwatch.config import Config
from paperwatch.identify import identify
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


def process(path: Path, cfg: Config, dry_run: bool = False) -> Result:
    res = Result(source=path)
    if not is_pdf(path):
        res.reason = "not a PDF"
        return res

    try:
        ids = identify(path)
    except Exception as e:
        res.reason = f"could not read PDF: {e}"
        return res

    if not (ids.doi or ids.arxiv or ids.title_guess):
        res.reason = "no DOI, arXiv ID or title found"
        return res
    log.debug("%s: doi=%s arxiv=%s title=%r (from %s)",
              path.name, ids.doi, ids.arxiv, ids.title_guess, ids.source)

    try:
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
