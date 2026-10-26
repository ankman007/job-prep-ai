# 04 - Backend and Infrastructure Audit

Branch: `chore/revive-local-docker-setup` (HEAD `f891313`). Scope: `backend/`, `docker-compose.yml`, `start.py`, `frontend/Dockerfile`, `.github/workflows/`. No application code was changed.

---

## 1. What exists

### 1.1 Stack as actually implemented
| Layer | Implementation | Reference |
|---|---|---|
| API | FastAPI app factory, 4 routers | `backend/app/run.py:19-40`, `backend/main.py:3` |
| DB | SQLAlchemy 2 (sync), psycopg3, `create_all` on startup | `backend/app/db/session.py:6-8`, `backend/app/run.py:21,38` |
| Async jobs | Celery + Redis (broker and result backend) | `backend/app/celery_worker.py:7-16`, `backend/app/tasks/cheatsheet_tasks.py:8` |
| LLM | Google Gemini via `google-genai`, JSON-schema constrained output | `backend/app/service/llm/gemini.py:20-31` |
| "RAG" | In-memory FAISS `IndexFlatL2` + `all-MiniLM-L6-v2`, created per request, never populated | `backend/app/service/rag_engine.py:4-43`, `backend/app/service/interview_cheatsheet.py:12-13` |
| Resume parsing | PyMuPDF, PDF only, in-memory | `backend/app/service/extract_pdf.py:5-26` |
| Auth | HS256 JWT access token (90 min) + opaque refresh tokens (bcrypt-hashed in DB, rotation, 5-per-user cap), reset tokens | `backend/app/routes/auth.py:18-23,43-125` |
| Passwords | bcrypt over SHA-256 hex pre-hash | `backend/app/core/hashing.py:5-16` |
| Logging | loguru, request/response middleware, rotating file `api_logs.log` | `backend/app/core/middleware.py:6-21` |
| Containers | `python:3.12-slim` backend image, multi-stage Node 22 frontend, compose with Postgres 17, Redis 7, backend, worker, frontend | `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml` |
| Port picking | `start.py` scans for free host ports, writes root `.env`, runs `compose up -d --build` | `start.py:39-87` |
| Keep-alive | GH Action curls Render `/health/` every 5 min | `.github/workflows/ping-health.yml:5,13` |

### 1.2 Route inventory
| Method | Path | Handler | Auth | sync/async | Ref |
|---|---|---|---|---|---|
| POST | `/auth/sign-up` | `sign_up` | none | def | `routes/auth.py:127` |
| POST | `/auth/login` | `login` | none | def | `routes/auth.py:169` |
| POST | `/auth/refresh-token` | `refresh_token` | refresh token in body | def | `routes/auth.py:197` |
| POST | `/auth/logout` | `logout` | Bearer | def | `routes/auth.py:256` |
| POST | `/auth/logout-all` | `logout_all` | Bearer | def | `routes/auth.py:297` |
| POST | `/auth/forgot-password` | `forgot_password` | none | def | `routes/auth.py:324` |
| POST | `/auth/reset-password` | `reset_password` | reset token in body | def | `routes/auth.py:366` |
| PUT | `/auth/change-password` | `change_password` | Bearer | def | `routes/auth.py:421` |
| GET | `/auth/check-token` | `check_token` | Bearer | def | `routes/auth.py:456` |
| POST | `/cheatsheet/generate` | `generate_cheatsheet` (multipart) | Bearer | **async def** | `routes/cheatsheet.py:15` |
| GET | `/cheatsheet/task-status/{task_id}` | `get_task_status` | Bearer | **async def** | `routes/cheatsheet.py:51` |
| GET | `/user/details` | `get_user_details` | Bearer | async def | `routes/user.py:11` |
| GET | `/user/cheatsheets` | `get_user_cheatsheets` | Bearer | **async def** | `routes/user.py:36` |
| GET/HEAD | `/health/` | `health_check` | none | def | `routes/health.py:5` |

Missing for a complete product: get/delete a single cheatsheet, update profile, delete account.

### 1.3 Data model
Tables `users`, `cheatsheets`, `refresh_tokens`, `password_reset_tokens` (`backend/app/db/models.py:11-80`). No Alembic, no migrations directory; `backend/.gitignore:17,36` even ignores `*/migrations/*` and `/alembic/versions/`, so migrations could never be committed as configured.

---

## 2. Gaps vs intended architecture (README.md)

