"""주보 PPT 생성: 템플릿에 찬송가·성가대 가사·성경 구절 슬라이드를 삽입"""
import os
import shutil
import tempfile
from datetime import date, timedelta

from pptx import Presentation
from pptx.dml.color import RGBColor

from .pptx_zip import (
    copy_slide_from_file_zip,
    duplicate_slide_zip,
    embed_slide_background,
    get_slide_size,
    scale_slide_shapes,
)
from .slide_text import (
    add_chapter_title_text,
    delete_slide,
    set_slide_choir_title,
    set_slide_lyrics,
    set_slide_text_bibel,
    set_slide_title_scripture,
    split_lyrics_into_paragraphs,
)

# ── 설계 원칙 ─────────────────────────────────────────────────
#
# 모든 삽입 작업을 원본 템플릿 기준 raw_after 인덱스로 정렬한 뒤
# 앞에서부터 순서대로 처리하면서 offset을 누적한다.
#
# extra_verses는 모두 동일한 template 슬라이드(ev_in_order[0].slide_index)를
# 공유하므로 ev_block 하나로 묶어서 순방향으로 처리한다:
#   ev[0]  : template 복제 → pairs 삽입 → 원본 삭제
#   ev[1+] : 검은 슬라이드 삽입 → template 복제 → pairs 삽입 (원본 유지)
#
# TYPE_PRIORITY (같은 raw_after일 때 처리 순서):
#   hymn=0 (최우선) → choir_title=1 → choir_lyrics=2
#   → sc_title=3 → sc_verse=4 → ev_block=5

TYPE_PRIORITY = {
    "hymn": 0,
    "choir_title": 1,
    "choir_lyrics": 2,
    "sc_title": 3,
    "sc_verse": 4,
    "ev_block": 5,
}


def next_sunday_filename():
    today = date.today()
    days_until_sunday = 6 - today.weekday()  # 일요일(6)까지 남은 날 수
    if days_until_sunday < 0:
        days_until_sunday += 7
    sunday = today + timedelta(days=days_until_sunday)
    return sunday.strftime("%d.%m.%Y") + ".pptx"


# ── 작업 목록 생성 ────────────────────────────


def build_tasks(hymn_slots, choir, scripture, extra_verses):
    """요청 데이터를 원본 템플릿 기준 삽입 작업 목록으로 변환 (정렬됨).

    hymn_slots의 각 슬롯은 업로드 파일의 임시 경로 "upload_file"을 가진다.
    "upload_file"이 없거나 비어 있으면 해당 슬롯은 건너뛴다.
    """
    tasks = []

    # ── choir ────────────────────────────────────────────────────
    if choir and not choir.get("skip"):
        title_idx = choir.get("title_slide_index")
        lyrics_idx = choir.get("lyrics_slide_index")
        song_title = choir.get("song_title", "").strip()
        lyrics_text = choir.get("lyrics", "").strip()

        if song_title and title_idx is not None:
            tasks.append(
                {
                    "type": "choir_title",
                    "raw_after": title_idx - 1,
                    "song_title": song_title,
                    "slide_raw": title_idx,
                }
            )

        if lyrics_text and lyrics_idx is not None:
            paragraphs = split_lyrics_into_paragraphs(lyrics_text)
            if paragraphs:
                tasks.append(
                    {
                        "type": "choir_lyrics",
                        "raw_after": lyrics_idx - 1,
                        "paragraphs": paragraphs,
                        "template_raw": lyrics_idx,
                    }
                )

    # ── scripture ────────────────────────────────────────────────
    if scripture and not scripture.get("skip"):
        sc_title_idx = scripture.get("title_slide_index")
        sc_verse_idx = (sc_title_idx + 1) if sc_title_idx is not None else None
        verses = scripture.get("verses", [])
        book_name = scripture.get("book_name", "")
        chapter = scripture.get("chapter", "")
        verse_start = scripture.get("verse_start", "")
        verse_end = scripture.get("verse_end", "")

        if sc_title_idx is not None and book_name:
            tasks.append(
                {
                    "type": "sc_title",
                    "raw_after": sc_title_idx - 1,
                    "book_name": book_name,
                    "chapter": chapter,
                    "verse_start": verse_start,
                    "verse_end": verse_end,
                    "slide_raw": sc_title_idx,
                }
            )

        if verses and sc_verse_idx is not None:
            pairs = [verses[i : i + 2] for i in range(0, len(verses), 2)]
            tasks.append(
                {
                    "type": "sc_verse",
                    "raw_after": sc_verse_idx - 1,
                    "pairs": pairs,
                    "book_name": book_name,
                    "chapter": chapter,
                    "template_raw": sc_verse_idx,
                }
            )

    # ── extra_verses (ev_block으로 묶어서 처리) ──────────────────
    ev_in_order = sorted(
        [
            ev
            for ev in extra_verses
            if ev.get("slide_index") is not None and ev.get("verses")
        ],
        key=lambda x: x["slide_index"],
    )

    if ev_in_order:
        # 모든 ev는 첫번째 ev의 slide_index를 template으로 공유
        ev_template_raw = ev_in_order[0]["slide_index"]
        tasks.append(
            {
                "type": "ev_block",
                "raw_after": ev_template_raw - 1,
                "template_raw": ev_template_raw,
                "ev_list": ev_in_order,
            }
        )

    # ── hymns ─────────────────────────────────────────────────────
    for slot in hymn_slots:
        if slot.get("skip"):
            continue
        hymn_file = slot.get("upload_file")
        if not hymn_file:
            continue
        hymn_prs_tmp = Presentation(hymn_file)
        n_hymn_slides = len(hymn_prs_tmp.slides)
        del hymn_prs_tmp
        tasks.append(
            {
                "type": "hymn",
                "raw_after": slot.get("after_slide_index", 0),
                "hymn_file": hymn_file,
                "n_slides": n_hymn_slides,
            }
        )

    tasks.sort(key=lambda t: (t["raw_after"], TYPE_PRIORITY.get(t["type"], 9)))
    return tasks


