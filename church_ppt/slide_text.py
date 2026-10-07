"""슬라이드 텍스트 채우기 (성가대 가사, 성경 구절) 및 슬라이드 삭제"""
import copy
import re

from lxml import etree

from .ooxml import qn

# ── Lyrics helpers ────────────────────────────
def set_slide_choir_title(slide, song_title: str):
    """
    성가대 제목 슬라이드: 가장 큰 텍스트박스의 첫 번째 run 내용만 교체.
    서식(폰트 크기/색상 등)은 유지.
    """
    best_shape, best_size = None, 0
    for shape in slide.shapes:
        if shape.has_text_frame:
            size = shape.width * shape.height
            if size > best_size:
                best_size = size
                best_shape = shape
    if best_shape is None:
        return

    tf = best_shape.text_frame
    txBody = tf._txBody
    paras = txBody.findall(qn("a:p"))

    for para in paras:
        runs = para.findall(qn("a:r"))
        if runs:
            t_el = runs[0].find(qn("a:t"))
            if t_el is None:
                t_el = etree.SubElement(runs[0], qn("a:t"))
            t_el.text = song_title
            for extra_r in runs[1:]:
                para.remove(extra_r)
            break  # 첫 번째 단락만 교체


def split_lyrics_into_paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def set_slide_lyrics(slide, lyrics_text):
    best_shape, best_size = None, 0
    for shape in slide.shapes:
        if shape.has_text_frame:
            size = shape.width * shape.height
            if size > best_size:
                best_size = size
                best_shape = shape
    if best_shape is None:
        return
    tf = best_shape.text_frame
    lines = lyrics_text.split("\n")
    txBody = tf._txBody
    existing_ps = txBody.findall(qn("a:p"))
    template_p = copy.deepcopy(existing_ps[0]) if existing_ps else None
    for p in existing_ps:
        txBody.remove(p)
    for line in lines:
        if template_p is not None:
            new_p = copy.deepcopy(template_p)
            for r in new_p.findall(qn("a:r")):
                new_p.remove(r)
            runs = template_p.findall(qn("a:r"))
            if runs:
                new_r = copy.deepcopy(runs[0])
                t_el = new_r.find(qn("a:t"))
                if t_el is None:
                    t_el = etree.SubElement(new_r, qn("a:t"))
                t_el.text = line
                new_p.append(new_r)
            else:
                new_r = etree.SubElement(new_p, qn("a:r"))
                t_el = etree.SubElement(new_r, qn("a:t"))
                t_el.text = line
        else:
            new_p = etree.Element(qn("a:p"))
            new_r = etree.SubElement(new_p, qn("a:r"))
            t_el = etree.SubElement(new_r, qn("a:t"))
            t_el.text = line
        txBody.append(new_p)


# ── Bible slide helpers ───────────────────────


def set_slide_title_scripture(slide, book_name: str, chapter, verse_start, verse_end):
    """
    성경구절 시작슬라이드: 기존 paragraph/run 구조와 서식(폰트크기 포함)을 그대로 유지,
    텍스트 내용만 교체.
      paragraph 1 (또는 run 1) → 책이름  (예: 요한복음)
      paragraph 2 (또는 run 2) → 장절    (예: 8장 3-9절)
    paragraph가 1개뿐이면 run을 2개로 나눠서 처리.
    """
    best_shape, best_size = None, 0
    for shape in slide.shapes:
        if shape.has_text_frame:
            size = shape.width * shape.height
            if size > best_size:
                best_size = size
                best_shape = shape
    if best_shape is None:
        return

    verse_range = (
        f"{verse_start}-{verse_end}절"
        if str(verse_start) != str(verse_end)
        else f"{verse_start}절"
    )
    chapter_verse_text = f"{chapter}장 {verse_range}"

    tf = best_shape.text_frame
    txBody = tf._txBody
    paras = txBody.findall(qn("a:p"))

    if len(paras) >= 2:
        # paragraph별 첫 run 내용만 교체, 나머지 run 제거 (서식 유지)
        for para, new_text in zip(paras[:2], [book_name, chapter_verse_text]):
            runs = para.findall(qn("a:r"))
            if runs:
                t_el = runs[0].find(qn("a:t"))
                if t_el is None:
                    t_el = etree.SubElement(runs[0], qn("a:t"))
                t_el.text = new_text
                for extra_r in runs[1:]:
                    para.remove(extra_r)
            else:
                new_r = etree.SubElement(para, qn("a:r"))
                t_el = etree.SubElement(new_r, qn("a:t"))
                t_el.text = new_text
    else:
        # paragraph 1개: 기존 run 서식 복제 → run 2개로
        para = paras[0] if paras else etree.SubElement(txBody, qn("a:p"))
        runs = para.findall(qn("a:r"))
        tmpl_run = copy.deepcopy(runs[0]) if runs else None
        for r in runs:
            para.remove(r)
        for new_text in [book_name, chapter_verse_text]:
            new_r = copy.deepcopy(tmpl_run) if tmpl_run else etree.Element(qn("a:r"))
            t_el = new_r.find(qn("a:t"))
            if t_el is None:
                t_el = etree.SubElement(new_r, qn("a:t"))
            t_el.text = new_text
            para.append(new_r)


