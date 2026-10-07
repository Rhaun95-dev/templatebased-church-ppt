"""공유 비밀번호 로그인 + 서명된 쿠키 세션 (APP_PASSWORD 설정 시에만 활성)"""
import hmac
import os
import time
from collections import defaultdict, deque

from flask import Blueprint, current_app, jsonify, request
from itsdangerous import BadSignature, URLSafeSerializer

COOKIE = "session_token"
TOKEN_MAX_AGE = 12 * 3600
MAX_FAILURES = 5
WINDOW_SECONDS = 300
PUBLIC = {"/api/login", "/api/logout", "/api/session"}

bp = Blueprint("auth", __name__)
_failures = defaultdict(deque)


def _cfg(name):
    return current_app.config.get(name) or os.environ.get(name) or ""


def _serializer():
    return URLSafeSerializer(_cfg("SECRET_KEY"), salt="church-ppt-session")


def _valid_cookie():
    token = request.cookies.get(COOKIE)
    if not token:
        return False
    try:
        issued = _serializer().loads(token).get("iat", 0)
    except (BadSignature, AttributeError):
        return False
    return 0 <= time.time() - issued <= TOKEN_MAX_AGE


def _limited(ip):
    q = _failures[ip]
    now = time.time()
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()
    return len(q) >= MAX_FAILURES


@bp.route("/api/session")
def session_state():
    required = bool(_cfg("APP_PASSWORD"))
    return jsonify({"auth_required": required,
                    "authenticated": (not required) or _valid_cookie()})


@bp.route("/api/login", methods=["POST"])
def login():
    password = _cfg("APP_PASSWORD")
    if not password:
        return jsonify({"ok": True})
    ip = request.remote_addr or "?"
    if _limited(ip):
        return jsonify({"error": "시도가 너무 많아요. 잠시 후 다시 시도해주세요"}), 429
    given = (request.get_json(silent=True) or {}).get("password", "")
    if not hmac.compare_digest(str(given).encode(), password.encode()):
        _failures[ip].append(time.time())
        return jsonify({"error": "비밀번호가 올바르지 않아요"}), 401
    _failures.pop(ip, None)
    res = jsonify({"ok": True})
    res.set_cookie(COOKIE, _serializer().dumps({"iat": time.time()}),
                   max_age=TOKEN_MAX_AGE, httponly=True, samesite="Lax",
                   secure=request.is_secure)
    return res


@bp.route("/api/logout", methods=["POST"])
def logout():
    res = jsonify({"ok": True})
    res.delete_cookie(COOKIE)
    return res


def init_auth(app):
    app.register_blueprint(bp)
    password = app.config.get("APP_PASSWORD") or os.environ.get("APP_PASSWORD")
    if not password:
        return
    if not (app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY")):
        raise RuntimeError("APP_PASSWORD 사용 시 SECRET_KEY 환경변수가 필요해요")
    app.config["SECRET_KEY"] = app.config.get("SECRET_KEY") or os.environ["SECRET_KEY"]

    @app.before_request
    def _guard():
        if request.path.startswith("/api/") and request.path not in PUBLIC and not _valid_cookie():
            return jsonify({"error": "로그인이 필요해요"}), 401
