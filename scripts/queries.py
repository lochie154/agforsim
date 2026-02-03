# queries.py
"""
Multilingual search queries for agroforestry / food forestry / permaculture /
syntropic agriculture and related concepts.
"""

QUERIES = {
    "en": [
        "agroforestry",
        "food forest",
        "forest garden",
        "syntropic agriculture",
        "regenerative agriculture",
        "permaculture",
        "silvopasture",
        "agroecology",
        "polyculture",
    ],
    "pt": [
        "agrofloresta",
        "sistema agroflorestal",
        "agroflorestal",
        "agricultura sintrópica",
        "agricultura regenerativa",
        "agroecologia",
    ],
    "es": [
        "agroforestería",
        "bosque de alimentos",
        "bosque comestible",
        "agricultura sintrópica",
        "agricultura regenerativa",
        "agroecología",
    ],
    "nl": [
        "voedselbos",
        "agrobosbouw",
    ],
    "fr": [
        "agroforesterie",
        "forêt nourricière",
        "forêt comestible",
        "agroécologie",
    ],
    "ru": [
        "агролесоводство",
        "лесосад",
        "агроэкология",
    ],
    "zh": [
        "农林复合",
        "食物森林",
        "永续农业",
        "农林牧复合",
    ],
    "ja": [
        "アグロフォレストリー",
        "フードフォレスト",
        "パーマカルチャー",
        "里山",
    ],
}


def iter_queries():
    """Yield (language_code, query_string) pairs."""
    for lang, terms in QUERIES.items():
        for term in terms:
            yield lang, term
