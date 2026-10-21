"""Command line interface."""

from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from paperwatch import __version__, config, service
from paperwatch.core import process

log = logging.getLogger("paperwatch")


def _setup_logging(verbose: bool, log_file: str | None = None):
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:  # pythonw.exe on Windows has no stderr
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(message)s"))
        handlers.append(h)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        fh.setFormatter(fmt)
        handlers.append(fh)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    for h in handlers:
        log.addHandler(h)


def _load_config(args) -> config.Config:
    cfg = config.load(Path(args.config).expanduser() if args.config else None)
    if getattr(args, "template", None):
        cfg.template = args.template
    if getattr(args, "email", None):
        cfg.email = args.email
    if getattr(args, "no_title_search", False):
        cfg.title_search = False
    if getattr(args, "ascii", False):
        cfg.ascii_only = True
    if getattr(args, "move_to", None):
        cfg.move_to = Path(args.move_to).expanduser()
    return cfg


def cmd_rename(args) -> int:
    cfg = _load_config(args)
    files: list[Path] = []
    for p in map(Path, args.paths):
        p = p.expanduser()
        if p.is_dir():
            pattern = "**/*.pdf" if args.recursive else "*.pdf"
            files.extend(sorted(f for f in p.glob(pattern) if f.is_file()))
        elif p.is_file():
            files.append(p)
        else:
            log.warning("not found: %s", p)

    failures = 0
    for f in files:
        res = process(f, cfg, dry_run=args.dry_run)
        if res.renamed:
            arrow = "would rename" if args.dry_run else "renamed"
            log.info("%s: %s\n   -> %s", arrow, f.name, res.target.name)
        elif res.target == f:
            log.info("ok (already named): %s", f.name)
        else:
            failures += 1
            log.info("skipped %s: %s", f.name, res.reason)
    return 1 if failures and len(files) == failures else 0


def cmd_watch(args) -> int:
    from paperwatch.watcher import Watcher

    cfg = _load_config(args)
    if args.folders:
        cfg.folders = [Path(f).expanduser() for f in args.folders]
    Watcher(cfg, dry_run=args.dry_run).run()
    return 0


def cmd_install(args) -> int:
    path = config.write_default()
    log.info("config: %s", path)
    log.info(service.install())
    log.info("log file: %s", config.log_path())
    log.info("paperwatch will now run in the background and start automatically at login.")
    return 0


def cmd_uninstall(args) -> int:
    log.info(service.uninstall())
    return 0


def cmd_config(args) -> int:
    path = config.write_default()
    print(path)
    if args.show:
        print(path.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="paperwatch",
        description="Automatically rename scientific paper PDFs using DOI / arXiv metadata.",
    )
    p.add_argument("--version", action="version", version=f"paperwatch {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="debug output")
    p.add_argument("--config", help="path to a config.toml (default: %s)" % config.config_path())
    sub = p.add_subparsers(dest="command", required=True)

    def naming_opts(sp):
        sp.add_argument("-t", "--template", help='file name template, e.g. "{year} - {authors} - {title}"')
        sp.add_argument("--email", help="your e-mail for Crossref's polite pool")
        sp.add_argument("--ascii", action="store_true", help="ASCII-only file names")
        sp.add_argument("--no-title-search", action="store_true",
                        help="only rename papers with a DOI / arXiv ID")
        sp.add_argument("--move-to", help="move renamed papers into this folder")
        sp.add_argument("-n", "--dry-run", action="store_true", help="show what would happen")

    r = sub.add_parser("rename", help="rename PDF files or all PDFs in folders, once")
    r.add_argument("paths", nargs="+", help="PDF files or folders")
    r.add_argument("-r", "--recursive", action="store_true", help="include sub-folders")
    naming_opts(r)
    r.set_defaults(func=cmd_rename)

    w = sub.add_parser("watch", help="watch folders (default: Downloads) and rename new PDFs")
    w.add_argument("folders", nargs="*", help="folders to watch (overrides config)")
    w.add_argument("--log-file", help="also log to this file")
    naming_opts(w)
    w.set_defaults(func=cmd_watch)

    i = sub.add_parser("install", help="run the watcher in the background at every login")
    i.set_defaults(func=cmd_install)

    u = sub.add_parser("uninstall", help="remove the background service")
    u.set_defaults(func=cmd_uninstall)

    c = sub.add_parser("config", help="print (and create) the config file path")
    c.add_argument("--show", action="store_true", help="also print its contents")
    c.set_defaults(func=cmd_config)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose, getattr(args, "log_file", None))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