# ── 작업 실행 ─────────────────────────────────


class _WorkFile:
    """작업 중인 pptx 경로와 지금까지 늘어난 슬라이드 수(offset)"""

    def __init__(self, path):
        self.path = path
        self.offset = 0


def _apply_choir_title(w, task):
    prs = Presentation(w.path)
    set_slide_choir_title(
        prs.slides[task["slide_raw"] + w.offset],
        task["song_title"],
    )
    prs.save(w.path)


def _apply_choir_lyrics(w, task):
    paragraphs = task["paragraphs"]
    template_idx = task["template_raw"] + w.offset

    prs = Presentation(w.path)
    set_slide_lyrics(prs.slides[template_idx], paragraphs[0])
    prs.save(w.path)

    for i, para in enumerate(paragraphs[1:], 1):
        ins = template_idx + i - 1
        new_path = duplicate_slide_zip(w.path, template_idx, ins)
        os.unlink(w.path)
        w.path = new_path
        prs = Presentation(w.path)
        set_slide_lyrics(prs.slides[ins + 1], para)
        prs.save(w.path)
        w.offset += 1


def _apply_sc_title(w, task):
    prs = Presentation(w.path)
    set_slide_title_scripture(
        prs.slides[task["slide_raw"] + w.offset],
        task["book_name"],
        task["chapter"],
        task["verse_start"],
        task["verse_end"],
    )
    prs.save(w.path)


def _apply_sc_verse(w, task):
    pairs = task["pairs"]
    template_idx = task["template_raw"] + w.offset

    prs = Presentation(w.path)
    sl = prs.slides[template_idx]
    set_slide_text_bibel(sl, pairs[0])
    add_chapter_title_text(sl, f"{task['book_name']} {task['chapter']}장")
    prs.save(w.path)

    for i, pair in enumerate(pairs[1:], 1):
        ins = template_idx + i - 1
        new_path = duplicate_slide_zip(w.path, template_idx, ins)
        os.unlink(w.path)
        w.path = new_path
        prs = Presentation(w.path)
        sl = prs.slides[ins + 1]
        set_slide_text_bibel(sl, pair)
        add_chapter_title_text(
            sl, f"{task['book_name']} {task['chapter']}장"
        )
        prs.save(w.path)
        w.offset += 1


