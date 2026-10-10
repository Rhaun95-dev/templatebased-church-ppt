"""주보 PPT 생성: 템플릿에 찬송가·성가대 가사·성경 구절 슬라이드를 삽입"""
import io
from datetime import date, timedelta

from pptx import Presentation

from .pptx_zip import (
    Package,
    add_black_slide,
    copy_slide,
    count_slides,
    delete_slide,
    duplicate_slide,
    embed_slide_background,
    get_slide_size,
    scale_slide_shapes,
    slide_id_at,
)
from .slide_text import (
    add_chapter_title_text,
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
        n_hymn_slides = count_slides(Package.from_path(hymn_file))
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
#
# 슬라이드 추가/삭제 같은 구조 변경은 메모리의 Package에서 즉시 처리하고,
# 텍스트 채우기는 (슬라이드 sldId, 함수, 인자)로 모아 두었다가 마지막에
# python-pptx로 한 번만 열어 적용한다. sldId는 이후 삽입으로 슬라이드
# 위치가 밀려도 바뀌지 않으므로 인덱스 어긋남이 생기지 않는다.


class _WorkFile:
    """작업 중인 pptx(메모리), 지금까지 늘어난 슬라이드 수(offset), 대기 중인 텍스트 편집"""

    def __init__(self, pkg):
        self.pkg = pkg
        self.offset = 0
        self.edits = []  # [(sld_id, func, args)]

    def edit(self, sld_id, func, *args):
        self.edits.append((sld_id, func, args))


def _apply_choir_title(w, task):
    sid = slide_id_at(w.pkg, task["slide_raw"] + w.offset)
    w.edit(sid, set_slide_choir_title, task["song_title"])


def _apply_choir_lyrics(w, task):
    paragraphs = task["paragraphs"]
    template_idx = task["template_raw"] + w.offset

    w.edit(slide_id_at(w.pkg, template_idx), set_slide_lyrics, paragraphs[0])

    for i, para in enumerate(paragraphs[1:], 1):
        sid = duplicate_slide(w.pkg, template_idx, template_idx + i - 1)
        w.edit(sid, set_slide_lyrics, para)
        w.offset += 1


def _apply_sc_title(w, task):
    sid = slide_id_at(w.pkg, task["slide_raw"] + w.offset)
    w.edit(
        sid,
        set_slide_title_scripture,
        task["book_name"],
        task["chapter"],
        task["verse_start"],
        task["verse_end"],
    )


def _fill_bible_slide(slide, pair, title):
    set_slide_text_bibel(slide, pair)
    add_chapter_title_text(slide, title)


def _apply_sc_verse(w, task):
    pairs = task["pairs"]
    template_idx = task["template_raw"] + w.offset
    title = f"{task['book_name']} {task['chapter']}장"

    w.edit(slide_id_at(w.pkg, template_idx), _fill_bible_slide, pairs[0], title)

    for i, pair in enumerate(pairs[1:], 1):
        sid = duplicate_slide(w.pkg, template_idx, template_idx + i - 1)
        w.edit(sid, _fill_bible_slide, pair, title)
        w.offset += 1


def _apply_ev_block(w, task):
    template_raw = task["template_raw"]

    for ev_i, ev in enumerate(task["ev_list"]):
        ev_verses = ev.get("verses", [])
        ev_book = ev.get("book_name", "")
        ev_ch = str(ev.get("chapter", ""))
        pairs = [ev_verses[j : j + 2] for j in range(0, len(ev_verses), 2)]
        cur_tmpl = template_raw + w.offset  # template 슬라이드 현재 위치
        title = f"{ev_book} {ev_ch}장"

        if ev_i == 0:
            # ev[0]: template 뒤에 pairs 복제 삽입 → template 삭제
            for i, pair in enumerate(pairs):
                sid = duplicate_slide(w.pkg, cur_tmpl, cur_tmpl + i)
                w.edit(sid, _fill_bible_slide, pair, title)

            delete_slide(w.pkg, cur_tmpl)
            w.offset += len(pairs) - 1  # pairs개 추가 - template 1개 삭제

        else:
            # ev[1+]: 검은 슬라이드 삽입 → template으로 pairs 복제 삽입
            # 1) 검은 슬라이드를 cur_tmpl 바로 뒤에 삽입
            add_black_slide(w.pkg, cur_tmpl)
            w.offset += 1

            # 2) 검은 슬라이드 뒤에 pairs 복제 삽입
            insert_base = cur_tmpl + 1  # 검은 슬라이드 현재 위치
            for i, pair in enumerate(pairs):
                sid = duplicate_slide(w.pkg, cur_tmpl, insert_base + i)
                w.edit(sid, _fill_bible_slide, pair, title)

            w.offset += len(pairs)  # 검은 슬라이드 offset은 위에서 이미 반영


def _apply_hymn(w, task):
    actual_after = task["raw_after"] + w.offset
    n_slides = task["n_slides"]

    # 대상(현재 작업 중인) 프레젠테이션의 실제 슬라이드 크기(EMU)
    dst_width, dst_height = get_slide_size(w.pkg)

    # 찬송가 파일은 메모리에서만 수정하므로 원본 임시 파일은 그대로 둔다
    hymn = Package.from_path(task["hymn_file"])

    for i in range(n_slides):
        embed_slide_background(hymn, i)

    # 찬송가 원본의 실제 슬라이드 크기(EMU)가 대상과 다르면(같은 16:9라도
    # 절대 크기가 다를 수 있음) 도형 좌표를 대상 크기 비율로 스케일해서
    # 내용이 작게 붙는 문제를 방지
    for i in range(n_slides):
        scale_slide_shapes(hymn, i, dst_width, dst_height)

    for i in range(n_slides):
        copy_slide(hymn, i, w.pkg, actual_after + i)

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

    w = _WorkFile(Package.from_path(template_file))

    # 정렬된 순서대로 처리, offset 누적
    for task in tasks:
        _HANDLERS[task["type"]](w, task)

    if not w.edits:
        return w.pkg.to_bytes()

    # 텍스트 편집은 python-pptx로 한 번만 열어서 일괄 적용
    prs = Presentation(io.BytesIO(w.pkg.to_bytes(compress=False)))
    slides_by_id = {s.slide_id: s for s in prs.slides}
    for sld_id, func, args in w.edits:
        func(slides_by_id[sld_id], *args)
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()
