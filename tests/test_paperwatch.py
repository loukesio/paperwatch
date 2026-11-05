from pathlib import Path

import pytest
from pypdf import PdfWriter

from paperwatch import core, lookup
from paperwatch.config import Config
from paperwatch.identify import arxiv_from_filename, clean_doi, find_arxiv, find_doi, identify
from paperwatch.lookup import Paper, _crossref_to_paper
from paperwatch.naming import build_name, clean_text, unique_path


# ---------------------------------------------------------------- identifiers
@pytest.mark.parametrize("text,expected", [
    ("https://doi.org/10.1038/s41586-020-2649-2", "10.1038/s41586-020-2649-2"),
    ("doi:10.1016/j.cell.2020.01.001.", "10.1016/j.cell.2020.01.001"),
    ("(see 10.1002/anie.201915678)", "10.1002/anie.201915678"),
    ("DOI 10.1103/PhysRevLett.116.061102, received", "10.1103/PhysRevLett.116.061102"),
    ("10.1007/978-3-030-58452-8_13", "10.1007/978-3-030-58452-8_13"),
    ("10.1016/S0140-6736(20)30183-5", "10.1016/S0140-6736(20)30183-5"),
    ("no identifier here", None),
])
def test_find_doi(text, expected):
    assert find_doi(text) == expected


def test_clean_doi_strips_prefixes():
    assert clean_doi("https://dx.doi.org/10.1000/xyz;") == "10.1000/xyz"


def test_arxiv_stamp_and_text():
    stamp = "Some text arXiv:2401.12345v2 [cs.LG] 3 Jan 2024 more"
    assert find_arxiv(stamp, stamp_only=True) == "2401.12345v2"
    assert find_arxiv("see arXiv:hep-th/9901001", stamp_only=False) == "hep-th/9901001"
    assert find_arxiv("see arXiv:2401.12345", stamp_only=True) is None


@pytest.mark.parametrize("name,expected", [
    ("2401.12345v2.pdf", "2401.12345v2"),
    ("2401.12345.pdf", "2401.12345"),
    ("arXiv_2401.12345.pdf", "2401.12345"),
    ("paper 2401.12345.pdf", None),
    ("nature12345.pdf", None),
])
def test_arxiv_from_filename(name, expected):
    assert arxiv_from_filename(Path(name)) == expected


def _make_pdf(path: Path, metadata: dict) -> Path:
    w = PdfWriter()
    w.add_blank_page(width=612, height=792)
    w.add_metadata(metadata)
    with open(path, "wb") as f:
        w.write(f)
    return path


def test_identify_from_metadata(tmp_path):
    pdf = _make_pdf(tmp_path / "s41586.pdf", {"/Subject": "Nature, doi:10.1038/s41586-020-2649-2"})
    ids = identify(pdf)
    assert ids.doi == "10.1038/s41586-020-2649-2"
    assert ids.source == "pdf metadata"


def test_identify_title_guess(tmp_path):
    pdf = _make_pdf(tmp_path / "x.pdf", {"/Title": "Array programming with NumPy and friends"})
    ids = identify(pdf)
    assert ids.doi is None and ids.arxiv is None
    assert ids.title_guess == "Array programming with NumPy and friends"


def test_identify_ignores_junk_title(tmp_path):
    pdf = _make_pdf(tmp_path / "x.pdf", {"/Title": "Microsoft Word - final_v3.docx"})
    assert identify(pdf).title_guess is None


# ---------------------------------------------------------------- naming
def test_build_name_default():
    p = Paper(title="Array programming with <i>NumPy</i>: a review", authors=["Harris", "Millman", "van der Walt"],
              year="2020", journal="Nature", doi="10.1038/s41586-020-2649-2")
    assert build_name(p) == "Harris_2020_Array programming with NumPy - a review"
    assert build_name(p, space="-") == "Harris_2020_Array-programming-with-NumPy-a-review"
    assert build_name(p, space="_") == "Harris_2020_Array_programming_with_NumPy_a_review"


