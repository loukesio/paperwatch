---
name: paperwatch
description: Rename scientific paper PDFs to "Author_Year_Title.pdf" using their DOI or arXiv metadata, and manage the paperwatch background watcher. Use when the user wants to rename, tidy or organize research papers / PDFs, asks why a downloaded paper was not renamed, wants to change the paper naming scheme, or wants to install, configure, start or stop paperwatch.
---

# paperwatch

`paperwatch` is a CLI that finds a PDF's DOI or arXiv ID, looks up title / authors / year on
Crossref or arXiv (no API key) and renames the file, e.g.
`s41586-020-2649-2.pdf` → `Harris_2020_Array programming with NumPy.pdf`.
It can also run in the background and rename every new download automatically.

## 1. Make sure it is installed

Run `paperwatch --version`. If it is missing, ask the user before installing, then use the first
option that is available:

```bash
brew install loukesio/tap/paperwatch                        # macOS / Linux with Homebrew
pipx install git+https://github.com/loukesio/paperwatch     # any OS with pipx
uv tool install git+https://github.com/loukesio/paperwatch  # any OS with uv
```

## 2. Renaming existing papers

Always preview first, show the user the result, and only then rename for real:

```bash
paperwatch rename <files-or-folders> -n          # dry run: prints "would rename: a.pdf -> b.pdf"
paperwatch rename <files-or-folders>             # do it
```

Useful options (work with `rename` and `watch`):

| option | effect |
|---|---|
| `-r` | include sub-folders |
| `-t "<template>"` | naming template (see below) |
| `--move-to <folder>` | move renamed papers into a folder |
| `--ascii` | strip accents / non-ASCII characters |
| `--no-title-search` | only rename papers that have a DOI / arXiv ID |
| `-v` | debug output: shows which identifier was found and where |

Template fields: `{author}` (first author's surname), `{authors}` (`Smith`, `Smith & Lee` or
`Smith et al.`), `{year}`, `{title}`, `{journal}`, `{doi}`, `{arxiv}`.
Default: `{author}_{year}_{title}`. Example: `-t "{year} - {authors} - {title}"`.

Existing files are never overwritten (a duplicate becomes `name (2).pdf`), and PDFs that are not
papers are skipped, so it is safe to run on mixed folders.

## 3. Background watcher

| task | command |
|---|---|
| start at login (Homebrew install) | `brew services start paperwatch` |
| start at login (pipx / uv / binary) | `paperwatch install` |
| stop | `brew services stop paperwatch` or `paperwatch uninstall` |
| run in the foreground | `paperwatch watch [folders...]` |

Use only one of `brew services` and `paperwatch install`, never both. Check which is active with
`brew services list` before changing anything.

Settings live in a TOML file; `paperwatch config --show` prints its path and contents. Keys:
`folders` (list of watched folders, default `["~/Downloads"]`), `template`, `max_length`,
`ascii_only`, `title_search`, `move_to`, `email`. Edit the file, then restart the service
(`brew services restart paperwatch`, or run `paperwatch install` again).

Logs:
- Homebrew: `$(brew --prefix)/var/log/paperwatch.log`
- macOS: `~/Library/Logs/paperwatch/paperwatch.log`
- Linux: `~/.local/state/paperwatch/paperwatch.log`
- Windows: `%APPDATA%\paperwatch\paperwatch.log`

## 4. When a paper was not renamed

1. Read the log: each file gets a `renamed …` or `skipped …: <reason>` line.
2. Run `paperwatch -v rename <file> -n` to see what identifier was found.
3. Common causes:
   - **"no DOI, arXiv ID or title found"**: usually a scanned PDF without a text layer.
     Offer to rename it by hand from what the user knows.
   - **"metadata not found"**: the DOI was misread from the text. Look at the PDF's first page,
     find the real DOI and rename manually with the same `Author_Year_Title` pattern.
   - **"no permission"** on macOS: the service needs Full Disk Access
     (System Settings → Privacy & Security → Full Disk Access) for the binary named in the log.
   - **Browser still shows the old name**: that's expected. The browser's download list does not
     notice renames; check the folder itself.

Do not send the user's PDFs anywhere. paperwatch only sends the DOI, arXiv ID or title to
Crossref / arXiv.
