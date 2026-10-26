# Audit 02: Retrieval Pipeline

Scope: the path from resume/JD upload to the context handed to the LLM. Every path is relative to the repo root. Line numbers are from branch `chore/revive-local-docker-setup` at commit `f891313`.

**Bottom line:** retrieval does not run. `RAGEngine` is created fresh for every request with an empty in-memory FAISS index, and nothing ever writes documents into it. `retrieve()` therefore always returns `[]`, so the LLM never gets any retrieved context. The ChromaDB, LangChain, hybrid search, fusion and ranking described in `README.md` are not in the code.

---

## 1. What exists

| Stage | Implementation | Reference |
|---|---|---|
| Upload | `POST /generate`: an `async` route that takes the resume PDF and the JD as a form string | `backend/app/routes/cheatsheet.py:15-34` |
| Resume parsing | PyMuPDF `page.get_text()` joined into one raw string (no sectioning, cleaning or chunking) | `backend/app/service/extract_pdf.py:5-26` |
| Validation | Minimum word counts only (JD 120 words, resume 250 words) | `backend/app/service/input_validator.py:3-16` |
| Async job | Celery task calls `get_interview_cheatsheet` | `backend/app/tasks/cheatsheet_tasks.py:8-10` |
| Retriever | `RAGEngine`: lazily loads `SentenceTransformer('all-MiniLM-L6-v2')` and a `faiss.IndexFlatL2(384)` held in memory | `backend/app/service/rag_engine.py:4-23` |
| Indexing | `index_documents()` exists but is **never called anywhere in the repo** | `backend/app/service/rag_engine.py:25-28` |
| Query | `rag_engine.retrieve(job_description, top_k=3)`: the whole raw JD is the query, and the resume is not used | `backend/app/service/interview_cheatsheet.py:12-13` |
| Search | Dense L2 kNN with `top_k=3`. Invalid (`-1`) FAISS ids are filtered out | `backend/app/service/rag_engine.py:30-43` |
| Context injection | The chunks are joined with `\n\n` and put under `ADDITIONAL CONTEXT:` | `backend/app/service/interview_cheatsheet.py:14`, `backend/app/service/prompts.py:22-23` |
| LLM | Gemini (`gemini-2.5-flash` by default) with JSON-schema output | `backend/app/service/llm/gemini.py:20-31` |
| Dependencies | `faiss-cpu`, `sentence-transformers`, and CPU torch in the image. **No** `chromadb`, `langchain*`, `rank_bm25` or cross-encoder package | `backend/requirements.txt:22-26`, `backend/Dockerfile:10` |
| Infrastructure | Compose runs db, redis, backend, worker and frontend. **No ChromaDB service** and no volume for a vector store or model cache | `docker-compose.yml:1-63` |

## 2. Gaps vs the intended architecture

| Intended (README) | In code? | Evidence |
|---|---|---|
| ~4.5 GB knowledge base ingested (`README.md:17`) | **No.** The repo has no corpus, no ingestion script, no loader and no persisted index | `index_documents` is never called (`rag_engine.py:25`) |
| LangChain RecursiveCharacterTextSplitter, 600/100 (`README.md:47-51`) | **No.** LangChain is not a dependency and there is no chunking | `backend/requirements.txt` |
| ChromaDB storage with metadata and source (`README.md:79-87`) | **No.** The store is an in-memory FAISS index that is thrown away after each request | `rag_engine.py:22` |
| Extract skills, concepts, technologies and requirements from the resume and JD into queries (`README.md:104-106`) | **No.** The raw JD string is the single query, and the resume is ignored for retrieval | `interview_cheatsheet.py:13` |
| Same embedding model at ingest and query | Not testable because ingestion does not exist. The model name is hard-coded with no version pin or config, so a future ingest script could drift silently | `rag_engine.py:15` |
| Dense search in ChromaDB (`README.md:116`) | FAISS instead, and it never runs because the index is always empty | `rag_engine.py:31-33` |
| Sparse/keyword search (`README.md:127-136`) | **Does not exist.** There is no BM25, TF-IDF or keyword matching anywhere in `backend/` | none |
| Result fusion and ranking (`README.md:137-139`) | **Does not exist.** There is no RRF, no weights and no k constant | none |
| Ranked chunks handed to the LLM (`README.md:148`) | Only as a stub. Always `""` in practice | `interview_cheatsheet.py:14` |
| Metadata filtering | **Does not exist.** `self.docs` holds plain strings with no metadata | `rag_engine.py:8,28` |
| Deduplication | **Does not exist** | none |
| Reranking (cross-encoder) | **Does not exist** | none |
| "Answer only using the supplied information" (`README.md:169`) | **No.** The prompt has no grounding or citation instruction | `prompts.py:1-23` |