def test_build_name_space_keeps_template_separators():
    p = Paper(title="On things", authors=["Smith", "Lee", "Wu"], year="2021")
    assert build_name(p, "{year} - {authors} - {title}", space="-") == "2021 - Smith-et-al. - On-things"
    two = Paper(title="On things", authors=["Smith", "Lee"], year="2021")
    assert build_name(two, "{authors}_{year}", space="-") == "Smith-and-Lee_2021"
    assert build_name(two, space="/") == "Smith_2021_Onthings"  # illegal space char is dropped


def test_build_name_template_and_missing_fields():
    p = Paper(title="On things", authors=["Smith", "Lee"], year="")
    assert build_name(p, "{authors} - {year} - {title}", space=" ") == "Smith & Lee - On things"
    assert build_name(p, "{author}_{year}_{title}", space=" ") == "Smith_On things"


@pytest.mark.parametrize("space", [" ", "-", "_"])
def test_build_name_truncates_on_word_boundary(space):
    p = Paper(title="word " * 100, authors=["Smith"], year="2024")
    name = build_name(p, max_length=40, space=space)
    assert len(name) <= 40 and name.endswith("word")


def test_clean_text_illegal_and_ascii():
    assert clean_text('a/b\\c?*"<>|', ascii_only=False) == "a-bc"
    assert clean_text("Schrödinger équation", ascii_only=True) == "Schrodinger equation"


def test_unique_path(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    assert unique_path(tmp_path / "a.pdf") == tmp_path / "a (2).pdf"
    assert unique_path(tmp_path / "a.pdf", current=tmp_path / "a.pdf") == tmp_path / "a.pdf"


# ---------------------------------------------------------------- lookup parsing
def test_crossref_parsing():
    msg = {
        "title": ["A title"],
        "author": [{"family": "Doe", "given": "Jane"}, {"name": "The Consortium"}],
        "issued": {"date-parts": [[2021, 5, 3]]},
        "container-title": ["Journal of Things"],
        "short-container-title": ["J. Things"],
        "DOI": "10.1/abc",
    }
    p = _crossref_to_paper(msg)
    assert p.title == "A title"
    assert p.authors == ["Doe", "Consortium"]
    assert p.year == "2021"
    assert p.journal == "J. Things"


def test_arxiv_doi_routes_to_arxiv(monkeypatch):
    called = {}
    monkeypatch.setattr(lookup, "arxiv_by_id", lambda i, e=None: called.setdefault("id", i) and Paper("t"))
    lookup.lookup(doi="10.48550/arXiv.2401.12345")
    assert called["id"] == "2401.12345"


# ---------------------------------------------------------------- end to end (network mocked)
def test_process_renames(tmp_path, monkeypatch):
    pdf = _make_pdf(tmp_path / "download (3).pdf", {"/doi": "10.1038/s41586-020-2649-2"})
    monkeypatch.setattr(core, "lookup", lambda *a, **k: Paper(
        title="Array programming with NumPy", authors=["Harris"], year="2020"))
    res = core.process(pdf, Config(folders=[tmp_path]))
    assert res.renamed
    assert res.target == tmp_path / "Harris_2020_Array programming with NumPy.pdf"
    assert res.target.exists() and not pdf.exists()

    # running again is a no-op
    again = core.process(res.target, Config(folders=[tmp_path]))
    assert not again.renamed and again.target == res.target


def test_process_dry_run_and_non_pdf(tmp_path, monkeypatch):
    pdf = _make_pdf(tmp_path / "x.pdf", {"/doi": "10.1000/abc"})
    monkeypatch.setattr(core, "lookup", lambda *a, **k: Paper(title="T T T", authors=["A"], year="1999"))
    res = core.process(pdf, Config(), dry_run=True)
    assert res.renamed and pdf.exists()

    fake = tmp_path / "fake.pdf"
    fake.write_text("<html>login page</html>")
    assert core.process(fake, Config()).reason == "not a PDF"


# ---------------------------------------------------------------- false-rename guards
import shutil
import subprocess

from paperwatch.identify import figure_reason, title_in_text
from paperwatch.lookup import _doi_variants


@pytest.mark.parametrize("meta", [
    {"/Title": "R Graphics Output", "/Creator": "R", "/Producer": "R 4.5.1"},
    {"/Creator": "Matplotlib v3.8.4, https://matplotlib.org", "/Producer": "Matplotlib pdf backend v3.8.4"},
    {"/Producer": "cairo 1.17.6 (https://cairographics.org)"},
])
def test_plots_are_never_renamed(tmp_path, monkeypatch, meta):
    pdf = _make_pdf(tmp_path / "Figure1.pdf", meta)
    monkeypatch.setattr(core, "lookup", lambda *a, **k: pytest.fail("plot must not be looked up"))
    res = core.process(pdf, Config())
    assert not res.renamed and "figure" in res.reason and pdf.exists()


def test_papers_from_latex_are_not_mistaken_for_plots(tmp_path):
    pdf = _make_pdf(tmp_path / "p.pdf", {"/Creator": "LaTeX with hyperref", "/Producer": "pdfTeX-1.40.26",
                                         "/Subject": "doi:10.1000/abc"})
    assert identify(pdf).skip_reason == ""


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="R not installed")
def test_real_r_plot_is_not_renamed(tmp_path, monkeypatch):
    out = tmp_path / "Rplots.pdf"
    subprocess.run(["Rscript", "-e", f"pdf('{out}'); plot(1:10, main='Graphics Output'); invisible(dev.off())"],
                   check=True, capture_output=True)
    monkeypatch.setattr(core, "lookup", lambda *a, **k: pytest.fail("plot must not be looked up"))
    res = core.process(out, Config())
    assert not res.renamed and out.exists(), res.reason


