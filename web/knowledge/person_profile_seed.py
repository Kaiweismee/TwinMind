"""將 data/person_profiles.py 寫入 persons 表。"""

from __future__ import annotations


import psycopg2
from psycopg2.extras import Json


from web.core.rag_backend import DB_CONFIG
from data.person_profiles import PERSON_PROFILES, category_for_slug


def seed_person_profiles() -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            for slug, profile in PERSON_PROFILES.items():
                cur.execute(
                    """
                    INSERT INTO persons (slug, name_zh, name_en, bio, links, category)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (slug) DO UPDATE SET
                        name_zh = EXCLUDED.name_zh,
                        name_en = EXCLUDED.name_en,
                        bio = EXCLUDED.bio,
                        links = EXCLUDED.links,
                        category = EXCLUDED.category,
                        updated_at = NOW();
                    """,
                    (
                        slug,
                        profile["name_zh"],
                        profile["name_en"],
                        profile["bio"],
                        Json(profile["links"]),
                        category_for_slug(slug) or None,
                    ),
                )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed_person_profiles()
    print(f"Seeded {len(PERSON_PROFILES)} person profiles.")
