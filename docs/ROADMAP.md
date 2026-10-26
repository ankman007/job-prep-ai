# Roadmap

A single prioritized task list, merged from the audits in `docs/audit/01-06` and `docs/ARCHITECTURE.md` (2026-10-17, branch `chore/revive-local-docker-setup` @ `f891313`).

**How to use:** take the first unchecked task in the highest priority section, do it, tick the box, and commit. Each task lists its sources (`[01]` = `docs/audit/01-ingestion.md`, and so on) for full context.

Effort: **S** = under 2h · **M** = half a day to 1 day · **L** = several days.

**Key finding:** the RAG pipeline in the README does not exist. There's no corpus, cleaning, chunking, ChromaDB, LangChain, BM25 or fusion. `interview_cheatsheet.py:12` builds a new, empty in-memory FAISS index on every request, so `ADDITIONAL CONTEXT` is always blank. Today the app is one Gemini structured-output call. Section P0-C below makes the RAG pipeline real.

Test command (see `[06]`): `python -m pytest tests -q -rxXs`. Currently 65 passed, 1 skipped, 3 xfail (strict); each xfail marks a real bug.

---

## P0: Critical

### P0-A: Security (do first, mostly S)

- [ ] **Remove `backend/dev.db` from git.** It contains a real user row and password hash. Add `*.db` to `backend/.gitignore`. Purge it from history if the user is real, and rotate that password. **S**. `backend/dev.db`, `backend/.gitignore:13-14`. [04]
- [ ] **Stop logging secrets.** Delete the raw reset-token log, take the loguru level from env (default INFO), and stop logging JWT payloads and emails. **S**. `backend/app/routes/auth.py:67,129,171,331,355`, `backend/app/core/middleware.py:6`. [04]
- [ ] **Stop exposing Postgres.** Bind it to localhost or don't publish the port, and move DB credentials to env with no `jobprep/jobprep` defaults. **S**. `docker-compose.yml:4-11,28,44`, `start.py:16,88`. [04]
- [ ] **Look tokens up by hash, not by scanning with bcrypt.** Store `sha256(token)` in an indexed, unique `token_hash` column and query by it for refresh, reset and logout. **M**. `backend/app/routes/auth.py:98-99,212-221,269-284,343,376-385`, `backend/app/db/models.py:61,74`. [04]

### P0-B: LLM output contract (prevents dashboard crashes)

- [ ] **Fix schema bugs in `response.py`.** These overlap your uncommitted edits to this file.
  - Delete the duplicate `concept_refresh.items` key. Keep one item definition with both `video_resource` and `article_resource`, and update `concept-refresh.tsx`.
  - Add a top-level `required` list with all 8 sections to `interviewer_schema`.
  - Require `recommended_next_steps` and `cultural_fit_score`.

  Then remove the `xfail` from `test_response_schemas_have_no_duplicate_keys` and `test_interviewer_schema_requires_top_level_sections`. **S**. `backend/app/schemas/response.py:111-146,201-364`, `frontend/components/concept-refresh.tsx:17,80`. [03][04][05][06]
- [ ] **Validate LLM output.** Write Pydantic v2 models mirroring both schemas (`Literal` enums, `Field(ge=0, le=100)`) and generate the Gemini JSON schema from them with `model_json_schema()`, so there is one source of truth. Validate with `model_validate_json` before saving, then remove the `xfail` from `test_cheatsheet_rejects_schema_violating_llm_output`. **M**. `backend/app/schemas/response.py`, `backend/app/service/llm/gemini.py:20-31`, `backend/app/service/interview_cheatsheet.py:20`, `backend/app/tasks/cheatsheet_tasks.py:10-23`. [03][04][06]
- [ ] **Repair, retry and add timeouts.** On `None` text, `finish_reason != STOP`, `JSONDecodeError` or `ValidationError`, re-prompt once with the error appended, then fail with a typed reason. Also:
  - Celery: `autoretry_for` transient Gemini errors with backoff, `max_retries=2` and `soft_time_limit`/`time_limit`.
  - Gemini: a request timeout.
  - Stop swallowing exceptions, so the failure reason reaches the task status.

  **M**. `backend/app/service/llm/gemini.py:20-31`, `backend/app/tasks/cheatsheet_tasks.py:8-13`, `backend/app/service/interview_cheatsheet.py:22-25`, `backend/app/celery_worker.py:16`. [03][04][02]
