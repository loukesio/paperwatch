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
