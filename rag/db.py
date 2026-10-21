"""PostgreSQL 連線（有 pgvector 時自動註冊）"""

from __future__ import annotations

import psycopg2
from psycopg2.extras import RealDictCursor

from config import DB_CONFIG


def connect():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        from pgvector.psycopg2 import register_vector

        register_vector(conn)
    except Exception:
        pass
    return conn


def connect_dict():
    conn = connect()
    return conn, RealDictCursor
