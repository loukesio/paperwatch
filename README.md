<p align="center">
  <img src="assets/logo.gif" alt="paperwatch: download a paper, it renames itself" width="720">
</p>

<p align="center">
  <a href="https://github.com/loukesio/paperwatch/actions/workflows/ci.yml"><img src="https://github.com/loukesio/paperwatch/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/loukesio/paperwatch/releases/latest"><img src="https://img.shields.io/github/v/release/loukesio/paperwatch?color=2dd4bf" alt="Release"></a>
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-0f172a" alt="Platforms">
  <img src="https://img.shields.io/badge/python-3.10%2B-0f172a" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-0f172a" alt="MIT license"></a>
</p>

Papers download as `s41586-020-2649-2.pdf`, `1-s2.0-S0092867420300015-main.pdf` or
`download (3).pdf`. **paperwatch** sits quietly in the background and, the moment a download
finishes, gives each paper a name you can actually find again:

```text
s41586-020-2649-2.pdf               →  Harris_2020_Array programming with NumPy.pdf
1706.03762v7.pdf                    →  Vaswani_2017_Attention Is All You Need.pdf
journal.pcbi.1008373.pdf            →  Forano_2020_Timescales of motor memory formation in dual-adaptation.pdf
```

It reads the paper's **DOI** or **arXiv ID**, looks up the real title, authors and year
(Crossref / arXiv, free, no account or API key), and renames the file. PDFs that aren't papers,
like invoices and boarding passes, are left alone.

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Use it from Claude Code or Codex](#use-it-from-claude-code-or-codex)
- [How it works](#how-it-works)
- [Troubleshooting](#troubleshooting)
- [Similar tools](#similar-tools)
- [Development](#development)

## Install

### macOS & Linux: Homebrew

```bash
brew install loukesio/tap/paperwatch
brew services start paperwatch      # watch ~/Downloads now and at every login
```

### Any OS: pipx or uv

```bash
pipx install git+https://github.com/loukesio/paperwatch
# or
uv tool install git+https://github.com/loukesio/paperwatch

paperwatch install                  # watch ~/Downloads now and at every login
```

### Standalone binary

No Python needed. Grab the file for your system from the
[latest release](https://github.com/loukesio/paperwatch/releases/latest), then:

```bash
chmod +x paperwatch-macos-arm64 && mv paperwatch-macos-arm64 /usr/local/bin/paperwatch
paperwatch install
```

On Windows, put `paperwatch-windows-x86_64.exe` somewhere permanent, then run
`paperwatch-windows-x86_64.exe install` in a terminal. The binaries are not code-signed, so macOS
and Windows will warn the first time you run them.

## Quick start

| command | what it does |
|---|---|
| `paperwatch install` | run in the background and start at every login |
| `paperwatch uninstall` | stop and remove the background service |
| `paperwatch watch` | watch `~/Downloads` in the foreground (Ctrl+C to stop) |
| `paperwatch watch ~/Downloads ~/Desktop` | watch other folders |
| `paperwatch rename paper.pdf` | rename specific files once |
| `paperwatch rename ~/Papers -r -n` | preview (`-n`) renaming a whole folder tree (`-r`) |
| `paperwatch config --show` | show the config file location and contents |

> Use **either** `brew services` **or** `paperwatch install`, not both.

## Configuration

`paperwatch config` creates the config file and prints where it is
(macOS `~/Library/Application Support/paperwatch/config.toml`,
Linux `~/.config/paperwatch/config.toml`, Windows `%APPDATA%\paperwatch\config.toml`):

```toml
folders = ["~/Downloads"]              # folders to watch
template = "{author}_{year}_{title}"   # file name template, see below
space = " "                            # use "-" or "_" for names without spaces
max_length = 150                       # longer names are cut at a word boundary
ascii_only = false                     # "Schrödinger" -> "Schrodinger"
title_search = true                    # no DOI/arXiv ID? search Crossref by title (strict match)
# email = "you@example.org"            # optional: use Crossref's faster "polite" pool
# move_to = "~/Papers"                 # optional: also move renamed papers here
```

Restart the service after editing (`paperwatch install` again, or `brew services restart paperwatch`).

**Template fields:** `{author}` first author's surname, `{authors}` (`Smith`, `Smith & Lee` or
`Smith et al.`), `{year}`, `{title}`, `{journal}`, `{doi}`, `{arxiv}`.

| template | result |
|---|---|
| `{author}_{year}_{title}` *(default)* | `Harris_2020_Array programming with NumPy.pdf` |
| `{year} - {authors} - {title}` | `2020 - Harris et al. - Array programming with NumPy.pdf` |
| `{authors} ({year}) {journal}` | `Harris et al. (2020) Nature.pdf` |

**Spaces:** `space` controls what goes between the words *inside* a title or author list.
By default normal spaces are kept. Set `space = "-"` for
`Array-programming-with-NumPy`, or `space = "_"` for `Array_programming_with_NumPy`
(or pass `--space -` on the command line). Separators you type in the
template itself (like ` - ` above) are always kept as written.

Every setting can also be given on the command line; see `paperwatch watch --help`.

## Use it from Claude Code or Codex

paperwatch also ships as an **agent skill**: a short instruction file
([`skills/paperwatch/SKILL.md`](skills/paperwatch/SKILL.md)) that teaches an AI coding assistant
how to use the tool. The background watcher handles new downloads by itself; the skill is for
everything you'd rather just *ask* for:

> *"Rename all the papers in ~/Documents/thesis-refs"*
> *"Rename them as Year - Authors - Title instead"*
> *"Why wasn't the PDF I just downloaded renamed?"*
> *"Also watch my Desktop and move renamed papers into ~/Papers"*

**How it works:** the assistant only loads the skill when your request is about renaming or
organizing papers. It then:

1. checks that paperwatch is installed, and offers to install it if not;
2. runs a dry run (`paperwatch rename … -n`) and shows you the proposed new names;
3. renames the files only after you agree;
4. for setup questions, edits the config file and restarts the service for you;
5. for failures, reads the log, runs `paperwatch -v` to see what was found, and explains
   or fixes the problem.

The skill itself contains no code. Everything runs through the `paperwatch` command, so the
same skill works in both tools.

### Claude Code

Inside Claude Code:

```text
/plugin marketplace add loukesio/paperwatch
/plugin install paperwatch@paperwatch
```

On Claude Code 2.1.275 or later this works in one step:
`/plugin install paperwatch --marketplace loukesio/paperwatch`

### Codex

Inside Codex, ask the built-in installer:

```text
$skill-installer install https://github.com/loukesio/paperwatch/tree/main/skills/paperwatch
```

Or copy it by hand:

```bash
git clone https://github.com/loukesio/paperwatch /tmp/paperwatch
mkdir -p ~/.codex/skills && cp -r /tmp/paperwatch/skills/paperwatch ~/.codex/skills/
```

Restart Codex afterwards so it picks up the new skill.

## How it works

1. **Wait for the download to finish.** Browser temp files (`.crdownload`, `.part`, `.download`)
   are ignored, and the file size has to stop changing.
2. **Check it's really a PDF.** Many "PDF" links actually download an HTML login page.
3. **Find an identifier**, in this order: DOI in the PDF metadata → arXiv ID in the file name →
   arXiv stamp on page 1 → first DOI on pages 1–2 → any arXiv ID in the text.
4. **Look up the metadata** on [Crossref](https://www.crossref.org) (DOIs) or
   [arXiv](https://arxiv.org) (arXiv IDs and `10.48550/arXiv.*` DOIs).
5. **No identifier?** It guesses the title (PDF metadata, or the largest text on page 1), searches
   Crossref, and renames only if the titles match at least 90 %.
6. **Rename safely.** The name is valid on Windows, macOS and Linux, and existing files are never
   overwritten: you get `name (2).pdf` instead.

Background service:

| OS | mechanism | log file |
|---|---|---|
| macOS | LaunchAgent `~/Library/LaunchAgents/io.github.paperwatch.plist` | `~/Library/Logs/paperwatch/paperwatch.log` |
| Linux | systemd user unit `~/.config/systemd/user/paperwatch.service` | `~/.local/state/paperwatch/paperwatch.log` |
| Windows | hidden launcher in the Startup folder (`shell:startup`) | `%APPDATA%\paperwatch\paperwatch.log` |
| Homebrew | `brew services` | `$(brew --prefix)/var/log/paperwatch.log` |

## Troubleshooting

**Nothing happens on macOS.** macOS protects the Downloads folder from background programs. If
the log says *no permission*, open **System Settings → Privacy & Security → Full Disk Access**,
add the program from the log message (the Python binary, or `paperwatch` itself), and restart the
service.

**A paper wasn't renamed.** Run `paperwatch -v rename that-file.pdf -n` to see what it found.
Common reasons: the PDF is a scan without a text layer, or it has no DOI and its title couldn't be
read reliably. paperwatch would rather leave a file alone than give it a wrong name.

**Two copies of the same paper.** The second one becomes `… (2).pdf`; nothing is overwritten.

## Similar tools

| tool | approach | compared with paperwatch |
|---|---|---|
| [pdf-renamer](https://pypi.org/project/pdf-renamer) | DOI/arXiv lookup via pdf2doi + pdf2bib | renames on demand; no watcher or autostart |
| [pydfdoi](https://pypi.org/project/pydfdoi/) | DOI from metadata/text → Crossref | no watcher |
| [watchpdf](https://github.com/defaultobject/watchpdf) | watches folders, delegates renaming | |
| [arxiv-rename](https://pypi.org/project/arxiv-rename) | watcher for arXiv downloads | arXiv only |
| [sci-paper-rename](https://pypi.org/project/sci-paper-rename/), [chou](https://pypi.org/project/chou/) | title from the PDF text (font size, OCR) | no online metadata |
| [Zotero](https://www.zotero.org), [JabRef](https://www.jabref.org) | full reference managers | much more, but heavier; files live in a library |

paperwatch aims to be the small one: a single install, a background service on all three OSes,
DOI **and** arXiv, and only two dependencies ([pypdf](https://github.com/py-pdf/pypdf) and
[watchdog](https://github.com/gorakhargosh/watchdog)).

## Development

```bash
git clone https://github.com/loukesio/paperwatch && cd paperwatch
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
```

The banner is generated by `assets/make_logo.py` (`pip install pillow`, then run it).

**Releasing**

1. Bump `version` in `pyproject.toml` and `src/paperwatch/__init__.py`.
2. Commit, then tag and push: `git tag vX.Y.Z && git push --tags`.
3. GitHub Actions builds the binaries for all OSes and creates the release. To also publish to
   PyPI, set up [trusted publishing](https://docs.pypi.org/trusted-publishers/) and set the
   repository variable `PUBLISH_PYPI=true`.
4. Update the Homebrew formula in
   [loukesio/homebrew-tap](https://github.com/loukesio/homebrew-tap): change `url` to the new
   tag's tarball and update `sha256` (`curl -sL <url> | shasum -a 256`).

## License

[MIT](LICENSE). The banner uses [IBM Plex](https://github.com/IBM/plex) (SIL Open Font License).