def _apply_ev_block(w, task):
    template_raw = task["template_raw"]

    for ev_i, ev in enumerate(task["ev_list"]):
        ev_verses = ev.get("verses", [])
        ev_book = ev.get("book_name", "")
        ev_ch = str(ev.get("chapter", ""))
        pairs = [ev_verses[j : j + 2] for j in range(0, len(ev_verses), 2)]
        cur_tmpl = template_raw + w.offset  # template 슬라이드 현재 위치

        if ev_i == 0:
            # ev[0]: template 뒤에 pairs 복제 삽입 → template 삭제
            for i, pair in enumerate(pairs):
                new_path = duplicate_slide_zip(
                    w.path, cur_tmpl, cur_tmpl + i
                )
                os.unlink(w.path)
                w.path = new_path
                prs = Presentation(w.path)
                sl = prs.slides[cur_tmpl + i + 1]
                set_slide_text_bibel(sl, pair)
                add_chapter_title_text(sl, f"{ev_book} {ev_ch}장")
                prs.save(w.path)

            prs = Presentation(w.path)
            delete_slide(prs, cur_tmpl)
            prs.save(w.path)
            w.offset += len(pairs) - 1  # pairs개 추가 - template 1개 삭제

        else:
            # ev[1+]: 검은 슬라이드 삽입 → template으로 pairs 복제 삽입
            # 1) 검은 슬라이드를 cur_tmpl 바로 뒤에 삽입
            prs = Presentation(w.path)
            blank_layout = prs.slide_layouts[6]
            new_slide = prs.slides.add_slide(blank_layout)
            new_slide.background.fill.solid()
            new_slide.background.fill.fore_color.rgb = RGBColor(0, 0, 0)
            xml_slides = prs.slides._sldIdLst
            last = xml_slides[-1]
            xml_slides.remove(last)
            xml_slides.insert(cur_tmpl + 1, last)
            prs.save(w.path)
            w.offset += 1

            # 2) 검은 슬라이드 뒤에 pairs 복제 삽입
            insert_base = cur_tmpl + 1  # 검은 슬라이드 현재 위치
            for i, pair in enumerate(pairs):
                new_path = duplicate_slide_zip(
                    w.path, cur_tmpl, insert_base + i
                )
                os.unlink(w.path)
                w.path = new_path
                prs = Presentation(w.path)
                sl = prs.slides[insert_base + i + 1]
                set_slide_text_bibel(sl, pair)
                add_chapter_title_text(sl, f"{ev_book} {ev_ch}장")
                prs.save(w.path)

            w.offset += len(pairs)  # 검은 슬라이드 offset은 위에서 이미 반영


def _apply_hymn(w, task):
    actual_after = task["raw_after"] + w.offset
    hymn_file = task["hymn_file"]
    n_slides = task["n_slides"]

    # 대상(현재 작업 중인) 프레젠테이션의 실제 슬라이드 크기(EMU)
    dst_width, dst_height = get_slide_size(w.path)

    hymn_fd, hymn_tmp = tempfile.mkstemp(suffix=".pptx")
    os.close(hymn_fd)
    shutil.copy2(hymn_file, hymn_tmp)

    for i in range(n_slides):
        new_tmp = embed_slide_background(hymn_tmp, i)
        if new_tmp:
            os.unlink(hymn_tmp)
            hymn_tmp = new_tmp

    # 찬송가 원본의 실제 슬라이드 크기(EMU)가 대상과 다르면(같은 16:9라도
    # 절대 크기가 다를 수 있음) 도형 좌표를 대상 크기 비율로 스케일해서
    # 내용이 작게 붙는 문제를 방지
    for i in range(n_slides):
        new_tmp = scale_slide_shapes(hymn_tmp, i, dst_width, dst_height)
        if new_tmp:
            os.unlink(hymn_tmp)
            hymn_tmp = new_tmp

    for i in range(n_slides):
        new_path = copy_slide_from_file_zip(
            hymn_tmp, i, w.path, actual_after + i
        )
        os.unlink(w.path)
        w.path = new_path

    os.unlink(hymn_tmp)
    w.offset += n_slides


_HANDLERS = {
    "choir_title": _apply_choir_title,
    "choir_lyrics": _apply_choir_lyrics,
    "sc_title": _apply_sc_title,
    "sc_verse": _apply_sc_verse,
    "ev_block": _apply_ev_block,
    "hymn": _apply_hymn,
}


def generate_presentation(template_file, hymn_slots, choir, scripture, extra_verses):
    """템플릿 복사본에 모든 작업을 적용하고 결과 pptx 바이트를 반환"""
    tasks = build_tasks(hymn_slots, choir, scripture, extra_verses)

    work_fd, work_path = tempfile.mkstemp(suffix=".pptx")
    os.close(work_fd)
    shutil.copy2(template_file, work_path)
    w = _WorkFile(work_path)
    try:
        # 정렬된 순서대로 처리, offset 누적
        for task in tasks:
            _HANDLERS[task["type"]](w, task)
        with open(w.path, "rb") as f:
            return f.read()
    finally:
        if w.path and os.path.exists(w.path):
            try:
                os.unlink(w.path)
            except:
                pass
