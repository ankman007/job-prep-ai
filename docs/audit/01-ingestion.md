# Audit 01 — Ingestion Pipeline

Scope: cleaning, dedup, chunking, embedding, batching/memory, vector store setup, metadata, re-ingestion/idempotency.
Snapshot: branch `chore/revive-local-docker-setup` (HEAD `f891313`), 2026-10-17.

**Headline: none of the ingestion pipeline described in `README.md:11-87` is in the repository.** No cleaning, dedup, chunking, LangChain, or ChromaDB code exists, now or in git history (`git log --all -S chromadb` and `git log --all -S RecursiveCharacterTextSplitter` both return nothing). The only vector code is an in-memory FAISS index that nothing ever fills, so retrieval always returns nothing.

---

## 1. What exists

| Component | Location | Notes |
|---|---|---|
| Vector "engine" | `backend/app/service/rag_engine.py:4-43` | `RAGEngine` class: lazy SentenceTransformer + FAISS |
| Embedding model | `backend/app/service/rag_engine.py:15` | `SentenceTransformer('all-MiniLM-L6-v2')`, hard-coded, local (no API), 384-dim |
| Index | `backend/app/service/rag_engine.py:22` | `faiss.IndexFlatL2(384)`: in-memory, exact L2 search, dimension hard-coded |
| Indexing method | `backend/app/service/rag_engine.py:25-28` | `index_documents(list[str])`: one `encode()` over the whole list, `index.add`, `docs.extend` |
| Retrieval | `backend/app/service/rag_engine.py:30-43` | Returns `[]` if `self.docs` is empty (`:31-33`); throws away distances `D` (`:36`) |
| Sole caller | `backend/app/service/interview_cheatsheet.py:12-14` | Builds a **new** `RAGEngine()` on every request and queries it with the raw `job_description` |
| Context injection | `backend/app/service/prompts.py:22-23` | `ADDITIONAL CONTEXT: {extra_context}` |
| Dependencies | `backend/requirements.txt:21-26` | `faiss-cpu`, `sentence-transformers`, `numpy`. **No** `langchain*`, **no** `chromadb` |
| Runtime | `backend/Dockerfile:10-16`, `docker-compose.yml:24-63` | CPU torch; no ingestion entrypoint, no vector-store service, no volume for vectors or model cache (only `pgdata`, `docker-compose.yml:62-63`) |
| History | deleted `backend/app/service/embeddings.py`, `backend/app/service/vectorstore.py` (removed in `aaaadd6`) | Earlier version of the same MiniLM + `IndexFlatL2(384)` design; also never filled |

`index_documents` is never called anywhere in the codebase (searching for `index_documents` finds only its definition at `rag_engine.py:25`). There are no data files, loaders, scripts, notebooks, or CLI/Celery tasks for ingestion.

---

## 2. Gaps vs. intended architecture

| Intended (README) | Status in code |
|---|---|
| ~4.5 GB corpus (`README.md:17`) | **Missing.** No data, no loader, no path config, no reference to where the data lives |
| Cleaning: formatting removal, whitespace normalization, noise/low-info filter, standardization (`README.md:28-39`) | **Missing.** No code at all |
| Duplicate content removal (`README.md:36`) | **Missing.** No exact or near-duplicate (hash/MinHash) step |
| `RecursiveCharacterTextSplitter`, 600/100 (`README.md:47-51`) | **Missing.** LangChain is not a dependency (`requirements.txt:1-29`) |
| Separate strategy for code snippets (`README.md:60`) | **Missing.** No code detection, no `RecursiveCharacterTextSplitter.from_language` |
| Local embedding model (`README.md:66-75`) | **Partial.** MiniLM runs locally (`rag_engine.py:15`), but only the query side ever runs it, and only if docs exist |
| ChromaDB with text + metadata + source (`README.md:79-85`) | **Missing.** FAISS is used instead (`rag_engine.py:22`); only bare strings are stored (`rag_engine.py:28`) |
| Persistent index over "millions of chunks" (`README.md:87`) | **Missing.** The index lives in process memory and is rebuilt empty on every request (`interview_cheatsheet.py:12`) |
| Same embedding model for query and docs (`README.md:106-108`) | Trivially true (one hard-coded model), but there are no docs |
| Hybrid dense + sparse retrieval (`README.md:110-148`) | **Missing** (no BM25/keyword index). Out of ingestion scope, but ingestion would have to build the sparse index too |

---

## 3. Bugs / risks