- [ ] **Make the frontend tolerate missing data.**
  - Add `app/results/[id]/error.tsx` and per-section error boundaries.
  - Guard every array or object access (`?? []`, `?.`) and render "Not available" for missing data.
  - Start with `interview-recommendation.tsx:120` (a live crash) and `compatibility-score.tsx:45`.

  **M**. `frontend/components/interviewer/*.tsx`, `frontend/components/{swot-analysis,skill-assessment,company-insights,concept-refresh,interview-questions}.tsx`, `frontend/app/results/[id]/page.tsx:63-81`, `frontend/components/results/interview-cheatsheet.tsx:21-22,67,74`. [05]
- [ ] **Stop one malformed sheet from crashing `/profile`.** **S**. `frontend/components/profile/cheatsheets-panel.tsx:31-69`. [05]
- [ ] **Results page states.** Add loading, not-found and unknown-type states, and fetch by id when the sheet isn't in the store. This needs a new backend `GET /user/cheatsheets/{id}`. **M**. `frontend/app/results/[id]/page.tsx:20-90`, `backend/app/routes/user.py`. [05][04]

### P0-C: Make RAG real (the core product claim)

- [ ] **Be honest about the current state now.** Mark the ingestion and retrieval sections of the README as *planned*, and log an ERROR or fail `/health` when the vector index is empty, instead of a per-request WARNING. **S**. `README.md:11-148`, `backend/app/service/rag_engine.py:31-33`, `backend/app/routes/health.py`. [01][02]
- [ ] **Persistent vector store, loaded once per process.**
  - Replace the per-request FAISS index with `chromadb.PersistentClient(path=CHROMA_PATH)`, using collection `interview_kb_v1` with `hnsw:space=cosine`.
  - Keep a module-level singleton, or load it on Celery `worker_process_init`.
  - Add a `chroma_data` volume to `backend` and `worker`, and add `chromadb` to requirements.

  **M**. `backend/app/service/rag_engine.py:4-43`, `backend/app/service/interview_cheatsheet.py:12`, `docker-compose.yml:24-63`, `backend/app/core/config.py`, `backend/requirements.txt:21-26`. [01][02]
- [ ] **One embedding config.** Read `EMBEDDING_MODEL` and its revision from config, set `normalize_embeddings=True`, and read the dimension from the model instead of the literal `384`. Store the model name in the collection metadata and assert it matches at query time. Evaluate `bge-small-en-v1.5` and `e5-small-v2` against MiniLM. **S**. `backend/app/service/rag_engine.py:15,22,26,35`, `backend/app/core/config.py`. [01][02]
- [ ] **Ingestion CLI.** Build `backend/ingest/` (`load`, `clean`, `split`, `embed_store`, run with `python -m ingest`), streaming from `INGEST_DATA_DIR`.
  - **Cleaning:** NFKC normalization, whitespace collapse that leaves code intact, boilerplate stripping, and a low-info filter based on minimum length and alpha ratio.
  - **Dedup:** exact SHA-256 at the doc and chunk level, plus MinHash near-dup filtering.
  - **Splitting:** `RecursiveCharacterTextSplitter(600, 100)` for prose and `.from_language(...)` for code blocks, tagging each chunk with `content_type`.
  - **Metadata:** flat fields `source`, `doc_id`, `chunk_index`, `category`, `content_type`, `company`, `ingested_at`, `pipeline_version` and `embedding_model`.
  - **Writes:** stable IDs (`sha256(source+idx+text)`) via `upsert`, plus a manifest for incremental re-runs.
  - **Batching:** `batch_size=64` and upsert batches of 1-5k, never holding the whole corpus in memory.
  - **Tests:** unit tests for clean and split.

  **L**. New `backend/ingest/*`, `backend/requirements.txt` (`langchain-text-splitters`, `chromadb`, `datasketch`). [01][02][06]