@pytest.mark.parametrize("title", ["R Graphics Output", "Rplots", "Figure 3 panel B", "page.html"])
def test_more_junk_titles(tmp_path, title):
    pdf = _make_pdf(tmp_path / "x.pdf", {"/Title": title})
    assert identify(pdf).title_guess is None


def test_title_in_text():
    page = ("Received 3 May 2017\nAmplifiers of selection\nB. Adlam, K. Chatterjee, M. A. Nowak\n"
            "See also Wootton 2005, doi:10.1038/nature04072")
    assert title_in_text("Amplifiers of selection", page)
    assert title_in_text("Amplifiers of selection", "Amplifiersofselection by Adlam")   # spaces lost
    assert not title_in_text("Field parameterization and experimental test of the neutral "
                             "theory of biodiversity", page)


def test_reference_doi_is_rejected(tmp_path, monkeypatch):
    """A figure/paper whose only DOI is a citation must not be renamed after the cited paper."""
    from paperwatch.identify import Identifiers
    ids = Identifiers(doi="10.1038/nature04072", source="page text", text_dois=["10.1038/nature04072"],
                      text="Evolutionary dynamics on graphs\nLieberman, Hauert, Nowak\n... ref doi 10.1038/nature04072")
    pdf = _make_pdf(tmp_path / "lieberman.pdf", {})
    monkeypatch.setattr(core, "identify", lambda p: ids)
    monkeypatch.setattr(core, "lookup", lambda *a, **k: Paper(
        title="Field parameterization and experimental test of the neutral theory of biodiversity",
        authors=["Wootton"], year="2005"))
    res = core.process(pdf, Config(title_search=False))
    assert not res.renamed and "no DOI in the text matches" in res.reason


def test_verified_text_doi_is_accepted(tmp_path, monkeypatch):
    from paperwatch.identify import Identifiers
    ids = Identifiers(doi="10.1/ref", source="page text", text_dois=["10.1/ref", "10.1/own"],
                      text="Amplifiers of selection\nAdlam et al.\n10.1/ref 10.1/own")
    titles = {"10.1/ref": "Something else entirely about birds", "10.1/own": "Amplifiers of selection"}
    pdf = _make_pdf(tmp_path / "a.pdf", {})
    monkeypatch.setattr(core, "identify", lambda p: ids)
    monkeypatch.setattr(core, "lookup", lambda doi=None, **k: Paper(title=titles[doi], authors=["Adlam"], year="2015"))
    res = core.process(pdf, Config(), dry_run=True)
    assert res.target.name == "Adlam_2015_Amplifiers of selection.pdf"


@pytest.mark.parametrize("raw,fixed", [
    ("10.1101/2025.08.27.672609doi", "10.1101/2025.08.27.672609"),
    ("10.3389/fgene.2023.1230579/full", "10.3389/fgene.2023.1230579"),
    ("10.1038/s41586-020-2649-2Received", "10.1038/s41586-020-2649-2"),
])
def test_doi_tail_variants(raw, fixed):
    assert fixed in list(_doi_variants(raw))