1. **RAG is a silent no-op in production.** Each request runs `RAGEngine()` with `docs=[]` (`rag_engine.py:8`, `interview_cheatsheet.py:12`). `retrieve` then exits early at `rag_engine.py:31-33`, so `extra_context` is always `""` (`interview_cheatsheet.py:14`) and the prompt's `ADDITIONAL CONTEXT` is always empty (`prompts.py:22-23`). The only sign is a `logger.warning` on every request.
2. **No persistence.** FAISS sits in RAM with no `write_index`/`read_index`; `docker-compose.yml:62-63` mounts no volume for vectors. Even if `index_documents` were called, the data would vanish with the process. Celery runs 2 worker processes (`docker-compose.yml:41`), and each would hold its own separate index.
3. **Not idempotent / no IDs.** `index_documents` appends without IDs (`rag_engine.py:27-28`). Calling it twice duplicates every vector. FAISS `IndexFlatL2` has no upsert or delete-by-id, and nothing records which source a vector came from, so re-ingestion can't be done incrementally.
4. **No metadata or source.** `self.docs` is `list[str]` (`rag_engine.py:8,28`). There's no source, category (technical/system-design/behavioral/company), or chunk index, so no filtering or citation is possible.
5. **Memory blow-up on any real corpus.** `self.model.encode(documents)` (`rag_engine.py:26`) embeds the whole list in one call, with no streaming and no explicit `batch_size`/`show_progress_bar`. It also keeps every raw string in Python memory (`rag_engine.py:28`). Rough sizing: 4.5 GB at a 600/100 stride (~500 new chars per chunk) is about **9M chunks**. That's about **13.8 GB** of float32 384-d vectors, before HNSW graph overhead and before the ~4.5 GB+ of stored text. On a 20 GB machine this does not fit in one process, and it is also tight for a single Chroma HNSW collection held in memory. Without aggressive dedup/filtering or quantization, the README's "4.5 GB → Chroma on 20 GB RAM" plan doesn't fit.
6. **Embedding dimension hard-coded to the model.** `IndexFlatL2(384)` (`rag_engine.py:22`) must match `all-MiniLM-L6-v2` (`rag_engine.py:15`). Changing the model without changing this line fails at `index.add`.
7. **Distance metric unspecified and unchecked.** The index uses L2 (`rag_engine.py:22`). Vectors from `encode()` aren't explicitly normalized (`normalize_embeddings` is not passed, `rag_engine.py:26,35`). L2 only equals cosine ranking because this particular model ships a Normalize layer, so swapping models silently changes ranking. Scores `D` are thrown away (`rag_engine.py:36`), so there is no relevance threshold and irrelevant top-3 results would always be injected.
8. **Query truncation.** The raw job description is embedded as one query (`interview_cheatsheet.py:13`). MiniLM truncates input at 256 word-pieces, so most of a long JD is silently ignored, and the resume isn't used at all. On the ingestion side, 600-char chunks (~150 tokens) do fit within the limit.
9. **Model download at runtime.** The Dockerfile doesn't pre-fetch the model (`backend/Dockerfile:10-16`) and compose has no HF cache volume. The first real use downloads it inside each container, which fails in offline environments.
10. **Documentation misrepresents the system.** `README.md:15-87` describes past-tense work ("We collected and processed approximately 4.5GB…", "embeddings were generated locally…") that has no matching code. This is a credibility risk for reviewers.

---

## 4. Prioritized fixes

### P0

| # | Fix | Effort | Files |
|---|---|---|---|
| P0-1 | **Build the ingestion pipeline as an offline CLI** (e.g. `backend/ingest/` with `load.py`, `clean.py`, `split.py`, `embed_store.py`, run via `python -m ingest`). Stream files from a configurable `INGEST_DATA_DIR`. Add `langchain-text-splitters` and `chromadb` to `backend/requirements.txt:21-26`. | L | new `backend/ingest/*`, `backend/requirements.txt:21-26` |
| P0-2 | **Replace in-memory FAISS with a persistent Chroma collection.** Use `chromadb.PersistentClient(path=CHROMA_PATH)` with a named collection (e.g. `interview_kb_v1`) and `metadata={"hnsw:space": "cosine"}`. Load it once per process: use a module-level singleton instead of `RAGEngine()` per request. Add a `chroma_data` volume mounted into `backend` and `worker`. | M | `backend/app/service/rag_engine.py:4-43`, `backend/app/service/interview_cheatsheet.py:12`, `docker-compose.yml:24-63`, `backend/app/core/config.py` |
| P0-3 | **Make the empty-index state loud.** Fail the health check, or return an explicit flag, when the collection count is 0, instead of a per-request warning (`rag_engine.py:31-33`). | S | `backend/app/service/rag_engine.py:31-33`, `backend/app/routes/health.py` |
| P0-4 | **Make the README match the code.** Mark the ingestion phase as planned, or link to the pipeline once P0-1 lands. | S | `README.md:11-87` |