### P0-D: Backend correctness

- [ ] **Upload limits and non-blocking handlers.**
  - Limit size (5 MB) before reading, check content type and magic bytes, cap the page count and close the `fitz` document.
  - Return 413/415/422, using 422 rather than 404 for image-only PDFs.
  - Check `text.strip()`, not `text`.
  - Make the blocking handlers `def`, or use `run_in_threadpool`.

  **S**. `backend/app/service/extract_pdf.py:5-26`, `backend/app/routes/cheatsheet.py:15-24,52`, `backend/app/routes/user.py:12,37`. [04][02][06]
- [ ] **Alembic.** Add a baseline migration matching the current models, remove both `create_all` calls, and stop ignoring the migrations folder. **M**. `backend/app/run.py:21,38`, `backend/app/db/__init__.py:4-5`, `backend/.gitignore:17,36`, `backend/requirements.txt`. [04]
- [ ] **Tests for auth and task ownership.**
  - Auth: JWT encode/decode, expiry, `get_current_user` with the int `sub` cast, and hashing, against in-memory SQLite.
  - `GET /task-status/{id}`: another user's task returns 404, and a failed task returns a generic error.

  **M**. New `tests/test_auth.py` and `tests/test_task_status.py`, covering `backend/app/routes/auth.py`, `backend/app/core/hashing.py` and `backend/app/routes/cheatsheet.py:58`. [06]

---

## P1: Important

### Generation quality
- [ ] **Grounding, abstention and prompt-injection defense.**
  - Prompt rules: use only RESUME/JD/CONTEXT, return "Not stated" or empty arrays when information is absent, and never invent contact details, URLs or company facts.
  - Wrap inputs in `<resume>`/`<job_description>` tags marked as data, and move persona and rules to `system_instruction`.
  - Make `email`, `location` and `phone_number` nullable.

  **S**. `backend/app/service/prompts.py:3-24`, `backend/app/service/llm/gemini.py:24-29`, `backend/app/schemas/response.py:218`. [03][02]
- [ ] **Company Insights without hallucination.** Make the fields optional, add a required `source` enum (`job_description`/`none`) plus a `fallback`, and have the UI show the fallback when `source == none`. **S**. `backend/app/schemas/response.py:167-188`, `backend/app/service/prompts.py`, `frontend/components/company-insights.tsx`. [03]
- [ ] **Validate `cheatsheet_type` at the route.** Accept `Literal["candidate","interviewer"]` (return 422 otherwise), align the backend and frontend defaults, and map types in the service with an explicit dict. **S**. `backend/app/routes/cheatsheet.py:19`, `backend/app/service/interview_cheatsheet.py:16`, `backend/app/service/prompts.py:2-11`. [03][04][06][ARCH]
- [ ] **Token budget and Gemini settings.** Cap resume and JD input (~30k chars, or `count_tokens`) and return 413/400 when exceeded. Set `thinking_budget` (~2k), and log `finish_reason` and `usage_metadata` per task. **S**. `backend/app/service/input_validator.py`, `backend/app/service/llm/gemini.py:24-31`, `backend/app/routes/cheatsheet.py:18`. [03]
- [ ] **Compute `skillsDistribution` on the server** from `skillsByCategory[].status`, and add a scoring rubric (0/50/100 and levels 0-5) to the interviewer prompt. **S**. `backend/app/schemas/response.py:265-274`, `backend/app/tasks/cheatsheet_tasks.py`, `backend/app/service/prompts.py:7-9`. [03]