def test_trailing_slash_dropped():
    assert find_doi("https://doi.org/10.3389/fevo.2018.00010/ more") == "10.3389/fevo.2018.00010"


def _title_ids(text):
    from paperwatch.identify import Identifiers
    return Identifiers(title_guess="Data Transformation with dplyr", source="title guess", text=text)


def test_title_search_needs_author_in_pdf(tmp_path, monkeypatch):
    pdf = _make_pdf(tmp_path / "dplyr_cheat_sheet.pdf", {})
    monkeypatch.setattr(core, "identify", lambda p: _title_ids("Data transformation with dplyr :: CHEATSHEET"))
    monkeypatch.setattr(core, "lookup", lambda *a, **k: Paper(
        title="Data Transformation with dplyr", authors=["Duggan"], year="2024"))
    res = core.process(pdf, Config())
    assert not res.renamed and "not named in this PDF" in res.reason


def test_title_search_without_authors_rejected(tmp_path, monkeypatch):
    pdf = _make_pdf(tmp_path / "shape.pdf", {})
    monkeypatch.setattr(core, "identify", lambda p: _title_ids("shape: functions for plotting"))
    monkeypatch.setattr(core, "lookup", lambda *a, **k: Paper(title="shape", authors=[], year="2008"))
    assert "no authors" in core.process(pdf, Config()).reason


def test_title_search_accepted_when_author_present(tmp_path, monkeypatch):
    pdf = _make_pdf(tmp_path / "x.pdf", {})
    monkeypatch.setattr(core, "identify", lambda p: _title_ids("Data Transformation with dplyr\nJim Duggan, Galway"))
    monkeypatch.setattr(core, "lookup", lambda *a, **k: Paper(
        title="Data Transformation with dplyr", authors=["Duggan"], year="2024"))
    assert core.process(pdf, Config(), dry_run=True).renamed


def test_author_in_text():
    from paperwatch.identify import author_in_text
    assert author_in_text("van der Walt", "S. van der Walt, NumPy")
    assert author_in_text("Mendoza-Revilla", "Javier Mendoza-Revilla1")
    assert not author_in_text("Lee", "sleep tight")


# ---------------------------------------------------------------- opt-out
def test_paperwatchignore_protects_folder_and_subfolders(tmp_path, monkeypatch):
    (tmp_path / "manuscript").mkdir()
    (tmp_path / "manuscript" / ".paperwatchignore").touch()
    (tmp_path / "manuscript" / "v2").mkdir()
    pdf = _make_pdf(tmp_path / "manuscript" / "v2" / "draft.pdf", {"/doi": "10.1000/abc"})
    monkeypatch.setattr(core, "lookup", lambda *a, **k: pytest.fail("excluded file must not be looked up"))
    res = core.process(pdf, Config())
    assert not res.renamed and ".paperwatchignore" in res.reason and pdf.exists()


@pytest.mark.parametrize("pattern", ["*.Rcheck", "*/generated/*"])
def test_exclude_patterns(tmp_path, monkeypatch, pattern):
    d = tmp_path / "pkg.Rcheck" / "generated"
    d.mkdir(parents=True)
    pdf = _make_pdf(d / "x.pdf", {"/doi": "10.1000/abc"})
    monkeypatch.setattr(core, "lookup", lambda *a, **k: pytest.fail("excluded file must not be looked up"))
    assert "excluded" in core.process(pdf, Config(exclude=[pattern])).reason


def test_review_papers_are_not_excluded_by_default(tmp_path, monkeypatch):
    d = tmp_path / "review"
    d.mkdir()
    pdf = _make_pdf(d / "post_GWAS_methods_review.pdf", {"/doi": "10.1000/abc"})
    monkeypatch.setattr(core, "lookup", lambda *a, **k: Paper(title="A review of post-GWAS prioritization approaches",
                                                             authors=["Hou"], year="2013"))
    assert core.process(pdf, Config(), dry_run=True).renamed


def test_exclude_loaded_from_config(tmp_path):
    from paperwatch import config
    f = tmp_path / "c.toml"
    f.write_text('exclude = ["*.Rcheck", "_book"]\n')
    assert config.load(f).exclude == ["*.Rcheck", "_book"]
