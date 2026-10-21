"""
畢專：測試 Python 連線 PostgreSQL（digital_twin）
執行：./venv/bin/python connect_test.py
"""

import psycopg2
from psycopg2.extras import RealDictCursor

# 本機 Homebrew PostgreSQL 連線設定
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "digital_twin",
    "user": "kaiwei",  # 若連線失敗，終端機執行 whoami 確認使用者名
}


def main() -> None:
    print("正在連線到 PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT version();")
            row = cur.fetchone()
            print("連線成功！")
            print(f"版本：{row['version']}\n")

            # 若尚未建表，先建立（與 pgAdmin 練習用的表相同結構）
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS test_hello (
                    id SERIAL PRIMARY KEY,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """
            )

            cur.execute(
                "INSERT INTO test_hello (message) VALUES (%s) RETURNING id, message, created_at;",
                ("從 Python 寫入成功 🎉",),
            )
            inserted = cur.fetchone()
            conn.commit()
            print("已插入一筆資料：")
            print(f"  id={inserted['id']}, message={inserted['message']}, created_at={inserted['created_at']}\n")

            cur.execute("SELECT id, message, created_at FROM test_hello ORDER BY id;")
            rows = cur.fetchall()
            print(f"目前 test_hello 共有 {len(rows)} 筆：")
            for r in rows:
                print(f"  [{r['id']}] {r['message']} ({r['created_at']})")
    finally:
        conn.close()
        print("\n連線已關閉。")


if __name__ == "__main__":
    main()
