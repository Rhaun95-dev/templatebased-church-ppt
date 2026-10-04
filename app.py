import io
import os
import sys

from flask import Flask

from church_ppt.paths import BIBLE_CACHE_DIR
from church_ppt.routes import bp

app = Flask(__name__, static_folder="static")
app.register_blueprint(bp)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


if __name__ == "__main__":
    os.makedirs("static", exist_ok=True)
    os.makedirs(BIBLE_CACHE_DIR, exist_ok=True)
    print("✝  교회 PPT 자동화 도구 시작!")
    print("브라우저에서 http://localhost:5000 을 열어주세요")
    app.run(debug=True, port=5000)
