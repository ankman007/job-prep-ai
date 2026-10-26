"""Tests for app.service.rag_engine.RAGEngine (indexing + retrieval/ranking).

The repo has no text chunker and no hybrid (BM25 + vector) fusion/RRF function;
RAGEngine is a single dense FAISS retriever. These tests cover what exists and
pin down the "no chunking" behaviour so a future chunker is a visible change.
The SentenceTransformer model and FAISS index are replaced with fakes, so no
model download, torch, or faiss install is needed.
"""
import numpy as np
import pytest

from app.service.rag_engine import RAGEngine


class FakeModel:
    """Deterministic 'embedding': [len(text), count of 'python'] padded to 384."""

    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.append(list(texts))
        out = np.zeros((len(texts), 384), dtype="float32")
        for i, t in enumerate(texts):
            out[i, 0] = len(t)
            out[i, 1] = t.lower().count("python")
        return out


class FakeIndex:
    """Records adds; search returns a scripted (D, I) pair."""

    def __init__(self, scripted_ids=None):
        self.added = []
        self.scripted_ids = scripted_ids
        self.search_calls = []

    def add(self, arr):
        self.added.append(np.asarray(arr))

    def search(self, query, k):
        self.search_calls.append((np.asarray(query), k))
        ids = self.scripted_ids if self.scripted_ids is not None else list(range(k))
        return np.zeros((1, len(ids)), dtype="float32"), np.array([ids])


def make_engine(scripted_ids=None):
    eng = RAGEngine()
    eng._model = FakeModel()
    eng._index = FakeIndex(scripted_ids)
    return eng


# --- lazy loading ---------------------------------------------------------

def test_constructor_does_not_load_model_or_index():
    eng = RAGEngine()
    assert eng._model is None
    assert eng._index is None
    assert eng.docs == []


def test_retrieve_on_empty_index_short_circuits_without_loading_model():
    eng = RAGEngine()  # real class, nothing injected
    assert eng.retrieve("python developer", top_k=3) == []
    # Must not have triggered the expensive SentenceTransformer / faiss import.
    assert eng._model is None
    assert eng._index is None


# --- indexing / "chunking" ------------------------------------------------

def test_index_documents_stores_each_document_whole_no_chunking():
    eng = make_engine()
    long_doc = "word " * 5000  # ~25k chars, far beyond any sane chunk size
    eng.index_documents([long_doc, "short doc"])

    # Current behaviour: one vector per input document, no splitting/overlap.
    assert eng.docs == [long_doc, "short doc"]
    assert eng._model.calls == [[long_doc, "short doc"]]
    assert len(eng._index.added) == 1
    assert eng._index.added[0].shape == (2, 384)


def test_index_documents_accumulates_across_calls():
    eng = make_engine()
    eng.index_documents(["a"])
    eng.index_documents(["b", "c"])
    assert eng.docs == ["a", "b", "c"]
    assert len(eng._index.added) == 2


# --- retrieval / ranking --------------------------------------------------

def test_retrieve_preserves_faiss_rank_order():
    eng = make_engine(scripted_ids=[2, 0, 1])
    eng.docs = ["doc0", "doc1", "doc2"]
    assert eng.retrieve("q", top_k=3) == ["doc2", "doc0", "doc1"]


def test_retrieve_passes_top_k_and_encodes_query_once():
    eng = make_engine(scripted_ids=[0])
    eng.docs = ["only"]
    eng.retrieve("my query", top_k=7)
    assert eng._model.calls == [["my query"]]
    (_, k), = eng._index.search_calls
    assert k == 7


def test_retrieve_drops_faiss_padding_ids_when_top_k_exceeds_corpus():
    # FAISS pads missing neighbours with -1 when k > ntotal.
    eng = make_engine(scripted_ids=[1, 0, -1, -1])
    eng.docs = ["doc0", "doc1"]
    assert eng.retrieve("q", top_k=4) == ["doc1", "doc0"]


def test_retrieve_drops_out_of_range_ids():
    eng = make_engine(scripted_ids=[0, 99])
    eng.docs = ["doc0"]
    assert eng.retrieve("q", top_k=2) == ["doc0"]


def test_retrieve_handles_empty_result_rows():
    eng = make_engine(scripted_ids=[])
    eng.docs = ["doc0"]
    assert eng.retrieve("q", top_k=3) == []


def test_end_to_end_with_real_faiss_if_installed():
    faiss = pytest.importorskip("faiss")
    eng = RAGEngine()
    eng._model = FakeModel()
    eng._index = faiss.IndexFlatL2(384)
    eng.index_documents(["python python python", "java", "python"])
    # Query embedding closest (L2) to 'python' (len 6, count 1).
    assert eng.retrieve("python", top_k=1) == ["python"]
