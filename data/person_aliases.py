"""人物畫面使用的諧音別名；slug 與來源資料仍保留原始識別。"""

from __future__ import annotations

PERSON_ALIASES: dict[str, dict[str, str]] = {
    "elon_musk": {"zh": "伊隆·馬思克", "en": "Elon Musc"},
    "jensen_huang": {"zh": "黃忍勳", "en": "Jensen Hwang"},
    "steve_jobs": {"zh": "史蒂夫·賈伯思", "en": "Steve Jobbs"},
    "bill_gates": {"zh": "比爾·蓋滋", "en": "Bill Gaits"},
    "andrew_ng": {"zh": "吳恩答", "en": "Andrew Nge"},
    "jeff_bezos": {"zh": "傑夫·貝佐思", "en": "Jeff Bezous"},
    "ray_dalio": {"zh": "瑞·達利鷗", "en": "Ray Dallio"},
    "morris_chang": {"zh": "張忠牟", "en": "Morris Choung"},
    "charlie_munger": {"zh": "查理·蒙革", "en": "Charlie Mungar"},
    "peter_thiel": {"zh": "彼得·提洱", "en": "Peter Theil"},
    "indra_nooyi": {"zh": "英德拉·努衣", "en": "Indra Nooyee"},
    "michael_porter": {"zh": "麥可·波忒", "en": "Michael Portor"},
    "sheryl_sandberg": {"zh": "雪莉·桑德柏格", "en": "Sheryl Sandburg"},
    "terry_gou": {"zh": "郭台明", "en": "Terry Ghou"},
    "warren_buffett": {"zh": "沃倫·巴非特", "en": "Warren Buffitt"},
    "sam_altman": {"zh": "山姆·奧特慢", "en": "Sam Altmen"},
    "mark_zuckerberg": {"zh": "馬克·祖克百", "en": "Mark Zuckerburg"},
    "linus_torvalds": {"zh": "林納斯·托瓦滋", "en": "Linus Torvaldz"},
    "tim_cook": {"zh": "提姆·庫刻", "en": "Tim Cooke"},
    "sundar_pichai": {"zh": "桑達爾·皮查衣", "en": "Sundar Pichay"},
    "confucius": {"zh": "孔梓", "en": "Confuzius"},
    "peter_drucker": {"zh": "彼得·杜拉刻", "en": "Peter Druker"},
    "ken_robinson": {"zh": "肯·羅賓深", "en": "Ken Robbinson"},
    "sal_khan": {"zh": "薩爾·可漢", "en": "Sal Kahn"},
    "john_dewey": {"zh": "約翰·杜薇", "en": "John Dway"},
    "maria_montessori": {"zh": "瑪利亞·蒙特梭莉", "en": "Maria Montessory"},
    "sugata_mitra": {"zh": "蘇伽特·米特啦", "en": "Sugata Mitrah"},
    "carol_dweck": {"zh": "卡羅·德韋刻", "en": "Carol Dweek"},
    "howard_gardner": {"zh": "霍華·嘉娜", "en": "Howard Gardener"},
    "paulo_freire": {"zh": "保羅·弗雷樂", "en": "Paulo Freyre"},
    "sun_tzu": {"zh": "孫梓", "en": "Sun Tsu"},
    "leonardo_da_vinci": {"zh": "李奧納多·達文希", "en": "Leonardo da Vinchi"},
    "abraham_lincoln": {"zh": "亞伯拉罕·林懇", "en": "Abraham Lincon"},
    "albert_einstein": {"zh": "阿爾伯特·愛因思坦", "en": "Albert Einsten"},
    "zhuge_liang": {"zh": "諸葛量", "en": "Zhuge Liung"},
    "napoleon_bonaparte": {"zh": "拿破倫", "en": "Napoleon Bonapart"},
    "marie_curie": {"zh": "瑪麗·居理", "en": "Marie Cury"},
    "winston_churchill": {"zh": "溫斯頓·邱吉洱", "en": "Winston Churchil"},
    "nikola_tesla": {"zh": "尼古拉·特思拉", "en": "Nikola Teslla"},
    "aristotle": {"zh": "亞里斯多得", "en": "Aristotel"},
}


def aliases_for_slug(slug: str) -> dict[str, str]:
    return PERSON_ALIASES.get(slug, {})
