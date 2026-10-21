"""User configuration, stored as TOML in the OS-appropriate config directory."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from paperwatch.naming import DEFAULT_TEMPLATE

APP = "paperwatch"


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP


def config_path() -> Path:
    return config_dir() / "config.toml"


def log_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / APP / "paperwatch.log"
    if sys.platform == "win32":
        return config_dir() / "paperwatch.log"
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / APP / "paperwatch.log"


def default_downloads() -> Path:
    if sys.platform.startswith("linux"):
        # Respect localized folder names (e.g. ~/Téléchargements) from xdg-user-dirs.
        dirs_file = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "user-dirs.dirs"
        try:
            for line in dirs_file.read_text().splitlines():
                if line.startswith("XDG_DOWNLOAD_DIR="):
                    val = line.split("=", 1)[1].strip().strip('"')
                    return Path(val.replace("$HOME", str(Path.home())))
        except OSError:
            pass
    return Path.home() / "Downloads"


@dataclass
class Config:
    folders: list[Path] = field(default_factory=lambda: [default_downloads()])
    template: str = DEFAULT_TEMPLATE
    max_length: int = 150
    ascii_only: bool = False
    email: Optional[str] = None  # sent to Crossref for its faster "polite" pool
    title_search: bool = True  # fall back to a title search when no DOI/arXiv ID is found
    move_to: Optional[Path] = None  # optionally move renamed papers into this folder


DEFAULT_CONFIG_TEXT = f"""\
# paperwatch configuration
# Folders to watch for new PDFs.
folders = ["{default_downloads().as_posix()}"]

# File name template. Fields: {{author}} {{authors}} {{year}} {{title}} {{journal}} {{doi}} {{arxiv}}
#   {{author}}  = first author's family name     -> "Smith"
#   {{authors}} = "Smith", "Smith & Lee" or "Smith et al."
template = "{DEFAULT_TEMPLATE}"

# Maximum length of the file name (without .pdf).
max_length = 150

# Strip accents / non-ASCII characters from file names.
ascii_only = false

# Your e-mail, sent to Crossref so you get their faster "polite" API pool (optional).
# email = "you@example.org"

# If no DOI or arXiv ID is found, try a Crossref search by the paper's title.
title_search = true

# Move renamed papers into this folder (optional).
# move_to = "~/Papers"
"""


def load(path: Optional[Path] = None) -> Config:
    path = path or config_path()
    cfg = Config()
    if not path.exists():
        return cfg
    with open(path, "rb") as f:
        data = tomllib.load(f)
    if "folders" in data:
        cfg.folders = [Path(p).expanduser() for p in data["folders"]]
    for key in ("template", "max_length", "ascii_only", "email", "title_search"):
        if key in data:
            setattr(cfg, key, data[key])
    if data.get("move_to"):
        cfg.move_to = Path(data["move_to"]).expanduser()
    return cfg


def write_default(path: Optional[Path] = None) -> Path:
    path = path or config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
    return path
