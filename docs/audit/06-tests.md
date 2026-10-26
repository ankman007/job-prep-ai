# 06 - Backend Test Audit

## How to run

```
# from repo root, in any venv with: pytest fastapi pymupdf jsonschema numpy loguru python-multipart
python -m pytest tests -q -rxXs
```

There is no backend venv in the repo. The run below used a throwaway Python 3.12 venv
with only the lightweight packages listed above. torch, sentence-transformers, faiss and
google-genai were **not** installed: the model and index are faked, and `tests/conftest.py`
stubs `google.genai` when it is missing.

**Result (2026-10-17):** `65 passed, 1 skipped, 3 xfailed in 9.09s`
- Skipped: `test_end_to_end_with_real_faiss_if_installed` (faiss not installed; `importorskip`).
- The 3 xfails are `strict=True` and each one is a real bug (see section 3).

## 1. What exists (prior coverage)

- **None.** The repo had no `tests/`, `backend/tests/`, `conftest.py` or `test_*.py` files.
  `pytest` is listed in `backend/requirements.txt`, but nothing used it, and CI
  (`.github/workflows/ping-health.yml`) only pings a health endpoint.
- Architecture differs from the brief: there is **no LangChain, no ChromaDB, no chunker
  and no hybrid/fusion retrieval**. Retrieval is a single dense FAISS `IndexFlatL2` over
  `all-MiniLM-L6-v2` embeddings (`backend/app/service/rag_engine.py`). The LLM output
  "schemas" are plain JSON-Schema dicts sent to Gemini as `response_json_schema`
  (`backend/app/schemas/response.py`), not Pydantic models. The only Pydantic models are
  the auth request models in `backend/app/db/schemas.py`.

## 2. Tests added

| File | Covers |
|---|---|
| `tests/conftest.py` | Adds `backend/` to `sys.path`. Stubs `google.genai` / `google.genai.types` only when the SDK is not installed. |
| `tests/test_rag_retrieval.py` (10) | `RAGEngine`: the constructor stays lazy; `retrieve` on an empty index returns `[]` without loading the model or FAISS. **Chunking:** pins down that `index_documents` stores each document whole (one vector per doc, no size/overlap), and that docs accumulate across calls. **Ranking:** FAISS rank order is kept; `top_k` is passed through; the query is encoded once; FAISS `-1` padding and out-of-range IDs are dropped; empty result rows are handled. There is also an optional real-FAISS end-to-end test, skipped when faiss is missing. |
| `tests/test_llm_output_schema.py` (45) | Both schemas pass `Draft202012Validator.check_schema` and are JSON-serialisable. Valid candidate and interviewer payloads pass. Payloads fail when required fields are missing (top-level and nested) or malformed (out-of-range scores 0-100 and levels 0-5, enum violations, wrong types). **LLM text to JSON** (`GeminiLLM.generate`, client mocked): raises when the API key is missing; parses JSON; sends the model, `response_mime_type=application/json` and the schema; raises `JSONDecodeError` on malformed or truncated text and `TypeError` when `response.text is None`. **Orchestration** (`get_interview_cheatsheet`, LLM mocked): picks the schema by type; returns `None` on parse failure and on an invalid type (the LLM is not called); the prompt's RAG context is always empty. |
| `tests/test_resume_jd_parsing.py` (14) | `extract_text_from_pdf`, using real pymupdf with PDFs built in memory: text from multiple pages comes out in order; a PDF with no text gives 404; empty, garbage or corrupt bytes give 400 and never 500; a page-extraction error gives 500; whitespace-only text gets past the extractor but `validate_inputs` then rejects it. `validate_inputs` / `validate_word_count`: threshold values, exact-minimum boundaries, one-word-short cases, the JD is checked before the resume, and words are split on any whitespace. |

## 3. Bugs found by tests (xfail strict)

1. **Duplicate `items` key in `candidate_schema.concept_refresh`.** See
   `backend/app/schemas/response.py:114` and `:130`. Python keeps the second key without
   warning, so the `article_resource` item schema at lines 114-129 is dead code. The
   effective schema requires `video_resource`, which matches
   `frontend/components/concept-refresh.tsx`. Fix: delete the first block.
   Test: `test_response_schemas_have_no_duplicate_keys`.
2. **`interviewer_schema` has no top-level `required`.** See
   `backend/app/schemas/response.py:201-364`. A payload of `{}` is valid, so Gemini can
   leave out whole sections and the interviewer components get `undefined`. The candidate
   schema does have this list. Test: `test_interviewer_schema_requires_top_level_sections`.
3. **LLM output is never validated after parsing.** See
   `backend/app/service/llm/gemini.py:31` (`json.loads(response.text)`) and
   `backend/app/service/interview_cheatsheet.py:20`. The code relies only on Gemini's
   structured-output mode. A response that breaks the schema is saved to the DB and
   returned as it is. Test: `test_cheatsheet_rejects_schema_violating_llm_output`.

Observed but not marked xfail (design issues):
- **RAG is dead code in production.** `interview_cheatsheet.py:12` builds a new, empty
  `RAGEngine()` on every request, and nothing ever calls `index_documents`. `retrieve`
  therefore always returns `[]` and `ADDITIONAL CONTEXT` is always blank (pinned by
  `test_cheatsheet_prompt_has_empty_rag_context`).
- `routes/cheatsheet.py:19` accepts any `cheatsheet_type`. An invalid value is queued
  first and only fails later, asynchronously, in the Celery task.
- `extract_pdf.py:22` checks `if not text` instead of `if not text.strip()`. It also
  returns 404 for an image-only PDF (422 fits better) and never closes the `fitz`
  document.

## 4. Remaining coverage gaps

| Pri | Gap | Effort |
|---|---|---|
| P0 | Fix and then un-xfail the 3 bugs above. After parsing, add `jsonschema` validation (or Pydantic models generated from the schemas), plus a retry or a clear error. | S |
| P0 | Auth: JWT encode/decode, expiry, `get_current_user` (recent fix `4cc2934` casts `sub` to int), password hashing in `core/hashing.py`. Use SQLite in memory. | M |
| P0 | Task ownership check in `GET /task-status/{id}` (`routes/cheatsheet.py:58`). Test with `AsyncResult` mocked: another user's task gives 404, a failed task gives a generic error. | S |
| P1 | Route tests for `POST /generate` with `TestClient` (Celery `.delay` mocked): validation errors pass through, non-PDF upload, invalid `cheatsheet_type`. | M |
| P1 | `generate_cheatsheet_task`: raises when the result is empty, writes the DB record (session mocked), return shape. | S |
| P1 | Chunking / hybrid retrieval do not exist. If RAG is going to be real, add a chunker (size/overlap) and a corpus-loading path, then test them. Otherwise remove `RAGEngine`, `faiss-cpu` and `sentence-transformers` (heavy dependencies that are never used in practice). | M-L |
| P1 | CI: run `pytest tests` in GitHub Actions with these lightweight deps. | S |
| P2 | DOCX and plain-text resume input are not supported, so there is nothing to test. Add them if the product needs them. | M |
| P2 | `get_prompt` role branches and contents; `user` routes (profile, change password). | S |
| P2 | `RAGEngine.index_documents([])` edge case, real-FAISS test in CI. | S |
