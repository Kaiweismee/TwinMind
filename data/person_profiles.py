"""
名人自我介紹與外部連結（維基、社群、官網）。
伺服器啟動時寫入 persons.bio / persons.links。
"""

from __future__ import annotations

from typing import TypedDict


class PersonLinks(TypedDict, total=False):
    wikipedia_zh: str
    wikipedia_en: str
    twitter: str
    instagram: str
    facebook: str
    linkedin: str
    youtube: str
    company: str


class PersonProfile(TypedDict):
    name_zh: str
    name_en: str
    bio: str
    links: PersonLinks


# 探索頁分類（順序即顯示順序）
PERSON_CATEGORIES: list[dict[str, str | list[str]]] = [
    {
        "id": "tech",
        "title": "科技",
        "slugs": [
            "elon_musk",
            "jensen_huang",
            "steve_jobs",
            "bill_gates",
            "sam_altman",
            "mark_zuckerberg",
            "linus_torvalds",
            "andrew_ng",
            "tim_cook",
            "sundar_pichai",
        ],
    },
    {
        "id": "education",
        "title": "教育",
        "slugs": [
            "confucius",
            "peter_drucker",
            "ken_robinson",
            "sal_khan",
            "john_dewey",
            "maria_montessori",
            "sugata_mitra",
            "carol_dweck",
            "howard_gardner",
            "paulo_freire",
        ],
    },
    {
        "id": "business",
        "title": "商業",
        "slugs": [
            "warren_buffett",
            "jeff_bezos",
            "ray_dalio",
            "morris_chang",
            "charlie_munger",
            "peter_thiel",
            "indra_nooyi",
            "michael_porter",
            "sheryl_sandberg",
            "terry_gou",
        ],
    },
    {
        "id": "historical",
        "title": "歷史",
        "slugs": [
            "sun_tzu",
            "leonardo_da_vinci",
            "abraham_lincoln",
            "albert_einstein",
            "zhuge_liang",
            "napoleon_bonaparte",
            "marie_curie",
            "winston_churchill",
            "nikola_tesla",
            "aristotle",
        ],
    },
]

SLUG_TO_CATEGORY: dict[str, str] = {}
for _cat in PERSON_CATEGORIES:
    for _slug in _cat["slugs"]:
        SLUG_TO_CATEGORY[str(_slug)] = str(_cat["id"])


def category_for_slug(slug: str) -> str:
    return SLUG_TO_CATEGORY.get(slug, "")


def _p(
    name_zh: str,
    name_en: str,
    bio: str,
    *,
    wikipedia_zh: str = "",
    wikipedia_en: str = "",
    twitter: str = "",
    instagram: str = "",
    facebook: str = "",
    linkedin: str = "",
    youtube: str = "",
    company: str = "",
) -> PersonProfile:
    links: PersonLinks = {}
    if wikipedia_zh:
        links["wikipedia_zh"] = wikipedia_zh
    if wikipedia_en:
        links["wikipedia_en"] = wikipedia_en
    if twitter:
        links["twitter"] = twitter
    if instagram:
        links["instagram"] = instagram
    if facebook:
        links["facebook"] = facebook
    if linkedin:
        links["linkedin"] = linkedin
    if youtube:
        links["youtube"] = youtube
    if company:
        links["company"] = company
    return {"name_zh": name_zh, "name_en": name_en, "bio": bio, "links": links}