## 3. Bugs and risks

1. **B1. Retrieval is always empty (functional no-op).** `RAGEngine()` is built per call (`interview_cheatsheet.py:12`) with `docs=[]` (`rag_engine.py:8`), so `retrieve` returns at `rag_engine.py:31-33` every time. The only sign of this is a WARNING log line. The product is not RAG today, and `README.md` describes behaviour that does not exist.
2. **B2. Per-request state.** Even if documents were indexed, the index and model live on a short-lived instance (`interview_cheatsheet.py:12`). Each task would re-load MiniLM (about 1-3 s plus a possible first-time HF download) and re-embed the corpus. There is no singleton, and no worker-init hook in `backend/app/celery_worker.py`.
3. **B3. Query truncation and quality.** The JD has at least 120 words (`input_validator.py:3`) and is embedded as one vector. MiniLM's `max_seq_length` is 256 word-pieces, so long JDs are silently truncated, and a single averaged vector for a multi-requirement JD gives diluted recall. The resume, which carries the candidate's skills, is never part of the query.
4. **B4. Implicit normalization and metric.** `IndexFlatL2` (`rag_engine.py:22`) depends on MiniLM's built-in Normalize layer to behave like cosine. `encode()` is not called with `normalize_embeddings=True` (`rag_engine.py:26,35`), and the dimension `384` is a hard-coded literal. Swapping the model would silently break the metric or crash on a dimension mismatch.
5. **B5. No relevance threshold.** The top 3 results are returned whatever their distance (`rag_engine.py:36-43`), so irrelevant chunks would be injected. Distances `D` are thrown away.
6. **B6. Event-loop blocking.** The `async def generate_cheatsheet` route (`routes/cheatsheet.py:16`) runs the synchronous `file.file.read()` and PyMuPDF parsing (`extract_pdf.py:7,15-17`) on the event loop. A large PDF stalls every other request. The fitz `doc` is also never closed.
7. **B7. Heavy dependencies with no value.** CPU torch plus sentence-transformers plus faiss (`Dockerfile:10`, `requirements.txt:25-26`) add GBs to both the backend and worker images, yet with B1 the model code is never reached. The backend web image does not need them at all, because retrieval runs only in the worker.
8. **B8. Worker memory.** `--concurrency=2` prefork (`docker-compose.yml:41`) means that once retrieval works, each child process loads its own model and index copy. There is no shared store until Chroma (or a similar store) exists as a service.
9. **B9. LLM call has no timeout or retry.** `generate_content` (`llm/gemini.py:21`) has no timeout, the client is rebuilt per task (`interview_cheatsheet.py:19`, `gemini.py:17`), and the generic `except` returns `None` (`interview_cheatsheet.py:22-25`), so retrieval and LLM errors look the same.
10. **B10. Silent failure mode.** An empty context is not surfaced in the API response or stored on `InterviewCheatSheetModel` (`cheatsheet_tasks.py:16-23`), so there is no way to measure retrieval hit rate.

## 4. Prioritized fixes

### P0: make retrieval real

