"""
TF-IDF 備援（不需下載 HuggingFace 模型，網路受限時用）

用法：
  ./venv/bin/python rag/embed_tfidf.py
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import psycopg2
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, str(Path(__file__).parent.parent / "db"))
sys.path.insert(0, str(Path(__file__).parent))

from config import DB_CONFIG

MODEL_PATH = Path(__file__).parent / "models" / "tfidf_vectorizer.pkl"


def main() -> None:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.content
                FROM chunks c
                ORDER BY c.id;
                """
            )
            rows = cur.fetchall()

        if not rows:
            print("沒有 chunks。")
            return

        ids = [r[0] for r in rows]
        texts = [r[1] for r in rows]
        print(f"共 {len(texts)} 個 chunks，建立 TF-IDF 向量 …")

        vectorizer = TfidfVectorizer(
            max_features=512,
            ngram_range=(1, 2),
            min_df=2,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(texts)

        with open(MODEL_PATH, "wb") as f:
            pickle.dump(vectorizer, f)
        print(f"✓ 模型已存：{MODEL_PATH}")

        with conn.cursor() as cur:
            for i, chunk_id in enumerate(ids):
                vec = matrix[i].toarray().flatten().tolist()
                cur.execute(
                    "UPDATE chunks SET embedding_json = %s WHERE id = %s;",
                    (json.dumps(vec), chunk_id),
                )
            conn.commit()

        print(f"✓ 已寫入 {len(ids)} 筆 embedding_json。")
        print("\n測試搜尋：")
        print('  EMBEDDING_BACKEND=tfidf ./venv/bin/python rag/query.py "AI" --person jensen_huang')
    finally:
        conn.close()


if __name__ == "__main__":
    main()