### Retrieval (after P0-C)
- [ ] **Query extraction.** Pull JD requirements and skills plus resume skills, and run one short query per requirement (under 256 tokens) instead of one truncated raw JD. **M**. `backend/app/service/interview_cheatsheet.py:13`, new extractor module. [02][01]
- [ ] **Sparse retrieval and RRF fusion.** Use BM25 (`rank_bm25`, or Postgres `tsvector`) over the same chunk IDs, built during ingestion. Fuse with RRF (k=60) over about 20 candidates per retriever, dedupe by `content_hash` and cap the chunks per source. **M**. `backend/app/service/rag_engine.py:30-43`, `backend/ingest/`, `backend/requirements.txt`. [02][01]
- [ ] **Relevance threshold and traceability.** Use the scores (currently `D` is thrown away), drop low-similarity chunks, and give `extra_context` a character budget. Label each chunk with its source in the prompt, and store the retrieved chunk IDs and scores with each cheatsheet. **S**. `backend/app/service/rag_engine.py:35-43`, `backend/app/service/prompts.py:13-23`, `backend/app/tasks/cheatsheet_tasks.py:16-23`. [02][01][03]
- [ ] **Capacity plan for the 20GB machine.** Measure the chunk count after dedup. Above about 3-4M, shard collections or run Chroma as its own server. Never ingest inside the API or Celery processes. **S**. `docker-compose.yml:39-50`. [01]

### Backend
- [ ] **Persist a pending cheatsheet row before queueing** and pass only its ID to the task. Check ownership for every task state, and return 404 for unknown IDs. **M**. `backend/app/routes/cheatsheet.py:28-64`, `backend/app/tasks/cheatsheet_tasks.py:9-36`, `backend/app/db/models.py:42-54`. [04]
- [ ] **Auth hardening.**
  - Status codes: return 401 "Invalid credentials" for all login failures (unknown emails currently get 404), 409 for a duplicate email, and 202 for generate.
  - Passwords and emails: enforce a minimum password length and lowercase emails.
  - Tokens: add a `token_version` claim so password changes invalidate access tokens, remove the unused `REFRESH_SECRET_KEY`, fix the algorithm to HS256 and fix `tokenUrl`.

  **M**. `backend/app/routes/auth.py`, `backend/app/db/schemas.py:7,26,33`, `backend/app/db/models.py:11-20`, `backend/.env.example:6`. [04]
- [ ] **Rate limiting** on the auth and generate endpoints (slowapi with Redis). **M**. `backend/app/run.py`, `backend/app/routes/auth.py`, `backend/app/routes/cheatsheet.py`. [04]
- [ ] **Docker hardening.** Run both images as a non-root `USER`. Add healthchecks: `/health` checking the DB and Redis for the backend, `celery inspect ping` for the worker, and one for the frontend. Use `depends_on: service_healthy` and `restart: unless-stopped`. **M**. `backend/Dockerfile`, `frontend/Dockerfile:15-23`, `docker-compose.yml:24-60`, `backend/app/routes/health.py:5-7`. [04]

### Frontend
- [ ] **One typed contract.** Create `types/cheatsheet.ts` mirroring or generated from the Pydantic models, typing `content` as `CandidateContent | InterviewerContent`. Remove the `as any` casts and `constant/interface.ts`, and parse with zod at the fetch boundary. **M**. `frontend/redux/slices/cheatsheetSlice.ts:3-10`, `frontend/app/results/[id]/page.tsx`, `frontend/constant/interface.ts`, section components. [05]
- [ ] **Fix enum mismatches between backend and frontend:**
  - question category case (`interview-questions.tsx:51-64`)
  - recommendation badge (`profile/cheatsheets-panel.tsx:92-103`)
  - screening `category`, including `cultural` and `project` (`screening-questions.tsx:12,38-41`, `response.py:155,336`)
  - the free-string `rating` (`skill-assessment.tsx:39-46`)

  **S**. [05][03]
