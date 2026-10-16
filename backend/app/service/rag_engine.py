import numpy as np
from loguru import logger

class RAGEngine:
    def __init__(self):
        self._model = None
        self._index = None
        self.docs = []

    @property
    def model(self):
        # Loaded lazily: importing torch and downloading the model is expensive.
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._model

    @property
    def index(self):
        if self._index is None:
            import faiss
            self._index = faiss.IndexFlatL2(384)
        return self._index

    def index_documents(self, documents: list[str]):
        embeddings = self.model.encode(documents)
        self.index.add(np.array(embeddings))
        self.docs.extend(documents)

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        if not self.docs:
            logger.warning("RAG index is empty; skipping retrieval.")
            return []

        query_emb = self.model.encode([query])
        D, I = self.index.search(np.array(query_emb), top_k)

        if I is None or len(I) == 0 or len(I[0]) == 0:
            logger.warning("No similar documents found for the given query.")
            return []

        valid_indices = [i for i in I[0] if 0 <= i < len(self.docs)]
        return [self.docs[i] for i in valid_indices]
