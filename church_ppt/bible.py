"""성경 데이터 (bible_krv.json) 조회"""
import json
import os

from .paths import BIBLE_CACHE_DIR, BIBLE_JSON_FILE, BIBLE_META_FILE

os.makedirs(BIBLE_CACHE_DIR, exist_ok=True)

_bible_data_cache = None
_bible_meta_cache = None

BOOK_URL_MAP = {
    "GEN": "gen",
    "EXO": "exo",
    "LEV": "lev",
    "NUM": "num",
    "DEU": "deu",
    "JOS": "jos",
    "JDG": "jdg",
    "RUT": "rut",
    "1SA": "1sa",
    "2SA": "2sa",
    "1KI": "1ki",
    "2KI": "2ki",
    "1CH": "1ch",
    "2CH": "2ch",
    "EZR": "ezr",
    "NEH": "neh",
    "EST": "est",
    "JOB": "job",
    "PSA": "psa",
    "PRO": "pro",
    "ECC": "ecc",
    "SNG": "sng",
    "ISA": "isa",
    "JER": "jer",
    "LAM": "lam",
    "EZK": "ezk",
    "DAN": "dan",
    "HOS": "hos",
    "JOL": "jol",
    "AMO": "amo",
    "OBA": "oba",
    "JON": "jon",
    "MIC": "mic",
    "NAH": "nah",
    "HAB": "hab",
    "ZEP": "zep",
    "HAG": "hag",
    "ZEC": "zec",
    "MAL": "mal",
    "MAT": "mat",
    "MRK": "mrk",
    "LUK": "luk",
    "JHN": "jhn",
    "ACT": "act",
    "ROM": "rom",
    "1CO": "1co",
    "2CO": "2co",
    "GAL": "gal",
    "EPH": "eph",
    "PHP": "php",
    "COL": "col",
    "1TH": "1th",
    "2TH": "2th",
    "1TI": "1ti",
    "2TI": "2ti",
    "TIT": "tit",
    "PHM": "phm",
    "HEB": "heb",
    "JAS": "jas",
    "1PE": "1pe",
    "2PE": "2pe",
    "1JN": "1jn",
    "2JN": "2jn",
    "3JN": "3jn",
    "JUD": "jud",
    "REV": "rev",
}


def load_bible_meta():
    global _bible_meta_cache
    if _bible_meta_cache is None:
        with open(BIBLE_META_FILE, "r", encoding="utf-8") as f:
            _bible_meta_cache = json.load(f)
    return _bible_meta_cache


def get_bible_chapter(book_id: str, chapter: int) -> dict:
    global _bible_data_cache
    if _bible_data_cache is None:
        if not os.path.exists(BIBLE_JSON_FILE):
            return {"error": f"{BIBLE_JSON_FILE} 파일이 없습니다."}
        with open(BIBLE_JSON_FILE, "r", encoding="utf-8") as f:
            _bible_data_cache = json.load(f)
    book_data = _bible_data_cache.get(book_id)
    if not book_data:
        return {"error": f"{book_id} 책을 찾을 수 없습니다."}
    chapter_data = book_data.get(str(chapter))
    if not chapter_data:
        return {"error": f"{book_id} {chapter}장을 찾을 수 없습니다."}
    return {int(k): v for k, v in chapter_data.items()}


def lookup_verses(abbr, chapter, verse_start, verse_end):
    """책 약어/이름과 장·절 범위로 구절 목록을 찾는다. 실패 시 {"error": ...}"""
    meta = load_bible_meta()

    book_id = meta.get("abbr_to_id", {}).get(abbr)
    book_name = abbr
    if not book_id:
        for b in meta.get("books", []):
            if b["name"] == abbr or b["abbr"] == abbr:
                book_id = b["id"]
                book_name = b["name"]
                break
    else:
        for b in meta.get("books", []):
            if b["id"] == book_id:
                book_name = b["name"]
                break
    if not book_id:
        return {"error": f"책을 찾을 수 없어요: {abbr}"}

    chapter_data = get_bible_chapter(book_id, chapter)
    if "error" in chapter_data:
        return {"error": f'성경 데이터 오류: {chapter_data["error"]}'}

    max_verse = max(chapter_data)
    verses = []
    for v_num in range(verse_start, verse_end + 1):
        text = chapter_data.get(v_num, "")
        if text:
            verses.append({"num": v_num, "text": text})
    if not verses:
        return {
            "error": f"{book_name} {chapter}장은 {max_verse}절까지 있어요",
            "max_verse": max_verse,
        }

    ref_range = (
        f"{verse_start}-{verse_end}" if verse_start != verse_end else str(verse_start)
    )
    return {
        "verses": verses,
        "ref": f"{book_name} {chapter}:{ref_range}",
        "book_name": book_name,
        "chapter": chapter,
        "verse_start": verse_start,
        "verse_end": verse_end,
        "max_verse": max_verse,
    }
