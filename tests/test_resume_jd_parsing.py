"""Resume / JD parsing: PDF text extraction (app.service.extract_pdf) and the
word-count input validation (app.service.input_validator).

Only PDF is supported by the backend; there is no DOCX or plain-text resume
extraction helper (see docs/audit/06-tests.md, gaps).
"""
import io
from types import SimpleNamespace

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import HTTPException  # noqa: E402

from app.service.input_validator import (  # noqa: E402
    MIN_JOB_DESC_WORDS,
    MIN_RESUME_WORDS,
    validate_inputs,
    validate_word_count,
)


def upload(data: bytes):
    """Minimal stand-in for fastapi.UploadFile (only .file is used)."""
    return SimpleNamespace(file=io.BytesIO(data), filename="resume.pdf")


def words(n):
    return " ".join(f"w{i}" for i in range(n))


# --- PDF extraction (real pymupdf, PDFs generated in memory) -------------

@pytest.fixture
def pdf_mod():
    pytest.importorskip("pymupdf")
    from app.service import extract_pdf
    return extract_pdf


def make_pdf(pages):
    import pymupdf
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_extracts_text_from_all_pages_in_order(pdf_mod):
    data = make_pdf(["Jane Doe Senior Python Engineer", "Experience at Acme Corp"])
    text = pdf_mod.extract_text_from_pdf(upload(data))
    assert "Jane Doe Senior Python Engineer" in text
    assert "Experience at Acme Corp" in text
    assert text.index("Jane Doe") < text.index("Acme Corp")


def test_pdf_without_text_raises_404(pdf_mod):
    data = make_pdf([None])  # blank page, e.g. scanned image-only resume
    with pytest.raises(HTTPException) as exc:
        pdf_mod.extract_text_from_pdf(upload(data))
    assert exc.value.status_code == 404


@pytest.mark.parametrize("data", [b"", b"this is not a pdf", b"%PDF-1.4 garbage"])
def test_invalid_pdf_bytes_raise_400(pdf_mod, data):
    with pytest.raises(HTTPException) as exc:
        pdf_mod.extract_text_from_pdf(upload(data))
    assert exc.value.status_code in (400, 404)
    # Corrupt input must never surface as a 500.
    assert exc.value.status_code != 500


def test_page_extraction_error_raises_500(pdf_mod, monkeypatch):
    class BrokenDoc:
        page_count = 1

        def load_page(self, n):
            raise RuntimeError("boom")

    monkeypatch.setattr(pdf_mod.fitz, "open", lambda **kw: BrokenDoc())
    with pytest.raises(HTTPException) as exc:
        pdf_mod.extract_text_from_pdf(upload(b"x"))
    assert exc.value.status_code == 500


def test_whitespace_only_pdf_text_is_rejected_downstream(pdf_mod, monkeypatch):
    # extract_text_from_pdf only checks `if not text`, so whitespace passes it;
    # validate_inputs is what ultimately rejects the resume.
    class Page:
        def get_text(self):
            return "  \n\n "

    class Doc:
        page_count = 2

        def load_page(self, n):
            return Page()

    monkeypatch.setattr(pdf_mod.fitz, "open", lambda **kw: Doc())
    text = pdf_mod.extract_text_from_pdf(upload(b"x"))
    assert text.strip() == ""
    with pytest.raises(HTTPException) as exc:
        validate_inputs(text, words(MIN_JOB_DESC_WORDS))
    assert exc.value.status_code == 400
    assert "Found 0 words" in exc.value.detail


# --- word-count validation -----------------------------------------------

def test_thresholds():
    assert MIN_JOB_DESC_WORDS == 120
    assert MIN_RESUME_WORDS == 250


def test_validate_inputs_accepts_exact_minimums():
    validate_inputs(words(MIN_RESUME_WORDS), words(MIN_JOB_DESC_WORDS))


def test_resume_one_word_short_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_inputs(words(MIN_RESUME_WORDS - 1), words(MIN_JOB_DESC_WORDS))
    assert exc.value.status_code == 400
    assert exc.value.detail.startswith("Resume content is too short")
    assert f"Found {MIN_RESUME_WORDS - 1} words" in exc.value.detail


def test_job_description_checked_first():
    with pytest.raises(HTTPException) as exc:
        validate_inputs("", "")
    assert exc.value.detail.startswith("Job description is too short")


def test_word_count_splits_on_any_whitespace():
    text = "a\tb\nc  d\r\ne"
    validate_word_count("X", text, 5)
    with pytest.raises(HTTPException):
        validate_word_count("X", text, 6)
