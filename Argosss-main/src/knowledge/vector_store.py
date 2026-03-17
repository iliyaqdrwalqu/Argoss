from __future__ import annotations

import hashlib
import importlib
import math
import os
import re
from collections import Counter
from typing import Any

from src.argos_logger import get_logger

log = get_logger("argos.vector")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w{3,}", (text or "").lower())


class ArgosVectorStore:
    """Векторная память Аргоса.
    Предпочтительно: ChromaDB + sentence-transformers.
    Fallback: локальный cosine по bag-of-words без внешних зависимостей.
    """

    def __init__(self, path: str = "data/chroma"):
        self.path = path
        self._mode = "fallback"
        self._collection = None
        self._embedder = None
        self._fallback_docs: dict[str, dict[str, Any]] = {}
        self._init_chroma()

    @property
    def mode(self) -> str:
        return self._mode

    def _init_chroma(self):
        os.makedirs(self.path, exist_ok=True)
        try:
            if os.getenv("ARGOS_VECTOR_FORCE_FALLBACK", "").strip().lower() in {"1", "true", "on", "yes"}:
                self._mode = "fallback"
                log.info("VectorStore: fallback mode forced by ARGOS_VECTOR_FORCE_FALLBACK")
                return

            chromadb = importlib.import_module("chromadb")
            chromadb_config = importlib.import_module("chromadb.config")
            Settings = chromadb_config.Settings

            client = chromadb.PersistentClient(path=self.path, settings=Settings(anonymized_telemetry=False))

            try:
                sentence_transformers = importlib.import_module("sentence_transformers")
                SentenceTransformer = sentence_transformers.SentenceTransformer

                st_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

                class _Embedder:
                    def __init__(self, model):
                        self.model = model

                    def __call__(self, texts):
                        vecs = self.model.encode(texts)
                        return [v.tolist() for v in vecs]

                self._embedder = _Embedder(st_model)
                self._collection = client.get_or_create_collection("argos_memory", embedding_function=self._embedder)
            except Exception as e:
                # Не включаем chromadb без embedder, чтобы не триггерить дефолтный ONNX download/таймауты
                self._mode = "fallback"
                self._collection = None
                log.warning("VectorStore: sentence-transformers недоступен, fallback mode: %s", e)
                return

            self._mode = "chromadb"
            log.info("VectorStore: ChromaDB активирован (%s)", self.path)
        except Exception as e:
            self._mode = "fallback"
            log.warning("VectorStore fallback mode: %s", e)

    def upsert(self, text: str, metadata: dict[str, Any] | None = None, doc_id: str | None = None) -> str:
        if not text or not text.strip():
            return ""

        text = text.strip()
        metadata = metadata or {}
        if not doc_id:
            digest = hashlib.sha1((text + str(metadata)).encode("utf-8", errors="ignore")).hexdigest()
            doc_id = f"mem_{digest[:16]}"

        # Всегда держим локальное зеркало для мгновенного fallback-поиска
        self._fallback_docs[doc_id] = {"text": text, "metadata": metadata}

        if self._mode == "chromadb" and self._collection is not None:
            try:
                meta = {k: str(v) for k, v in metadata.items()}
                self._collection.upsert(ids=[doc_id], documents=[text], metadatas=[meta])
                return doc_id
            except Exception as e:
                log.warning("Vector upsert fallback: %s", e)
                self._mode = "fallback"
                self._collection = None
                log.info("VectorStore: переключаюсь в fallback mode после ошибки upsert")

        return doc_id

    def _fallback_search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        q_vec = Counter(q_tokens)

        scored = []
        for did, item in self._fallback_docs.items():
            d_tokens = _tokenize(item["text"])
            if not d_tokens:
                continue
            d_vec = Counter(d_tokens)
            score = self._cosine(q_vec, d_vec)
            if score > 0:
                scored.append((score, did, item))

        scored.sort(key=lambda x: -x[0])
        out = []
        for score, did, item in scored[: max(1, top_k)]:
            out.append({"id": did, "text": item["text"], "metadata": item["metadata"], "score": float(score)})
        return out

    @staticmethod
    def _cosine(a: Counter, b: Counter) -> float:
        common = set(a) & set(b)
        dot = sum(a[t] * b[t] for t in common)
        if dot == 0:
            return 0.0
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if not query or not query.strip():
            return []

        if self._mode == "chromadb" and self._collection is not None:
            try:
                res = self._collection.query(query_texts=[query], n_results=max(1, top_k))
                docs = (res.get("documents") or [[]])[0]
                ids = (res.get("ids") or [[]])[0]
                metas = (res.get("metadatas") or [[]])[0]
                dists = (res.get("distances") or [[]])[0]
                out = []
                for i, text in enumerate(docs):
                    dist = dists[i] if i < len(dists) else None
                    score = 1.0 / (1.0 + float(dist)) if dist is not None else 0.0
                    out.append({
                        "id": ids[i] if i < len(ids) else "",
                        "text": text,
                        "metadata": metas[i] if i < len(metas) else {},
                        "score": score,
                    })
                return out
            except Exception as e:
                log.warning("Vector search fallback: %s", e)
                self._mode = "fallback"
                self._collection = None
                log.info("VectorStore: переключаюсь в fallback mode после ошибки search")
                return self._fallback_search(query, top_k=top_k)

        return self._fallback_search(query, top_k=top_k)

    def status(self) -> str:
        if self._mode == "chromadb":
            return f"✅ VectorStore: ChromaDB ({self.path})"
        return "⚠️ VectorStore: fallback mode (без ChromaDB embeddings)"
