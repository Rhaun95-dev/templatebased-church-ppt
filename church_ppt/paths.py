"""프로젝트 경로 상수"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
BIBLE_CACHE_DIR = os.path.join(STATIC_DIR, "bible_cache")
BIBLE_META_FILE = os.path.join(STATIC_DIR, "bible_meta.json")
BIBLE_JSON_FILE = os.path.join(BIBLE_CACHE_DIR, "bible_krv.json")