| # | Fix | Effort | Files |
|---|---|---|---|
| P0-1 | Pick one store (ChromaDB per the README, or FAISS persisted to disk) and add it to compose with a volume. Load it once per worker process (module-level singleton or the Celery `worker_process_init` signal) and stop building `RAGEngine()` per call | M | `docker-compose.yml`, `backend/app/celery_worker.py`, `backend/app/service/rag_engine.py:4-23`, `backend/app/service/interview_cheatsheet.py:12` |
| P0-2 | Write the ingestion script that does not exist yet: load the corpus, clean it, chunk it (600/100 as documented), embed it, and upsert with metadata (`source`, `category`, `company`, `doc_type`, `content_hash`). Without a corpus, retrieval cannot return anything | L | new `backend/app/ingest/` (does not exist), `backend/requirements.txt` |
| P0-3 | Put the embedding config in one place: model name, revision, `normalize_embeddings=True`, cosine/IP metric and dimension read from the model, shared by ingest and query. Store the model name in the collection metadata and assert it matches at query time | S | `backend/app/service/rag_engine.py:15,22,26,35`, `backend/app/core/config.py` |
| P0-4 | Until P0-1 and P0-2 land, either remove the RAG claims from `README.md` or raise an ERROR or metric when the index is empty instead of logging a WARNING | S | `README.md:41-148`, `backend/app/service/rag_engine.py:31-33` |

### P1: reach the intended hybrid design

| # | Fix | Effort | Files |
|---|---|---|---|
| P1-1 | Query extraction: get JD requirements, skills and technologies plus resume skills (one Gemini structured call, or a keyword/skill-taxonomy extractor) and run one short query per requirement instead of one raw JD vector | M | `backend/app/service/interview_cheatsheet.py:13`, new extractor module |
| P1-2 | Add sparse retrieval (BM25 via `rank_bm25`, or SQLite FTS / Postgres `tsvector` over the same chunk ids) for exact tech terms | M | `backend/app/service/rag_engine.py`, `backend/requirements.txt` |
| P1-3 | Fuse with RRF (`k=60`, merging per-query and per-retriever lists), take about 20 candidates per retriever, then dedupe by chunk id or `content_hash` and cap chunks per source | S | `backend/app/service/rag_engine.py:30-43` |
| P1-4 | Add a relevance threshold and use `D` (or the fused score) so low-similarity chunks are dropped rather than always passing 3 through | S | `backend/app/service/rag_engine.py:36-43` |
| P1-5 | Stop blocking the event loop: make the route a plain `def`, or run `extract_text_from_pdf` via `run_in_threadpool`, and close the fitz doc | S | `backend/app/routes/cheatsheet.py:16-23`, `backend/app/service/extract_pdf.py:7-26` |
| P1-6 | Add grounding instructions to the prompt (use the context, label each chunk with its source), and log or store the retrieved chunk ids and scores per cheatsheet | S | `backend/app/service/prompts.py:13-23`, `backend/app/tasks/cheatsheet_tasks.py:16-23` |

### P2: quality and operations

| # | Fix | Effort | Files |
|---|---|---|---|
| P2-1 | Rerank the fused top 20-30 with a cross-encoder (for example `cross-encoder/ms-marco-MiniLM-L-6-v2`, loaded once per worker) down to the final top 5-8 | M | `backend/app/service/rag_engine.py` |
| P2-2 | Metadata filters: `doc_type` by cheatsheet type (candidate vs interviewer), and `company` when it can be parsed from the JD | S | `backend/app/service/rag_engine.py`, `backend/app/service/interview_cheatsheet.py:11-16` |
| P2-3 | Bake or cache the embedding model in the worker image (`HF_HOME` volume or download at build time), and drop torch, faiss and sentence-transformers from the API image | S | `backend/Dockerfile:10-13`, `docker-compose.yml:24-50` |
| P2-4 | Reuse the Gemini client per process, and add a timeout and Celery retry with backoff | S | `backend/app/service/llm/gemini.py:17-31`, `backend/app/tasks/cheatsheet_tasks.py:8` |
| P2-5 | Add a small labelled eval set (JD to expected chunks) that reports recall@k and MRR, to tune the RRF k, top-k and threshold | M | new `backend/tests/` (none exists) |