def set_slide_text_bibel(slide, text_content):

    best_shape, best_size = None, 0
    for shape in slide.shapes:
        if shape.has_text_frame:
            size = shape.width * shape.height
            if size > best_size:
                best_size = size
                best_shape = shape

    if best_shape is None:
        print("성경구절 생성 오류: 택스트 박스를 찾지 못했습니다.")
        return

    tf = best_shape.text_frame
    txBody = tf._txBody
    exist_p = txBody.findall(qn("a:p"))

    # 첫 paragraph run 서식 가져오기
    tmpl_run = None
    if exist_p:
        first_p = exist_p[0]
        runs = first_p.findall(qn("a:r"))
        if runs:
            tmpl_run = copy.deepcopy(runs[0])

    # 기존 paragraph 삭제
    for p in exist_p:
        txBody.remove(p)

    tab_pos = 705000  # 번호 뒤 텍스트 시작 위치
    tab_pos_use = 0
    new_lines = []

    for verse in text_content:
        # 글자 자동 줄바꿈용 글자 크기
        font_size_pt = 18  # 기본값
        if (
            tmpl_run is not None
            and hasattr(tmpl_run, "rPr")
            and hasattr(tmpl_run.rPr, "sz")
        ):
            sz = tmpl_run.rPr.sz
            font_size_pt = sz / 100 if isinstance(sz, int) else sz.pt

        wrapped = estimate_line_breaks(verse["text"], best_shape.width, font_size_pt)

        for i, l in enumerate(wrapped):
            new_lines.append(
                {"num": verse["num"] if i == 0 else None, "text": l}  # 첫 줄만 번호
            )

    for line in new_lines:

        new_p = etree.Element(qn("a:p"))
        pPr = etree.SubElement(new_p, qn("a:pPr"))

        # tab 위치 결정
        tab_pos_use = tab_pos

        # tab 설정
        tabLst = etree.SubElement(pPr, qn("a:tabLst"))
        tab = etree.SubElement(tabLst, qn("a:tab"))
        tab.set("pos", str(tab_pos_use))

        # run 생성 (서식 유지)
        if tmpl_run is not None:
            new_r = copy.deepcopy(tmpl_run)
        else:
            new_r = etree.SubElement(new_p, qn("a:r"))

        t_el = new_r.find(".//" + qn("a:t"))
        if t_el is None:
            t_el = etree.SubElement(new_r, qn("a:t"))

        # 번호 줄 / 번호 없는 줄 텍스트
        if line["num"] is not None:
            t_el.text = f"{line['num']}.\t{line['text']}"
        else:
            t_el.text = f"\t{line['text']}"

        new_p.append(new_r)
        txBody.append(new_p)


# 한 줄에 들어갈 문자 수 계산 (대략)
def estimate_line_breaks(text, box_width_emu, font_size_pt):

    EMU_PER_PT = 12700

    # 텍스트박스 width를 pt로 변환
    box_width_pt = box_width_emu / EMU_PER_PT

    # 한국어 평균 글자폭 (폰트의 약 0.9배)
    char_width_pt = font_size_pt * 0.9

    max_chars = int(box_width_pt / char_width_pt)

    if max_chars <= 1:
        max_chars = 10

    words = text.split()
    lines = []
    current = ""

    for w in words:

        test = (current + " " + w).strip()

        if len(test) <= max_chars:
            current = test
        else:
            lines.append(current)
            current = w

    if current:
        lines.append(current)

    return lines


def add_chapter_title_text(slide, title_text: str):
    """
    슬라이드 안의 가장 작은 텍스트박스를 찾아 내용을 title_text로 교체.
    글자 서식(rPr)은 기존 첫 번째 run에서 deepcopy하여 재사용.
    텍스트박스가 없으면 새로 추가.
    """
    import copy
    from lxml import etree
    from pptx.util import Emu, Pt
    from pptx.dml.color import RGBColor

    ns = "http://schemas.openxmlformats.org/drawingml/2006/main"

    # 가장 작은 텍스트박스 탐색 (초기값 inf → 작은 것 선택)
    small_shape, small_size = None, float("inf")
    for shape in slide.shapes:
        if shape.has_text_frame:
            size = shape.width * shape.height
            if size < small_size:
                small_size = size
                small_shape = shape

    if small_shape is not None:
        tf = small_shape.text_frame

        # 기존 첫 번째 run의 rPr(글자 서식) 복제
        source_rPr = None
        for para in tf.paragraphs:
            for run in para.runs:
                rPr_el = run._r.find(f"{{{ns}}}rPr")
                if rPr_el is not None:
                    source_rPr = copy.deepcopy(rPr_el)
                    break
            if source_rPr is not None:
                break

        # 모든 단락의 런 초기화 (텍스트 지우기)
        for para in tf.paragraphs:
            for r in list(para._p.findall(f"{{{ns}}}r")):
                para._p.remove(r)

        #         # python-pptx 고수준 API로 런 추가 → XML 구조 보장
        para = tf.paragraphs[0]
        run = para.add_run()
        run.text = title_text

        # source_rPr 서식 복제 적용
        if source_rPr is not None:
            run._r.insert(0, source_rPr)


def delete_slide(prs, slide_index):
    xml_slides = prs.slides._sldIdLst
    slide_el = xml_slides[slide_index]
    xml_slides.remove(slide_el)