- [ ] **Replace the 0-1 vs 0-100 scale guesses**, which overlap your uncommitted edits. Store an explicit `schema_version` or scale with each cheatsheet, and normalize legacy rows in one mapper. **M**. `frontend/components/interviewer/compatibility-score.tsx:39`, `frontend/components/interviewer/skills-assessment.tsx:91-95`, `backend/app/tasks/cheatsheet_tasks.py:156-174`. [05]
- [ ] **One API client.**
  - Read the base URL and auth header from `store.getState()`, which fixes `useSelector` being called outside a component.
  - Handle 401 centrally with a refresh-token retry.
  - Take the session expiry from the JWT `exp` claim.
  - Delete `utils.ts:14-32` and the unused, wrong-endpoint `constant/api.ts`.

  **M**. `frontend/utils.ts`, `frontend/constant/api.ts`, `frontend/redux/slices/authSlice.ts:7,83-96`, `frontend/components/{layout,cheatsheet-generator}.tsx`, `frontend/components/auth/login-form.tsx`. [05][ARCH]
- [ ] **Robust polling.** Abort on unmount, retry transient errors with backoff, handle 401 and 404, and on timeout tell the user the sheet will appear in their profile. **S**. `frontend/components/cheatsheet-generator.tsx:39-52,95-127`. [05]
- [ ] **Auth-guard `/generate`.** Wrap it in `withAuth`, honour `?redirect=`, and clear cheatsheets on logout. **S**. `frontend/app/generate/page.tsx`, `frontend/hoc/withAuth.tsx:17,22`, `frontend/redux/slices/authSlice.ts:74-81`. [05]
- [ ] **Fix the stale-file bug.** `removeFile` must notify the parent; currently the removed file still gets submitted. **S**. `frontend/components/file-uploader.tsx:81-84`, `frontend/components/cheatsheet-generator.tsx:185-188`. [05]

### Tests / CI
- [ ] **Route and task tests.** Test `POST /generate` with `TestClient` and a mocked `.delay` (non-PDF upload, invalid type, validation errors). Test that `generate_cheatsheet_task` raises on an empty result and writes the DB record (mocked session). **M**. New `tests/test_routes_cheatsheet.py` and `tests/test_tasks.py`. [06]
- [ ] **CI.** Add a GitHub Actions job that runs `python -m pytest tests -q` with the lightweight dependencies. **S**. New `.github/workflows/tests.yml`. [06][04]

---

## P2: Nice to have

- [ ] **Missing intended outputs.**
  - Interviewer: `interview_strategy` (focus areas, sequence, probes) and a dedicated `potential_concerns[]` (`type`, `evidence`, `severity`).
  - Candidate: `learning_recommendations[]` (`skill`, `why`, `search_query`, preferring search queries over invented URLs).
  - Build UI cards for each.

  **L**. `backend/app/schemas/response.py`, `frontend/app/results/[id]/page.tsx:63-85`, new components. [03][05]
