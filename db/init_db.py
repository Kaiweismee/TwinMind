"""
執行建表 SQL（不需開 pgAdmin）
用法：cd ~/Desktop/digital_twin_project && ./venv/bin/python db/init_db.py
"""

from pathlib import Path

import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "digital_twin",
    "user": "kaiwei",
}

DB_DIR = Path(__file__).parent
SQL_FILES = [
    "schema.sql",
    # "schema_pgvector.sql",  # 安裝 pgvector 後取消註解
    # "seed_sample.sql",      # 需要範例資料時取消註解
]


def run_sql_file(conn, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    print(f"執行：{path.name}")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"  ✓ 完成\n")


def main() -> None:
    print("連線 digital_twin ...")
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        for name in SQL_FILES:
            run_sql_file(conn, DB_DIR / name)
        print("全部建表完成。請到 pgAdmin 重新整理 Tables 查看。")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
