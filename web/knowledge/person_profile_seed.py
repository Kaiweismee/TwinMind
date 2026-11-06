"""將 data/person_profiles.py 寫入 persons 表。"""

from __future__ import annotations


import psycopg2
from psycopg2.extras import Json


from web.core.rag_backend import DB_CONFIG
from data.person_profiles import PERSON_PROFILES, category_for_slug
from data.person_aliases import aliases_for_slug


def _display_bio(slug: str, bio: str) -> str:
    text = bio or ""
    for person_slug, profile in PERSON_PROFILES.items():
        alias = aliases_for_slug(person_slug)
        if not alias:
            continue
        for key, target in (("name_zh", alias["zh"]), ("name_en", alias["en"])):
            source = profile.get(key) or ""
            if source:
                text = text.replace(source, target)
    return text


def seed_person_profiles() -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            for slug, profile in PERSON_PROFILES.items():
                cur.execute(
                    """
                    INSERT INTO persons (
                        slug, name_zh, name_en, display_name_zh, display_name_en,
                        bio, display_bio, links, category, avatar_url, avatar_source
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (slug) DO UPDATE SET
                        name_zh = EXCLUDED.name_zh,
                        name_en = EXCLUDED.name_en,
                        display_name_zh = EXCLUDED.display_name_zh,
                        display_name_en = EXCLUDED.display_name_en,
                        bio = EXCLUDED.bio,
                        display_bio = EXCLUDED.display_bio,
                        links = EXCLUDED.links,
                        category = EXCLUDED.category,
                        avatar_url = EXCLUDED.avatar_url,
                        avatar_source = EXCLUDED.avatar_source,
                        updated_at = NOW();
                    """,
                    (
                        slug,
                        profile["name_zh"],
                        profile["name_en"],
                        aliases_for_slug(slug)["zh"],
                        aliases_for_slug(slug)["en"],
                        profile["bio"],
                        _display_bio(slug, profile["bio"]),
                        Json(profile["links"]),
                        category_for_slug(slug) or None,
                        f"/static/avatars/{slug}-ai.png",
                        "ai-generated-illustration",
                    ),
                )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed_person_profiles()
    print(f"Seeded {len(PERSON_PROFILES)} person profiles.")
