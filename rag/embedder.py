"""文字 → 向量（本機模型或 OpenAI）"""

from __future__ import annotations

import os
from typing import Sequence

# 避免錯誤的系統 Proxy 導致 HuggingFace 下載模型失敗
for _k in list(os.environ.keys()):
    if "proxy" in _k.lower():
        os.environ.pop(_k, None)

from config import (
    EMBEDDING_BACKEND,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    OPENAI_EMBEDDING_DIM,
    OPENAI_EMBEDDING_MODEL,
)

_local_model = None


def embedding_dimension() -> int:
    if EMBEDDING_BACKEND == "openai":
        return OPENAI_EMBEDDING_DIM
    return EMBEDDING_DIM


def _get_local_model():
    global _local_model
    if _local_model is None:
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        from sentence_transformers import SentenceTransformer

        print(f"載入本機模型：{EMBEDDING_MODEL} …")
        print("（首次會從 HuggingFace 下載，約 400MB，請保持網路暢通）")
        _local_model = SentenceTransformer(EMBEDDING_MODEL)
    return _local_model


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    if not texts:
        return []

    if EMBEDDING_BACKEND == "openai":
        return _embed_openai(texts)

    if EMBEDDING_BACKEND == "tfidf":
        return _embed_tfidf(texts)

    model = _get_local_model()
    vectors = model.encode(
        list(texts),
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 64,
    )
    return [v.tolist() for v in vectors]


def _embed_tfidf(texts: Sequence[str]) -> list[list[float]]:
    import pickle
    from pathlib import Path

    path = Path(__file__).parent / "models" / "tfidf_vectorizer.pkl"
    if not path.exists():
        raise RuntimeError(
            "請先執行：./venv/bin/python rag/embed_tfidf.py"
        )
    with open(path, "rb") as f:
        vectorizer = pickle.load(f)
    matrix = vectorizer.transform(list(texts))
    return [row.toarray().flatten().tolist() for row in matrix]


def _embed_openai(texts: Sequence[str]) -> list[list[float]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("請設定環境變數 OPENAI_API_KEY，或改用 EMBEDDING_BACKEND=local")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=list(texts))
    return [item.embedding for item in resp.data]