| README claim | Reality | Ref |
|---|---|---|
| LangChain RecursiveCharacterTextSplitter, 600/100 chunks (`README.md:47-51`) | LangChain is not a dependency and not imported anywhere | `backend/requirements.txt:1-29` |
| ChromaDB vector store over ~4.5 GB corpus (`README.md:17,79-87`) | No ChromaDB client, no persisted index, no Chroma service or volume in compose | `docker-compose.yml:1-63`, `rag_engine.py:18-23` |
| Hybrid dense + sparse retrieval with fusion (`README.md:110-148`) | Dense only, and the index is empty: `RAGEngine()` is constructed fresh per request and `index_documents` is never called, so `retrieve` always returns `[]` at `rag_engine.py:31-33` | `interview_cheatsheet.py:12-14` |
| Resume + JD transformed into search queries (`README.md:102-106`) | Only the raw JD is used as the query; resume is ignored for retrieval | `interview_cheatsheet.py:13` |
| Schema validation (`README.md:14-22`) | Output is `json.loads` only; no validation against the schema after generation | `gemini.py:31` |
| Ingestion pipeline (Phase 1) | No ingestion scripts exist in the repo | `git ls-files` |
| Resume upload (PDF/DOCX per audit scope) | PDF only, no DOCX support | `extract_pdf.py:7` |

Net effect: the product is currently "prompt Gemini with resume + JD"; the RAG layer is dead code that still costs ~1 GB+ of image size (torch, sentence-transformers, faiss).

---

## 3. Bugs and risks

