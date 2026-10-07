import io
import os
import sys

from flask import Flask, jsonify

from church_ppt.errors import AppError
from church_ppt.paths import BIBLE_CACHE_DIR
from church_ppt.routes import bp


def create_app(config=None):
    app = Flask(__name__, static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024
    app.config.update(config or {})
    app.register_blueprint(bp)

    @app.errorhandler(AppError)
    def _app_error(e):
        return jsonify({"error": e.message}), e.status

    @app.errorhandler(413)
    def _too_large(e):
        return jsonify({"error": "파일이 너무 커요 (최대 60MB)"}), 413

    return app


app = create_app()

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    os.makedirs("static", exist_ok=True)
    os.makedirs(BIBLE_CACHE_DIR, exist_ok=True)
    print("✝  교회 PPT 자동화 도구 시작!")
    print("브라우저에서 http://localhost:5000 을 열어주세요")
    app.run(debug=True, port=5000)