- [ ] **Cross-encoder rerank.** Rerank the fused top 20-30 down to 5-8 with `ms-marco-MiniLM-L-6-v2`, loaded once per worker. **M**. `backend/app/service/rag_engine.py`. [02]
- [ ] **Metadata filters:** `doc_type` by cheatsheet type, and `company` when parsed from the JD. **S**. `backend/app/service/rag_engine.py`, `backend/app/service/interview_cheatsheet.py:11-16`. [02]
- [ ] **Retrieval eval set** of JD to expected chunks, reporting recall@k and MRR, plus an ingestion report (docs dropped per filter, dedup hits, chunks per type). **M**. New `tests/`, new `backend/ingest/report.py`. [01][02]
- [ ] **Docker image weight.** Bake in or cache the embedding model (`HF_HOME` volume), and drop torch, faiss and sentence-transformers from the API image. If RAG is abandoned, remove them entirely. **S**. `backend/Dockerfile:9-13`, `docker-compose.yml:24-63`, `backend/requirements.txt:24-26`. [01][02][04]
- [ ] **Gemini client hygiene.** Reuse one client per process, inject `BaseLLM` instead of importing `GeminiLLM` directly, raise typed errors (`input_too_long`, `model_truncated`, `invalid_output`), and validate `GEMINI_API_KEY` at worker startup. **S**. `backend/app/service/llm/gemini.py:12-31`, `backend/app/service/interview_cheatsheet.py:7-25`, `backend/app/celery_worker.py:5-16`. [02][03][04]
- [ ] **Prompt polish.** Rewrite the candidate persona as a coach, add per-section guidance, and add optional candidate-profile input passed through route, task and prompt. **M**. `backend/app/service/prompts.py`, `backend/app/routes/cheatsheet.py:16-34`, `backend/app/tasks/cheatsheet_tasks.py:9`. [03]
- [ ] **Lock dependencies.** Use pip-tools or a uv lock, pin torch and pytest dev dependencies, and pin the frontend's `"latest"` dependencies. **S**. `backend/requirements.txt`, `frontend/package.json`. [04][05]
- [ ] **Logging and errors.** Log to stdout in containers, add request-ID middleware, use a `perf_counter` timer, add a global exception handler and a consistent response envelope. **M**. `backend/app/core/middleware.py:4-21`, `backend/app/run.py:19-40`, `backend/app/routes/user.py`. [04]
- [ ] **Cheatsheets DB and API.** Index `cheatsheets.user_id` and make it non-null, add ordering and pagination to `/user/cheatsheets`, and add a delete endpoint. **M**. `backend/app/db/models.py:53`, `backend/app/routes/user.py:36-77`. [04]
- [ ] **DOCX and plain-text resume support** behind the same size and type checks, with tests. **S**. `backend/app/service/extract_pdf.py`, `backend/app/routes/cheatsheet.py:17`. [04][06]
- [ ] **Uvicorn proxy settings.** Add `--proxy-headers`, make the worker count configurable and set CORS `allow_credentials=False`. **S**. `backend/Dockerfile:20`, `backend/app/run.py:28`. [04]
- [ ] **Cheatsheets slice state.** Add `status`/`error` (or move to RTK Query), give fetch errors their own state separate from empty, and point the empty-state CTA at `/generate`. **M**. `frontend/redux/slices/cheatsheetSlice.ts`, `frontend/components/layout.tsx:33-47`, `frontend/components/profile/cheatsheets-panel.tsx:71-90`. [05]
- [ ] **Hydration fix.** Read `localStorage` in an effect, not in the initial state, and type `useDispatch<AppDispatch>`. **S**. `frontend/redux/slices/authSlice.ts:16-41`, `frontend/components/navbar.tsx:23`. [05]
- [ ] **Re-enable build checks.** Turn off `ignoreBuildErrors`/`ignoreDuringBuilds` after the typed contract lands. **S**. `frontend/next.config.mjs:4-9`. [05]
- [ ] **Wire or remove the dead buttons:** Save PDF, Print, Share and feedback. Drop `html2pdf.js` if unused. **S**. `frontend/components/results/candidate.cheatsheet.tsx:31-98`, `frontend/components/results/interview-cheatsheet.tsx:35-108`. [05]
- [ ] **Frontend cleanup.**
  - Remove debug ids, `console.log`s, the empty `redux/index.ts`, `lib/mock-*.ts` and `next/head`.
  - Fix the `skill-gaps.tsx:102,107` styling, and make the distribution in `skills-assessment.tsx:128-168` NaN-safe.
  - Allow only http/https URLs from the LLM (`concept-refresh.tsx:79-87`, `candidate-overview.tsx:75-113`).

  **S**. [05]
- [ ] **More tests:** `get_prompt` branches, `user` routes, and `RAGEngine.index_documents([])` with real FAISS in CI. **S**. [06]
- [ ] **Health ping.** Reduce keep-alive ping frequency, or move off the free-tier host that sleeps when idle. **S**. `.github/workflows/ping-health.yml:5`. [04]
