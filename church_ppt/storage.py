"""템플릿/설정 저장소: LocalStorage(교회 PC) | SupabaseStorage(클라우드)"""
import json
import os
import tempfile
from contextlib import contextmanager

import requests
from flask import current_app

from .errors import AppError, NotFound, StorageUnavailable
from .paths import CONFIG_FILE

DEFAULT_CONFIG = {"hymn_slots": []}
CLOUD_CONFIG_KEYS = {"hymn_slots", "slide_defaults"}  # 로컬 경로 값은 저장하지 않음
TEMPLATE_KEY = "template/base.pptx"
CONFIG_KEY = "config.json"
PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


class LocalStorage:
    mode = "local"

    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file

    def get_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"hymn_folder": "", "template_file": "", "hymn_slots": []}

    def put_config(self, cfg):
        cfg = {k: v for k, v in cfg.items() if k != "mode"}
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    @contextmanager
    def open_template(self, override=None):
        path = (
            override
            if override and os.path.exists(override)
            else self.get_config().get("template_file", "")
        )
        if not path or not os.path.exists(path):
            raise NotFound("템플릿 파일을 찾을 수 없어요")
        yield path

    def put_template(self, data):
        raise AppError("로컬 모드에서는 설정 탭에서 템플릿 경로를 지정하세요", 400)


class SupabaseStorage:
    mode = "supabase"

    def __init__(self, url, key, bucket="church-ppt", session=None, timeout=20):
        self.base = f"{url.rstrip('/')}/storage/v1/object"
        self.bucket = bucket
        self.key = key
        self.session = session or requests.Session()
        self.timeout = timeout

    def _call(self, method, obj, data=None, extra=None):
        headers = {"Authorization": f"Bearer {self.key}", "apikey": self.key}
        headers.update(extra or {})
        if method == "GET":
            url = f"{self.base}/authenticated/{self.bucket}/{obj}"
        else:
            url = f"{self.base}/{self.bucket}/{obj}"
        try:
            res = self.session.request(
                method, url, headers=headers, data=data, timeout=self.timeout
            )
        except requests.RequestException as e:
            raise StorageUnavailable(
                "저장소에 연결할 수 없어요. 로컬 모드를 사용해주세요"
            ) from e
        if res.status_code >= 500:
            raise StorageUnavailable("저장소가 응답하지 않아요. 로컬 모드를 사용해주세요")
        return res

    def _get(self, obj):
        res = self._call("GET", obj)
        if res.status_code in (400, 404):
            return None
        if res.status_code != 200:
            raise StorageUnavailable(f"저장소 오류 ({res.status_code})")
        return res.content

    def _put(self, obj, data, content_type):
        res = self._call(
            "POST", obj, data=data,
            extra={"x-upsert": "true", "Content-Type": content_type},
        )
        if res.status_code not in (200, 201):
            raise StorageUnavailable(f"저장소 저장 실패 ({res.status_code})")

    def get_config(self):
        raw = self._get(CONFIG_KEY)
        if raw is None:
            return dict(DEFAULT_CONFIG)
        cfg = json.loads(raw.decode("utf-8"))
        clean = {k: v for k, v in cfg.items() if k in CLOUD_CONFIG_KEYS}
        clean.setdefault("hymn_slots", [])
        return clean

    def put_config(self, cfg):
        clean = {k: v for k, v in cfg.items() if k in CLOUD_CONFIG_KEYS}
        self._put(
            CONFIG_KEY,
            json.dumps(clean, ensure_ascii=False).encode("utf-8"),
            "application/json",
        )

    @contextmanager
    def open_template(self, override=None):
        raw = self._get(TEMPLATE_KEY)
        if raw is None:
            raise NotFound("템플릿을 업로드해주세요")
        fd, path = tempfile.mkstemp(suffix=".pptx")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
            yield path
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def put_template(self, data):
        self._put(TEMPLATE_KEY, data, PPTX_CONTENT_TYPE)


def get_storage():
    ext = current_app.extensions
    if "storage" not in ext:
        cfg = current_app.config
        mode = cfg.get("STORAGE") or os.environ.get("STORAGE", "local")
        if mode == "supabase":
            url = cfg.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
            key = cfg.get("SUPABASE_SERVICE_KEY") or os.environ.get(
                "SUPABASE_SERVICE_KEY"
            )
            if not url or not key:
                raise RuntimeError(
                    "SUPABASE_URL / SUPABASE_SERVICE_KEY 환경변수가 필요해요"
                )
            ext["storage"] = SupabaseStorage(url, key)
        else:
            ext["storage"] = LocalStorage(cfg.get("CONFIG_FILE", CONFIG_FILE))
    return ext["storage"]