### 3.1 Auth and secrets
- **A1 Refresh/reset lookup is an O(N) bcrypt scan across all users.** `refresh_token` loads every non-revoked refresh token in the DB and runs `bcrypt.checkpw` on each (`routes/auth.py:212-221`); `reset_password` does the same for reset tokens (`routes/auth.py:376-385`). At ~250 ms per bcrypt check this is an unauthenticated CPU-exhaustion vector and degrades linearly with users. Tokens are high-entropy (`secrets.token_urlsafe(64)`, `auth.py:98`), so a SHA-256 hash with a unique index is sufficient. Same pattern in `logout` (`auth.py:269-284`, scoped per user, less severe).
- **A2 Raw password-reset token written to logs.** `logger.debug(f"[DEV ONLY] reset token=...")` at `routes/auth.py:355`. loguru's default sink level is DEBUG, and `middleware.py:6` adds a file sink with no level filter, so tokens land in `api_logs.log` and container stdout in every environment. There is no email delivery (`auth.py:353`), so forgot-password is non-functional except via logs.
- **A3 User enumeration on login.** 404 "User not found" vs 401 "Incorrect password" (`routes/auth.py:175-181`), contradicting the anti-enumeration intent in `forgot_password` (`auth.py:328`).
- **A4 No rate limiting** on `/auth/login`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/refresh-token`, or `/cheatsheet/generate` (Gemini cost). No limiter in `requirements.txt`.
- **A5 No password policy.** `password`/`new_password` are bare `str` (`db/schemas.py:7,26,33`); empty passwords accepted.
- **A6 Access tokens survive password change/reset** for up to 90 min; only refresh tokens are revoked (`auth.py:405-410,440-445`). No `token_version`/`iat` check in `get_current_user` (`auth.py:51-89`).
- **A7 `REFRESH_SECRET_KEY` is read but unused** (`auth.py:19`); `.env.example:6` advertises it. Misleading config.
- **A8 `ALGORITHM` comes from env with no allow-list** (`auth.py:20,59`). Hard-code HS256.
- **A9 `OAuth2PasswordBearer(tokenUrl="login")`** (`auth.py:31`) points to a non-existent path and `/auth/login` takes JSON not form data, so Swagger "Authorize" does not work.
- **A10 Token lifetimes hard-coded** (`auth.py:21-23`), not configurable.
- **A11 `python-jose` is effectively unmaintained** with past CVEs (algorithm confusion, JWE DoS). Pinned `>=3.5,<4` (`requirements.txt:15`). Prefer PyJWT.
- **A12 Email uniqueness is case-sensitive** (`models.py:16`, lookups at `auth.py:132,174,334`): `A@x.com` and `a@x.com` become two accounts.
- **A13 Postgres credentials hard-coded** `jobprep/jobprep` in `docker-compose.yml:5-7,28,44` and printed by `start.py:88`, while Postgres is published on all host interfaces (`docker-compose.yml:10-11`). Anyone on the LAN can connect with known credentials.
- **A14 Committed SQLite DB with real rows.** `backend/dev.db` is tracked (since `b234d58`) and contains 1 `users` row (name, email, password hash) and 2 `refresh_tokens` hashes. `backend/.dockerignore:6` excludes it from images, but it is in git history.
- **A15 Secrets files:** root `.env` (ports only) and `backend/.env` exist locally and are gitignored (`.gitignore:1`, `backend/.gitignore:2,26`); no `.env` has ever been committed (checked `git log --all`). OK. `SECRET_KEY`/`ALGORITHM` fail-fast at import (`auth.py:25-28`) and `DATABASE_URL` fail-fast (`core/config.py:6-8`) - good. `GEMINI_API_KEY` is only checked lazily inside the worker (`gemini.py:12-15`), so a missing key surfaces as a generic task failure.
- **A16 `get_current_user` logs the full JWT payload** on missing `sub` (`auth.py:67`), and every auth route binds the user's email into logs (`auth.py:129,171,331`) - PII in log files.

### 3.2 Async correctness
- **B1 Blocking calls inside `async def` on the event loop:**
  - `generate_cheatsheet` (`routes/cheatsheet.py:16`) calls sync `extract_text_from_pdf` (blocking `file.file.read()` + CPU-bound PyMuPDF parsing, `extract_pdf.py:7-17`) and `generate_cheatsheet_task.delay(...)` (sync Redis I/O, `cheatsheet.py:28`).
  - `get_task_status` (`cheatsheet.py:52-57`) does sync Redis reads via `AsyncResult.status/.successful()/.result`.
  - `get_user_cheatsheets` (`routes/user.py:37-43`) runs a sync SQLAlchemy query and loads every cheatsheet's full JSON with no pagination.
  One slow PDF or Redis hiccup stalls every request on the single uvicorn worker (`backend/Dockerfile:20`). Fix is to declare these `def` so FastAPI runs them in the threadpool.
- **B2 Celery task has no timeouts or retries.** No `time_limit`/`soft_time_limit`, no `autoretry_for` (`cheatsheet_tasks.py:8`, `celery_worker.py:16`); the Gemini call has no timeout (`gemini.py:21-30`). A hung Gemini request pins a worker slot (concurrency 2, `docker-compose.yml:41`) indefinitely.
- **B3 Errors are swallowed then re-raised as a generic error.** `get_interview_cheatsheet` catches everything and returns `None` (`interview_cheatsheet.py:22-25`); the task then raises `RuntimeError("...no content")` (`cheatsheet_tasks.py:11-13`). Root cause (bad key, quota, invalid JSON, invalid `cheatsheet_type`) is lost from the task result.
- **B4 Full resume text (PII) travels through Redis** as task args and the task result (`cheatsheet.py:28-34`, `cheatsheet_tasks.py:29-36`), kept 1 h (`celery_worker.py:16`), with no Redis auth (`docker-compose.yml:17-22`). Pass the cheatsheet/upload row ID instead.
- **B5 Task status leaks across users for non-success states.** Ownership is checked only when `successful()` (`cheatsheet.py:56-60`); any authenticated user can probe arbitrary task IDs for PENDING/STARTED/FAILURE. Unknown IDs return `PENDING` forever, not 404.

### 3.3 File upload handling
- **C1 No size limit.** `file.file.read()` reads the entire upload into memory (`extract_pdf.py:7`); no `Content-Length` check and no limit in uvicorn/FastAPI config. Multi-hundred-MB uploads are accepted.
- **C2 No type check.** `UploadFile.content_type` and extension are never inspected (`cheatsheet.py:17`); validation is "does PyMuPDF open it". PyMuPDF will also open XPS/EPUB/images given a stream, and `filetype="pdf"` is only a hint.
- **C3 No page-count or decompression-bomb guard.** Loops over all pages (`extract_pdf.py:15-17`); a 10,000-page PDF is parsed synchronously on the event loop (see B1).
- **C4 `fitz.Document` never closed** (`extract_pdf.py:7-26`) - native memory held until GC.
- **C5 Wrong status codes:** empty text returns **404** (`extract_pdf.py:24`), should be 422 (and scanned/image-only PDFs need a clear message); extraction failure returns 500 (`extract_pdf.py:20`) for what is a client-file problem.
- **C6 `cheatsheet_type` is unvalidated.** Any string is accepted (`cheatsheet.py:19`); `get_prompt` raises `ValueError` for unknown values (`prompts.py:10-11`), which happens in the worker, gets swallowed (B3), and surfaces as a generic failure instead of a 422 at the API.
- **C7 Filename stored unsanitized** (`cheatsheet.py:24`, `models.py:51`) - fine for DB, but rendered back to the frontend.
- **C8 No temp files** are written (all in-memory), so there is no cleanup issue. DOCX is not supported at all.

### 3.4 Database and migrations
- **D1 No migration tool.** Schema changes rely on `Base.metadata.create_all`, which never alters existing tables. `create_all` is called twice per startup (`run.py:21` via `db/__init__.py:4-5`, and `run.py:38`). Every column added since the first deploy (e.g. `bio`, `location`, `job_title`, `filename`) will be missing on an existing Render/Postgres DB.
- **D2 Migrations are gitignored** (`backend/.gitignore:17,36`).
- **D3 Missing index on `cheatsheets.user_id`** (`models.py:53`) - the primary query in `user.py:43` filters on it. `cheatsheets.user_id` is nullable (`models.py:53`).
- **D4 `token_hash` not indexed/unique** (`models.py:61,74`) - root of A1.
- **D5 No `updated_at`, no ordering** on cheatsheet listing (`user.py:43`) - order is undefined in Postgres.
- **D6 `resume_text`/`job_description` stored in plaintext** (`models.py:46-47`) with no retention policy; resume PII duplicated in Redis (B4).
- **D7 Engine has default pool settings** (`session.py:6`); with uvicorn threadpool (40 threads) plus 2 Celery processes that is fine locally, but there is no `pool_size`/`max_overflow` tuning for hosted Postgres connection limits.

### 3.5 Error handling and HTTP status codes
- **E1 Inconsistent envelopes.** Success bodies use `{status,message,...}` (`auth.py:155-159`), errors use FastAPI's `{detail}`; task status uses a different shape (`cheatsheet.py:54`). No global exception handler in `run.py`.
- **E2 Status code issues:** duplicate email returns 400 (should be 409, `auth.py:135-138`); login unknown user 404 (A3); empty PDF 404 (C5); `/cheatsheet/generate` returns 200 for an accepted async job (should be 202, `cheatsheet.py:15`).
- **E3 Pointless try/except** around attribute access in `user.py:15-33` and per-row in `user.py:54-65`.
- **E4 `IntegrityError` race on sign-up** is handled (`auth.py:160-166`) - good.

### 3.6 Logging and CORS
- **F1 File log sink written to CWD at import time** (`middleware.py:6`): inside the container that is `/app/api_logs.log` in the writable layer as root, lost on recreate and duplicated in every Celery worker process that imports it. Use stdout only in containers.
- **F2 Default level is DEBUG** in all environments (no `logger.remove()`/level config anywhere); combined with A2 and A16.
- **F3 Middleware logs full URL including query strings** (`middleware.py:12`); `uuid` is imported but no request ID is generated or propagated (`middleware.py:4`). Uses `datetime.now()` instead of `time.perf_counter()` (`middleware.py:10,16`).
- **F4 CORS** reads `CORS_ORIGINS` with a default that includes the production Vercel origin (`run.py:13-17`); compose overrides it (`docker-compose.yml:30`). `allow_credentials=True` with `allow_methods/headers=["*"]` (`run.py:28-30`) is acceptable because origins are explicit, but credentials are not used (Bearer tokens), so `allow_credentials` can be False.

### 3.7 Docker, compose, deploy
- **G1 Backend image runs as root** (`backend/Dockerfile` has no `USER`). Celery will also warn about running as root (worker shares the image, `docker-compose.yml:39-41`).
- **G2 Image weight from dead code.** CPU torch (unpinned, `backend/Dockerfile:10`) + `sentence-transformers` + `faiss-cpu` + `numpy` (`requirements.txt:24-26`) are installed for a RAG path that never runs (section 2). Single-stage build, no `--no-install-recommends`/build cache mounts.
- **G3 No healthchecks** for `backend`, `worker`, or `frontend` (`docker-compose.yml:24-60`); `frontend` uses plain `depends_on: [backend]` (`docker-compose.yml:59-60`). `/health/` does not check DB or Redis (`routes/health.py:5-7`).
- **G4 No `restart:` policies** on any service.
- **G5 Volumes:** Postgres has a named volume (`docker-compose.yml:9,62-63`) - good. No volume for a vector store (none exists) and no HF model cache volume, so if the embedding model were ever used it would download on every container recreate (`rag_engine.py:15`). Redis has no persistence (acceptable for a broker, but task results are lost on restart).
- **G6 Postgres port published to host** (`docker-compose.yml:10-11`) with default credentials (A13). Not needed for the app; should be opt-in or bound to `127.0.0.1`.
- **G7 Frontend image runs as root** (`frontend/Dockerfile:15-23`, no `USER node`). `NEXT_PUBLIC_API_BASE_URL` is baked at build (`frontend/Dockerfile:10-11`, `docker-compose.yml:56`), so a port change requires a rebuild (handled by `start.py:82 --build`, but slow).
- **G8 Uvicorn runs one process with no `--proxy-headers`** (`backend/Dockerfile:20`); behind Render's proxy `req.client.host` (used in every auth log, `auth.py:129`) is the proxy IP.
- **G9 `start.py` runs `compose down` on every start** (`start.py:68`) and rewrites root `.env` dropping comments/unknown formatting (`start.py:35-36`). Port check-then-use is racy but acceptable for local dev.
- **G10 Keep-alive cron every 5 min** (`ping-health.yml:5`) burns ~8,600 Action runs/month and only exists to defeat Render free-tier sleep.

### 3.8 Requirements
- **H1 No lockfile; ranges only** (`requirements.txt:2-29`); `python-multipart>=0.0.32` has no upper bound (`requirements.txt:6`); torch is fully unpinned in the Dockerfile (`backend/Dockerfile:10`). Builds are not reproducible.
- **H2 `pytest` in runtime requirements** (`requirements.txt:29`) and there are zero tests in the repo.
- **H3 Dead/unused deps:** `sentence-transformers`, `faiss-cpu`, `torch` (see G2). Missing deps for the intended architecture: `langchain-text-splitters`, `chromadb`, `alembic`, a DOCX parser.

### 3.9 Uncommitted change worth flagging
- **I1 Duplicate `"items"` key in `candidate_schema.concept_refresh`** (`backend/app/schemas/response.py:114-145`, modified in working tree). Python keeps only the second dict, so `article_resource` (`:126-128`) is silently discarded and only `video_resource` is enforced. Pick one or merge both fields.
- **I2 `interviewer_schema` has no top-level `required`** (`response.py:201-364`), so Gemini may omit whole sections the frontend renders unconditionally.

---

## 4. Prioritized fixes

Effort: S = under 2 h, M = half to 1 day, L = multi-day.

### P0 - fix before any shared/hosted deployment
| # | Fix | Effort | Files |
|---|---|---|---|
| P0-1 | Replace bcrypt-scan token lookup with `sha256(token)` stored in an indexed unique `token_hash`; query by hash (refresh, reset, logout). | M | `backend/app/routes/auth.py:98-99,212-221,269-284,343,376-385`, `backend/app/db/models.py:61,74` |
| P0-2 | Delete the raw reset-token debug log; set loguru level from env (INFO default); stop logging JWT payloads and emails. | S | `backend/app/routes/auth.py:67,129,171,331,355`, `backend/app/core/middleware.py:6` |
| P0-3 | Enforce upload limits: max size (e.g. 5 MB) before read, content-type/magic-byte check, max pages, close the document; return 413/415/422. | S | `backend/app/service/extract_pdf.py:5-26`, `backend/app/routes/cheatsheet.py:15-24` |
| P0-4 | Make blocking handlers `def` (or offload with `run_in_threadpool`). | S | `backend/app/routes/cheatsheet.py:16,52`, `backend/app/routes/user.py:12,37` |
| P0-5 | Remove `backend/dev.db` from git (and history if the user row is real); add `*.db` to `backend/.gitignore`. | S | `backend/dev.db`, `backend/.gitignore:13-14` |
| P0-6 | Stop publishing Postgres on all interfaces; move DB credentials to env with no defaults in compose. | S | `docker-compose.yml:4-11,28,44`, `start.py:16,88` |
| P0-7 | Introduce Alembic with a baseline migration matching current models; remove both `create_all` calls; un-ignore migrations. | M | `backend/app/run.py:21,38`, `backend/app/db/__init__.py:4-5`, `backend/.gitignore:17,36`, `backend/requirements.txt` |

### P1 - correctness, security hardening, reliability
| # | Fix | Effort | Files |
|---|---|---|---|
| P1-1 | Validate `cheatsheet_type` as `Literal["interviewer","candidate"]` at the API (422). | S | `backend/app/routes/cheatsheet.py:19`, `backend/app/service/prompts.py:10-11` |
| P1-2 | Celery: `soft_time_limit`/`time_limit`, `autoretry_for` transient Gemini errors with backoff, Gemini request timeout; stop swallowing exceptions so failure reason is recorded. | M | `backend/app/tasks/cheatsheet_tasks.py:8-13`, `backend/app/service/interview_cheatsheet.py:22-25`, `backend/app/service/llm/gemini.py:21-30`, `backend/app/celery_worker.py:16` |
| P1-3 | Persist a pending cheatsheet row first and pass only its ID to the task; check ownership for every task state, 404 unknown IDs. | M | `backend/app/routes/cheatsheet.py:28-64`, `backend/app/tasks/cheatsheet_tasks.py:9-36`, `backend/app/db/models.py:42-54` |
| P1-4 | Unify login failure to 401 "Invalid credentials"; 409 on duplicate email; 202 on generate. | S | `backend/app/routes/auth.py:135-138,175-181`, `backend/app/routes/cheatsheet.py:15` |
| P1-5 | Rate limiting (e.g. slowapi + Redis) on auth and generate endpoints. | M | `backend/app/run.py`, `backend/app/routes/auth.py`, `backend/app/routes/cheatsheet.py` |
| P1-6 | Password policy (min length) in schemas; normalize email to lowercase. | S | `backend/app/db/schemas.py:7,26,33`, `backend/app/routes/auth.py:132,141-148,174,334` |
| P1-7 | Invalidate access tokens on password change/reset (`token_version` claim), remove unused `REFRESH_SECRET_KEY`, hard-code HS256, make lifetimes configurable, fix `tokenUrl`. | M | `backend/app/routes/auth.py:19-23,31,51-89,402-445`, `backend/app/db/models.py:11-20`, `backend/.env.example:6` |
| P1-8 | Docker hardening: non-root `USER` in both images, healthchecks for backend (`/health/` checking DB + Redis), worker (`celery inspect ping`), frontend; `restart: unless-stopped`; `depends_on: condition: service_healthy`. | M | `backend/Dockerfile`, `frontend/Dockerfile:15-23`, `docker-compose.yml:24-60`, `backend/app/routes/health.py:5-7` |
| P1-9 | Fix duplicate `items` key and add top-level `required` to interviewer schema; validate LLM output against schema (e.g. `jsonschema`) before saving. | S | `backend/app/schemas/response.py:111-146,201-364`, `backend/app/service/llm/gemini.py:31` |
| P1-10 | Decide on RAG: either implement the README design (Chroma persistent volume + ingestion script + LangChain splitter + hybrid retrieval, singleton client) or remove torch/sentence-transformers/faiss and correct the README. | L (implement) / S (remove) | `backend/app/service/rag_engine.py`, `backend/app/service/interview_cheatsheet.py:12-14`, `backend/requirements.txt:24-26`, `backend/Dockerfile:9-10`, `docker-compose.yml`, `README.md:47-148` |

### P2 - quality and maintainability
| # | Fix | Effort | Files |
|---|---|---|---|
| P2-1 | Lock dependencies (pip-tools/uv lock), pin torch, move pytest to dev requirements. | S | `backend/requirements.txt`, `backend/Dockerfile:10-13` |
| P2-2 | Log to stdout only in containers; add request-ID middleware; use `perf_counter`; log path not full URL. | S | `backend/app/core/middleware.py:4-21` |
| P2-3 | Index `cheatsheets.user_id`, make it non-null, add ordering + pagination to `/user/cheatsheets`, add single-get/delete endpoints. | M | `backend/app/db/models.py:53`, `backend/app/routes/user.py:36-77` |
| P2-4 | Global exception handler and consistent response envelope; drop redundant try/except. | M | `backend/app/run.py:19-40`, `backend/app/routes/user.py:15-33,54-65` |
| P2-5 | DOCX resume support (python-docx) behind the same size/type checks. | S | `backend/app/service/extract_pdf.py`, `backend/app/routes/cheatsheet.py:17` |
| P2-6 | Uvicorn `--proxy-headers --forwarded-allow-ips`, configurable workers; `allow_credentials=False`. | S | `backend/Dockerfile:20`, `backend/app/run.py:28` |
| P2-7 | Validate `GEMINI_API_KEY` at worker startup (fail fast). | S | `backend/app/celery_worker.py:5-16`, `backend/app/service/llm/gemini.py:12-15` |
| P2-8 | Add a minimal pytest suite (auth flow, upload validation, task-status ownership) and CI job. | M | `backend/` (new `tests/`), `.github/workflows/` |
| P2-9 | Reduce keep-alive frequency or move off free-tier sleep. | S | `.github/workflows/ping-health.yml:5` |