### P1

| # | Fix | Effort | Files |
|---|---|---|---|
| P1-1 | **Stable IDs + upsert.** `id = sha256(source_path + "\x00" + chunk_index + "\x00" + normalized_text)[:32]`, written with `collection.upsert(...)` so a re-run is a no-op. Keep a manifest (source path → content hash) so only changed files are re-ingested and chunks from deleted sources get removed. | M | new `backend/ingest/embed_store.py` |
| P1-2 | **Dedup before embedding.** Exact dedup by normalized-text SHA-256 at the document and chunk level, plus near-dup filtering (MinHash/LSH, e.g. `datasketch`) on documents. This is also the main lever for the memory problem in Risk 5. | M | new `backend/ingest/clean.py` |
| P1-3 | **Cleaning rules as tested, pure functions.** Unicode NFKC, whitespace collapse (preserving whitespace inside fenced code), boilerplate/nav stripping, min-length / alpha-ratio low-info filter, language filter. | M | new `backend/ingest/clean.py`, new `backend/tests/test_clean.py` |
| P1-4 | **Splitters.** Prose: `RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)`. Code: detect fenced or indented code blocks and split them with `RecursiveCharacterTextSplitter.from_language(Language.<lang>, chunk_size=600, chunk_overlap=100)`, so code isn't cut mid-block. Tag each chunk `content_type=code\|text`. | M | new `backend/ingest/split.py` |
| P1-5 | **Metadata schema.** For each chunk: `source` (path/URL), `doc_id`, `chunk_index`, `category`, `content_type`, `language`, `company` (if any), `ingested_at`, `pipeline_version`, `embedding_model`. Use only flat scalars, because Chroma metadata values must be str/int/float/bool. | S | new `backend/ingest/embed_store.py` |
| P1-6 | **Bounded-memory batching.** Stream documents through a generator. Embed with `model.encode(batch, batch_size=64, normalize_embeddings=True, convert_to_numpy=True)` and upsert in batches of about 1–5k, never holding the full corpus. Log progress and checkpoint the manifest so a crashed run can resume. | M | `backend/app/service/rag_engine.py:25-28` (remove or replace), new `backend/ingest/embed_store.py` |
| P1-7 | **Model and dimension from config, not literals.** Use `EMBEDDING_MODEL` as the single source for both ingest and query, read the dimension from `model.get_sentence_embedding_dimension()`, and store the model name in the collection metadata so a mismatch is refused at query time. Evaluate `BAAI/bge-small-en-v1.5` or `intfloat/e5-small-v2` (both 384-d, 512-token input) against MiniLM. | S | `backend/app/service/rag_engine.py:15,22`, `backend/app/core/config.py` |
| P1-8 | **Capacity plan for 20 GB RAM.** Measure the chunk count after dedup. If it is over about 3–4M, either split into multiple collections by category or run Chroma as a separate server process instead of in the worker. Do not embed ingestion inside the API or Celery processes (2 workers, `docker-compose.yml:41`). | S | `docker-compose.yml:39-50`, new `backend/ingest/` |

### P2

| # | Fix | Effort | Files |
|---|---|---|---|
| P2-1 | Pre-download the embedding model into the image, or mount an HF cache volume. | S | `backend/Dockerfile:10-13`, `docker-compose.yml:62-63` |
| P2-2 | Return and use similarity scores. Apply a min-score cutoff and dedupe near-identical hits before prompt injection. | S | `backend/app/service/rag_engine.py:35-43`, `backend/app/service/interview_cheatsheet.py:13-14` |
| P2-3 | Build queries from extracted JD skills plus resume gaps (multiple queries under 256 tokens each) instead of one truncated raw JD. | M | `backend/app/service/interview_cheatsheet.py:13` |
| P2-4 | Build a sparse (BM25) index during the same ingestion pass, to support the hybrid retrieval described in `README.md:110-148`. | M | new `backend/ingest/`, `backend/requirements.txt` |
| P2-5 | Add an ingestion report: docs in, dropped by each filter, dedup hits, chunks per content type, and total vectors. Add a small labelled retrieval eval set (recall@k) so changes to the splitter or model can be measured. | M | new `backend/ingest/report.py`, new `backend/tests/` |