PERSON_PROFILES: dict[str, PersonProfile] = {
    "elon_musk": _p(
        "伊隆·馬斯克",
        "Elon Musk",
        "我是伊隆·馬斯克，Tesla 與 SpaceX 的創辦人，也參與 Neuralink、The Boring Company 等項目。"
        "我關注可持續能源、太空探索與人工智慧，常在公開場合分享對科技與人類未來的看法。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E4%BC%8A%E9%9A%86%C2%B7%E9%A6%AC%E6%96%AF%E5%85%8B",
        wikipedia_en="https://en.wikipedia.org/wiki/Elon_Musk",
        twitter="https://x.com/elonmusk",
        instagram="https://www.instagram.com/elonmusk",
        company="https://www.tesla.com",
    ),
    "jensen_huang": _p(
        "黃仁勳",
        "Jensen Huang",
        "我是黃仁勳，NVIDIA 共同創辦人兼執行長。"
        "從 GPU 到 AI 運算平台，我長期推動加速運算在科學、產業與生成式 AI 時代的應用。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E9%BB%83%E4%BB%81%E5%8B%8B",
        company="https://www.nvidia.com",
    ),
    "steve_jobs": _p(
        "史蒂夫·賈伯斯",
        "Steve Jobs",
        "我是史蒂夫·賈伯斯，Apple 共同創辦人。"
        "我相信科技與人文的交會，致力於把複雜的創新變成直覺、優雅且改變生活的產品。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E5%96%AC%E5%B8%83%E6%96%AF",
        wikipedia_en="https://en.wikipedia.org/wiki/Steve_Jobs",
        company="https://www.apple.com",
    ),
    "bill_gates": _p(
        "比爾·蓋茲",
        "Bill Gates",
        "我是比爾·蓋茲，Microsoft 共同創辦人，現專注於比爾及梅琳達·蓋茲基金會的公益工作。"
        "我關注全球健康、教育、氣候與創新如何改善最弱勢族群的生活。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E6%AF%94%E7%88%BE%C2%B7%E8%93%8B%E8%8C%B2",
        wikipedia_en="https://en.wikipedia.org/wiki/Bill_Gates",
        twitter="https://x.com/BillGates",
        instagram="https://www.instagram.com/thisisbillgates",
        linkedin="https://www.linkedin.com/in/williamhgates",
        company="https://www.gatesfoundation.org",
    ),
    "andrew_ng": _p(
        "吳恩達",
        "Andrew Ng",
        "我是吳恩達，史丹佛大學客座教授，DeepLearning.AI 與 Coursera 共同創辦人。"
        "我致力於讓更多人能學習 AI 與機器學習，並推動 AI 在產業中負責任地落地。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E5%90%B3%E6%81%A9%E9%81%94",
        wikipedia_en="https://en.wikipedia.org/wiki/Andrew_Ng",
        twitter="https://x.com/AndrewYNg",
        linkedin="https://www.linkedin.com/in/andrewyng",
        youtube="https://www.youtube.com/@DeepLearningAI",
        company="https://www.deeplearning.ai",
    ),
    "jeff_bezos": _p(
        "傑夫·貝佐斯",
        "Jeff Bezos",
        "我是傑夫·貝佐斯，Amazon 創辦人，現領導 Blue Origin 探索太空。"
        "我長期關注長期主義、客戶至上與創新如何塑造商業與探索的邊界。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E6%9D%B0%E5%A4%AB%C2%B7%E8%B4%9D%E4%BD%90%E6%96%AF",
        wikipedia_en="https://en.wikipedia.org/wiki/Jeff_Bezos",
        instagram="https://www.instagram.com/jeffbezos",
        company="https://www.blueorigin.com",
    ),
    "ray_dalio": _p(
        "瑞·達利歐",
        "Ray Dalio",
        "我是瑞·達利歐，Bridgewater Associates 創辦人。"
        "我以原則化思考與經濟機器框架聞名，並透過著作與公開分享探討投資、組織與人生決策。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E7%91%9E%C2%B7%E9%81%94%E5%88%A9%E6%AD%90",
        wikipedia_en="https://en.wikipedia.org/wiki/Ray_Dalio",
        twitter="https://x.com/RayDalio",
        instagram="https://www.instagram.com/raydalio",
        linkedin="https://www.linkedin.com/in/raydalio",
        youtube="https://www.youtube.com/@principlesbyraydalio",
        company="https://www.bridgewater.com",
    ),
    "morris_chang": _p(
        "張忠謀",
        "Morris Chang",
        "我是張忠謀，台積電（TSMC）創辦人，被譽為晶圓代工模式的開創者。"
        "我見證並推動了半導體產業從垂直整合走向專業分工的典範轉移。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E5%BC%B5%E5%BF%A0%E8%AC%99",
        wikipedia_en="https://en.wikipedia.org/wiki/Morris_Chang",
        company="https://www.tsmc.com",
    ),
    "charlie_munger": _p(
        "查理·蒙格",
        "Charlie Munger",
        "我是查理·蒙格，Berkshire Hathaway 前副董事長，也是沃倫·巴菲特長年的思想夥伴。"
        "我提倡多元思維模型、理性決策與長期價值投資，並以直率幽默著稱。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E6%9F%A5%E7%90%86%C2%B7%E8%8E%AB%E6%A0%BC",
        wikipedia_en="https://en.wikipedia.org/wiki/Charlie_Munger",
        company="https://www.berkshirehathaway.com",
    ),
    "peter_thiel": _p(
        "彼得·提爾",
        "Peter Thiel",
        "我是彼得·提爾，PayPal 共同創辦人、Palantir 共同創辦人，也是創投家與作家。"
        "我關注科技創新、競爭策略與「從 0 到 1」的創業思維。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E5%BD%BC%E5%BE%B7%C2%B7%E6%8F%90%E7%88%BE",
        wikipedia_en="https://en.wikipedia.org/wiki/Peter_Thiel",
        twitter="https://x.com/peterthiel",
        company="https://www.palantir.com",
    ),
    "indra_nooyi": _p(
        "英德拉·努伊",
        "Indra Nooyi",
        "我是英德拉·努伊，曾任 PepsiCo 執行長。"
        "我推動『Performance with Purpose』，在成長、健康產品與永續之間尋找平衡，也是全球最具影響力的女性領袖之一。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E8%8B%B1%E5%BE%B7%E6%8B%89%C2%B7%E8%AB%BE%E4%BC%8A",
        wikipedia_en="https://en.wikipedia.org/wiki/Indra_Nooyi",
        twitter="https://x.com/IndraNooyi",
        linkedin="https://www.linkedin.com/in/indra-nooyi-531a942",
    ),
    "michael_porter": _p(
        "麥可·波特",
        "Michael Porter",
        "我是麥可·波特，哈佛商學院教授，競爭策略與國家競爭力理論的代表學者。"
        "我的研究涵蓋五力分析、價值鏈、策略定位與企業社會責任。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E9%BA%A5%E5%8F%AF%C2%B7%E6%B3%A2%E7%89%B9",
        wikipedia_en="https://en.wikipedia.org/wiki/Michael_Porter",
        company="https://www.hbs.edu/faculty/Pages/profile.aspx?facId=6532",
    ),
    "sheryl_sandberg": _p(
        "雪莉·桑德伯格",
        "Sheryl Sandberg",
        "我是雪莉·桑德伯格，曾任 Meta 營運長，也是《Lean In》作者。"
        "我長期關注女性領導力、職場平等，以及科技平台如何連結世界。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E9%9B%AA%E8%8E%89%C2%B7%E6%A1%91%E5%BE%B7%E6%A0%8A",
        wikipedia_en="https://en.wikipedia.org/wiki/Sheryl_Sandberg",
        twitter="https://x.com/sherylsandberg",
        instagram="https://www.instagram.com/sherylsandberg",
        facebook="https://www.facebook.com/sheryl",
        company="https://leanin.org",
    ),
    "terry_gou": _p(
        "郭台銘",
        "Terry Gou",
        "我是郭台銘，鴻海精密（Foxconn）創辦人。"
        "我從連接器起家，打造全球製造供應鏈體系，並長期關注製造業升級與科技產業布局。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E9%83%AD%E5%8F%B0%E9%8A%98",
        wikipedia_en="https://en.wikipedia.org/wiki/Terry_Gou",
        company="https://www.foxconn.com",
    ),
    "warren_buffett": _p(
        "沃倫·巴菲特",
        "Warren Buffett",
        "我是沃倫·巴菲特，Berkshire Hathaway 董事長，被稱為「奧马哈的先知」。"
        "我奉行價值投資與長期持有，並透過股東信與公開演講分享商業與人生的樸素智慧。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E6%B2%83%E5%80%AB%C2%B7%E5%B7%B4%E8%8F%B2%E7%89%B9",
        wikipedia_en="https://en.wikipedia.org/wiki/Warren_Buffett",
        company="https://www.berkshirehathaway.com",
    ),
    "sam_altman": _p(
        "山姆·奧特曼",
        "Sam Altman",
        "我是山姆·奧特曼，OpenAI 執行長，曾任 Y Combinator 總裁。"
        "我關注通用人工智慧的安全與益處，以及新創如何推動科技前沿。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E5%B1%B1%E5%A7%86%C2%B7%E5%A5%A7%E7%89%B9%E6%9B%BC",
        wikipedia_en="https://en.wikipedia.org/wiki/Sam_Altman",
        twitter="https://x.com/sama",
        company="https://openai.com",
    ),
    "mark_zuckerberg": _p(
        "馬克·祖克柏",
        "Mark Zuckerberg",
        "我是馬克·祖克柏，Meta 創辦人兼執行長。"
        "我創辦 Facebook 以連結世界，現正投入社群平台、VR/AR 與 AI 的下一階段。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E9%A6%AC%E5%85%8B%C2%B7%E5%B7%9D%E5%A5%87%E5%A0%A1",
        wikipedia_en="https://en.wikipedia.org/wiki/Mark_Zuckerberg",
        facebook="https://www.facebook.com/zuck",
        instagram="https://www.instagram.com/zuck",
        company="https://about.meta.com",
    ),
    "linus_torvalds": _p(
        "林納斯·托瓦茲",
        "Linus Torvalds",
        "我是林納斯·托瓦茲，Linux 核心創始人，也是 Git 版本的發明者。"
        "我相信開源協作能推動軟體創新，讓開發者自由建構與改進系統。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E6%9E%97%E7%B4%8D%E6%96%AF%C2%B7%E6%89%98%E7%93%A6%E8%8C%B2",
        wikipedia_en="https://en.wikipedia.org/wiki/Linus_Torvalds",
        company="https://www.kernel.org",
    ),
    "tim_cook": _p(
        "提姆·庫克",
        "Tim Cook",
        "我是提姆·庫克，Apple 執行長。"
        "我延續 Apple 對設計、隱私與使用者體驗的堅持，並推動供應鏈永續與服務生態成長。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E8%92%82%E5%A7%86%C2%B7%E5%BA%AB%E5%85%8B",
        wikipedia_en="https://en.wikipedia.org/wiki/Tim_Cook",
        twitter="https://x.com/tim_cook",
        company="https://www.apple.com",
    ),
    "sundar_pichai": _p(
        "桑達爾·皮查伊",
        "Sundar Pichai",
        "我是桑達爾·皮查伊，Alphabet 與 Google 執行長。"
        "我帶領 Google 在搜尋、雲端與 AI 領域創新，並思考科技如何負責任地服務全球使用者。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E6%A1%91%E9%81%94%E7%88%BE%C2%B7%E7%9A%AE%E6%9F%A5%E4%BC%8A",
        wikipedia_en="https://en.wikipedia.org/wiki/Sundar_Pichai",
        twitter="https://x.com/sundarpichai",
        company="https://about.google",
    ),
    "confucius": _p(
        "孔子",
        "Confucius",
        "我是孔子，春秋時期魯國人，儒家學派創始人。"
        "我提倡仁、義、禮、智、信，強調修身、齊家、治國、平天下，影響東亞文化兩千餘年。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E5%AD%94%E5%AD%90",
        wikipedia_en="https://en.wikipedia.org/wiki/Confucius",
    ),
    "peter_drucker": _p(
        "彼得·杜拉克",
        "Peter Drucker",
        "我是彼得·杜拉克，被譽為『現代管理學之父』。"
        "我提出目標管理、知識工作者等概念，強調組織的使命、創新與社會責任。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E5%BD%BC%E5%BE%97%C2%B7%E6%9D%9C%E9%AD%AF%E5%85%8B",
        wikipedia_en="https://en.wikipedia.org/wiki/Peter_Drucker",
    ),
    "ken_robinson": _p(
        "肯·羅賓森",
        "Ken Robinson",
        "我是肯·羅賓森，教育家與創意專家，以 TED 演講《Do Schools Kill Creativity?》廣為人知。"
        "我相信每個人都蘊含創造力，教育應釋放而非壓抑個人的獨特天賦。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E8%82%AF%C2%B7%E7%BE%85%E8%B3%93%E6%A3%AE",
        wikipedia_en="https://en.wikipedia.org/wiki/Ken_Robinson_(educationalist)",
        youtube="https://www.youtube.com/watch?v=iG9jS5R5b9A",
    ),
    "sal_khan": _p(
        "薩爾·可汗",
        "Sal Khan",
        "我是薩爾·可汗，可汗學院（Khan Academy）創辦人。"
        "我希望為全球學習者提供免費、高品質的教育資源，讓任何人、任何地方都能學習。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E8%96%A9%E7%88%BE%C2%B7%E5%8F%AF%E6%B1%97",
        wikipedia_en="https://en.wikipedia.org/wiki/Sal_Khan",
        twitter="https://x.com/sal",
        youtube="https://www.youtube.com/@khanacademy",
        company="https://www.khanacademy.org",
    ),
    "john_dewey": _p(
        "約翰·杜威",
        "John Dewey",
        "我是約翰·杜威，美國哲學家、教育家，實用主義代表人物。"
        "我主張『做中學』，認為教育應連結生活經驗、民主社會與批判思考。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E7%B4%84%E7%BF%B0%C2%B7%E6%9D%9C%E5%A8%81",
        wikipedia_en="https://en.wikipedia.org/wiki/John_Dewey",
    ),
    "maria_montessori": _p(
        "瑪利亞·蒙特梭利",
        "Maria Montessori",
        "我是瑪利亞·蒙特梭利，義大利醫師與教育家，蒙特梭利教育法創始人。"
        "我相信兒童具有內在的學習動機，環境應支持其自主探索與動手實作。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E7%91%9B%E4%B8%BD%E4%BA%9A%C2%B7%E8%92%99%E7%89%B9%E6%A2%9D%E5%88%A9",
        wikipedia_en="https://en.wikipedia.org/wiki/Maria_Montessori",
        company="https://montessori-ami.org",
    ),
    "sugata_mitra": _p(
        "蘇伽特·米特拉",
        "Sugata Mitra",
        "我是蘇伽特·米特拉，教育研究者，以『牆中洞』實驗聞名。"
        "我探索最低限度介入的教育方式，讓孩子在互聯環境中自行探索與協作學習。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E8%8B%8F%E4%BC%8A%E7%89%B9%C2%B7%E7%B1%B3%E7%89%B9%E6%8B%89",
        wikipedia_en="https://en.wikipedia.org/wiki/Sugata_Mitra",
        twitter="https://x.com/Sugatam",
    ),
    "carol_dweck": _p(
        "卡羅·德韋克",
        "Carol Dweck",
        "我是卡羅·德韋克，史丹佛大學心理學教授，成長型思維（Growth Mindset）研究代表人物。"
        "我指出：相信能力可以培養的人，更願意面對挑戰並從失敗中學習。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E5%8D%A1%E7%BE%85%C2%B7%E5%BE%B7%E9%9F%8B%E5%85%8B",
        wikipedia_en="https://en.wikipedia.org/wiki/Carol_Dweck",
        company="https://www.mindsetworks.com",
    ),
    "howard_gardner": _p(
        "霍華·嘉納",
        "Howard Gardner",
        "我是霍華·嘉納，哈佛大學教授，多元智能理論提出者。"
        "我認為人類智能並非單一 IQ 可衡量，而是包含語言、邏輯、音樂、人際等多種形式。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E9%9C%8D%E5%8D%8E%C2%B7%E5%98%89%E7%B4%8D",
        wikipedia_en="https://en.wikipedia.org/wiki/Howard_Gardner",
    ),
    "paulo_freire": _p(
        "保羅·弗雷勒",
        "Paulo Freire",
        "我是保羅·弗雷勒，巴西教育家，《被壓迫者教育學》作者。"
        "我批判填鴨式教育，主張透過對話與批判意識，讓弱勢者掌握改變處境的力量。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E4%BF%9D%E7%BE%85%C2%B7%E5%BC%97%E9%9B%B7%E5%8B%92",
        wikipedia_en="https://en.wikipedia.org/wiki/Paulo_Freire",
    ),
    "sun_tzu": _p(
        "孫子",
        "Sun Tzu",
        "我是孫子，春秋末期軍事家，《孫子兵法》相傳為我所著。"
        "我強調『知己知彼，百戰不殆』，以謀略、形勢與士氣勝過單純的武力對抗。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E5%AD%AB%E5%AD%90",
        wikipedia_en="https://en.wikipedia.org/wiki/Sun_Tzu",
    ),
    "leonardo_da_vinci": _p(
        "李奧納多·達文西",
        "Leonardo da Vinci",
        "我是李奧納多·達文西，文藝復興時期的畫家、發明家與科學觀察者。"
        "我橫跨繪畫、解剖、工程與飛行構想，相信藝術與科學是理解世界的同一條路。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E5%88%97%E5%A5%A7%E7%B4%8D%E5%A4%9A%C2%B7%E9%81%94%E6%96%87%E8%A5%BF",
        wikipedia_en="https://en.wikipedia.org/wiki/Leonardo_da_Vinci",
    ),
    "abraham_lincoln": _p(
        "亞伯拉罕·林肯",
        "Abraham Lincoln",
        "我是亞伯拉罕·林肯，美國第 16 任總統，在內戰期間維護聯邦並推動解放奴隸。"
        "我以蓋茲堡演說等文字，闡述民主、自由與國家團結的價值。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E4%BA%9E%E4%BC%AF%E6%8B%89%E7%95%95%C2%B7%E6%9E%97%E8%82%AF",
        wikipedia_en="https://en.wikipedia.org/wiki/Abraham_Lincoln",
    ),
    "albert_einstein": _p(
        "阿爾伯特·愛因斯坦",
        "Albert Einstein",
        "我是阿爾伯特·愛因斯坦，理論物理學家，提出狹義與廣義相對論。"
        "我關注自然界的簡潔與奧妙，也關心科學與人類和平、教育的關係。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E9%98%BF%E7%88%BE%E4%BC%8F%E7%89%B9%C2%B7%E6%84%9B%E5%9B%A0%E6%96%AF%E5%9D%A6",
        wikipedia_en="https://en.wikipedia.org/wiki/Albert_Einstein",
    ),
    "zhuge_liang": _p(
        "諸葛亮",
        "Zhuge Liang",
        "我是諸葛亮，三國時期蜀漢丞相，以謀略、治國與忠誠著稱。"
        "我提出『鞠躬盡瘁，死而後已』，在《出師表》中留下對理想與責任的經典表述。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E8%AB%B8%E8%91%9B%E4%BA%AE",
        wikipedia_en="https://en.wikipedia.org/wiki/Zhuge_Liang",
    ),
    "napoleon_bonaparte": _p(
        "拿破崙",
        "Napoleon Bonaparte",
        "我是拿破崙·波拿巴，法國軍事家與政治領袖，曾建立拿破崙法典並重塑歐洲格局。"
        "我的生涯結合軍事天才、行政改革與對榮耀與權力的執著追求。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E6%9C%9D%E6%8B%9C%E5%B4%94",
        wikipedia_en="https://en.wikipedia.org/wiki/Napoleon",
    ),
    "marie_curie": _p(
        "瑪麗·居禮",
        "Marie Curie",
        "我是瑪麗·居禮，物理學家與化學家，兩次諾貝爾獎得主。"
        "我與皮埃爾·居禮共同發現釙與鐳，開創放射性研究，也是首位獲諾貝爾獎的女性。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E7%91%9B%E4%B8%BD%C2%B7%E5%B1%85%E7%A4%AE",
        wikipedia_en="https://en.wikipedia.org/wiki/Marie_Curie",
    ),
    "winston_churchill": _p(
        "溫斯頓·邱吉爾",
        "Winston Churchill",
        "我是溫斯頓·邱吉爾，英國首相，在二戰關鍵時刻領導英國抵抗納粹。"
        "我以演說與寫作聞名，相信勇氣、堅持與歷史責任可以改變國家的命運。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E6%BA%AB%E6%96%AF%E9%A0%93%C2%B7%E4%B8%98%E5%90%89%E7%88%BE",
        wikipedia_en="https://en.wikipedia.org/wiki/Winston_Churchill",
    ),
    "nikola_tesla": _p(
        "尼古拉·特斯拉",
        "Nikola Tesla",
        "我是尼古拉·特斯拉，發明家與電氣工程師，推動交流電系統的應用。"
        "我構想無線通訊與電力傳輸的未來，以遠見與實驗精神探索電與磁的奧秘。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E5%B0%BC%E5%8F%A4%E6%8B%89%C2%B7%E7%89%B9%E6%96%AF%E6%8B%89",
        wikipedia_en="https://en.wikipedia.org/wiki/Nikola_Tesla",
    ),
    "aristotle": _p(
        "亞里斯多德",
        "Aristotle",
        "我是亞里斯多德，古希臘哲學家，柏拉圖的學生、亞歷山大大帝的老師。"
        "我的著作涵蓋邏輯、倫理、政治、生物學，對西方思想產生深遠影響。",
        wikipedia_zh="https://zh.wikipedia.org/wiki/%E4%BA%9E%E9%87%8C%E6%96%AF%E5%A4%9A%E5%BE%B7",
        wikipedia_en="https://en.wikipedia.org/wiki/Aristotle",
    ),
}
