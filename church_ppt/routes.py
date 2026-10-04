"""HTTP 라우트 (페이지 + /api/*)"""
import io
import json
import os
import tempfile
import traceback

from flask import Blueprint, jsonify, render_template, request, send_file
from pptx import Presentation

from .bible import load_bible_meta, lookup_verses
from .config import load_config, save_config
from .generator import generate_presentation, next_sunday_filename
from .hymns import list_hymns, search_hymn as find_hymn_by_number
from .ppt_convert import convert_ppt_to_pptx

bp = Blueprint("main", __name__)

PPTX_MIMETYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


@bp.route("/")
def index():
    return render_template("index.html")


# ── Config ────────────────────────────────────


@bp.route("/api/config", methods=["GET"])
def get_config():
    print("HIT /api/config")  # 이거 반드시 찍힘
    return jsonify(load_config())


@bp.route("/api/config", methods=["POST"])
def set_config():
    save_config(request.json)
    return jsonify({"ok": True})


# ── Hymns ─────────────────────────────────────


@bp.route("/api/scan-hymns", methods=["POST"])
def scan_hymns():
    folder = request.json.get("folder", "")
    if not folder or not os.path.exists(folder):
        return jsonify({"error": "폴더를 찾을 수 없어요", "hymns": []})
    return jsonify({"hymns": list_hymns(folder)})


@bp.route("/api/search-hymn", methods=["POST"])
def search_hymn():
    folder = request.json.get("folder", "")
    number = request.json.get("number")
    if not folder or not os.path.exists(folder):
        return jsonify({"found": False, "error": "폴더 없음"})
    found = find_hymn_by_number(folder, number)
    if found:
        filename, title = found
        return jsonify({"found": True, "filename": filename, "title": title})
    return jsonify({"found": False})


# ── Template ──────────────────────────────────


@bp.route("/api/template-info", methods=["POST"])
def template_info():
    template_file = request.json.get("template_file", "")
    if not template_file or not os.path.exists(template_file):
        return jsonify({"error": "템플릿 파일을 찾을 수 없어요"})
    try:
        prs = Presentation(template_file)
        slides_info = []
        for i, slide in enumerate(prs.slides):
            texts = [
                s.text_frame.text.strip()[:40]
                for s in slide.shapes
                if s.has_text_frame and s.text_frame.text.strip()
            ]
            slides_info.append(
                {
                    "index": i,
                    "number": i + 1,
                    "preview_text": (
                        " / ".join(texts[:2]) if texts else f"슬라이드 {i+1}"
                    ),
                }
            )
        return jsonify({"slides": slides_info, "total": len(slides_info)})
    except Exception as e:
        return jsonify({"error": str(e)})


# ── Bible ─────────────────────────────────────


@bp.route("/api/bible-meta", methods=["GET"])
def api_bible_meta():
    return jsonify(load_bible_meta())


@bp.route("/api/bible", methods=["POST"])
def api_bible():
    data = request.json or {}
    verse_start = int(data.get("verse_start", 1))
    return jsonify(
        lookup_verses(
            data.get("book_abbr", ""),
            int(data.get("chapter", 1)),
            verse_start,
            int(data.get("verse_end", verse_start)),
        )
    )


# ── Generate ──────────────────────────────────


def _save_uploaded_hymn(upload, tmp_files):
    """업로드된 찬송가를 임시 pptx로 저장 (ppt면 변환). 저장한 경로는 tmp_files에 기록"""
    if not upload:
        return None
    ext = os.path.splitext(upload.filename.lower())[1]
    if ext not in (".ppt", ".pptx"):
        return None
    fd, path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    tmp_files.append(path)
    upload.save(path)
    # ppt면 자동 변환
    if ext == ".ppt":
        path = convert_ppt_to_pptx(path)
        tmp_files.append(path)
    return path


def _resolve_hymn_slots(hymn_slots, tmp_files):
    """upload_key가 있는 슬롯에 업로드 파일의 임시 경로(upload_file)를 채운다"""
    slots = []
    for slot in hymn_slots:
        # 클라이언트가 보낸 경로는 신뢰하지 않음
        slot = {k: v for k, v in slot.items() if k != "upload_file"}
        if slot.get("upload_key") and not slot.get("skip"):
            slot["upload_file"] = _save_uploaded_hymn(
                request.files.get(slot["upload_key"]), tmp_files
            )
        slots.append(slot)
    return slots


@bp.route("/api/generate", methods=["POST"])
def generate():
    upload_tmp_files = []  # 업로드된 찬송가 임시 파일 (요청 종료 시 삭제)
    try:
        if "payload" in request.form:
            data = json.loads(request.form["payload"])
        else:
            data = request.json
        config = load_config()
        template_file = data.get("template_file") or config.get("template_file", "")
        hymn_folder = data.get("hymn_folder") or config.get("hymn_folder", "")

        if not template_file or not os.path.exists(template_file):
            return jsonify({"error": "템플릿 파일을 찾을 수 없어요"})

        data_bytes = generate_presentation(
            template_file,
            hymn_folder,
            _resolve_hymn_slots(data.get("hymn_slots", []), upload_tmp_files),
            data.get("choir", None),
            data.get("scripture", None),
            data.get("extra_verses", []),
        )

        return send_file(
            io.BytesIO(data_bytes),
            mimetype=PPTX_MIMETYPE,
            as_attachment=True,
            download_name=next_sunday_filename(),
        )

    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()})

    finally:
        for p in upload_tmp_files:
            try:
                os.unlink(p)
            except:
                pass
