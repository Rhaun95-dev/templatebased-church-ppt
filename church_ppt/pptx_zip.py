"""ZIP/XML 레벨 슬라이드 복사·복제·배경/크기 처리

pptx를 메모리(`Package`)에 한 번만 올려 두고 파트 단위로 수정한다.
슬라이드를 하나 넣을 때마다 파일 전체를 다시 압축해 쓰던 방식은 느려서,
최종 결과를 내보낼 때(`Package.to_bytes`) 한 번만 zip으로 쓴다.
"""
import copy
import io
import os
import re
import zipfile

from lxml import etree

from .ooxml import NSMAP, qn

# 이미 압축된 형식은 다시 deflate 하지 않는다 (시간만 쓰고 크기는 그대로)
_STORED_EXTS = {"png", "jpg", "jpeg", "gif", "mp4", "mp3", "m4a", "mov", "wmv", "webp"}

_SLIDE_CT = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
_REL_SLIDE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
_REL_LAYOUT = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
)

EXT_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "svg": "image/svg+xml",
    "wmf": "image/x-wmf",
    "emf": "image/x-emf",
    "mp4": "video/mp4",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
}


class Package:
    """메모리에 올린 pptx. 파트 이름 → 바이트 (zipfile.ZipFile과 같은 읽기 인터페이스)"""

    def __init__(self, files):
        self.files = files

    @classmethod
    def from_path(cls, path):
        with zipfile.ZipFile(path, "r") as zf:
            return cls({name: zf.read(name) for name in zf.namelist()})

    @classmethod
    def from_bytes(cls, data):
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            return cls({name: zf.read(name) for name in zf.namelist()})

    # zipfile.ZipFile 호환 (아래 XML 헬퍼들이 공유)
    def namelist(self):
        return self.files.keys()

    def read(self, name):
        return self.files[name]

    def open(self, name):
        return io.BytesIO(self.files[name])

    def to_bytes(self, compress=True):
        """zip으로 직렬화. compress=False면 압축 없이 빠르게 (중간 산출물용)"""
        buf = io.BytesIO()
        base = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
        with zipfile.ZipFile(buf, "w", base, compresslevel=1) as zf:
            for name, data in self.files.items():
                ext = os.path.splitext(name)[1].lower().lstrip(".")
                kind = zipfile.ZIP_STORED if ext in _STORED_EXTS else base
                zf.writestr(name, data, compress_type=kind)
        return buf.getvalue()


def _read_xml(zf, path):
    with zf.open(path) as f:
        return etree.parse(f).getroot()


def _xml_bytes(root):
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _slide_paths_ordered(zf):
    prs_xml = _read_xml(zf, "ppt/presentation.xml")
    prs_rels = _read_xml(zf, "ppt/_rels/presentation.xml.rels")
    rid_to_t = {r.get("Id"): r.get("Target", "") for r in prs_rels}
    paths = []
    sldIdLst = prs_xml.find(qn("p:sldIdLst"))
    if sldIdLst is None:
        return paths
    for sldId in sldIdLst:
        t = rid_to_t.get(sldId.get(qn("r:id")), "")
        if t:
            paths.append("ppt/" + t.lstrip("./"))
    return paths


def _rels_path(slide_path):
    parts = slide_path.rsplit("/", 1)
    return parts[0] + "/_rels/" + parts[1] + ".rels"


def _max_slide_num(zf):
    nums = [
        int(m.group(1))
        for n in zf.namelist()
        for m in [re.match(r"ppt/slides/slide(\d+)\.xml$", n)]
        if m
    ]
    return max(nums) if nums else 0


def _max_rid(rels_root):
    ids = [
        int(m.group(1))
        for r in rels_root
        for m in [re.match(r"rId(\d+)", r.get("Id", ""))]
        if m
    ]
    return max(ids) + 1 if ids else 1


def _max_sld_id(prs_xml):
    sldIdLst = prs_xml.find(qn("p:sldIdLst"))
    ids = [
        int(el.get("id", 255))
        for el in (list(sldIdLst) if sldIdLst is not None else [])
    ]
    return max(ids) + 1 if ids else 256


# ── 크기 / 슬라이드 정보 ───────────────────────


def _get_zip_slide_size(zf):
    """presentation.xml의 sldSz(width, height) EMU 값을 읽는다."""
    prs_xml = _read_xml(zf, "ppt/presentation.xml")
    sldSz = prs_xml.find(qn("p:sldSz"))
    if sldSz is None:
        return None, None
    return int(sldSz.get("cx")), int(sldSz.get("cy"))


def get_slide_size(pkg):
    return _get_zip_slide_size(pkg)


def count_slides(pkg):
    return len(_slide_paths_ordered(pkg))


def slide_id_at(pkg, index):
    """현재 index번째 슬라이드의 고유 sldId (이후 삽입으로 위치가 바뀌어도 유지됨)"""
    prs_xml = _read_xml(pkg, "ppt/presentation.xml")
    return int(prs_xml.find(qn("p:sldIdLst"))[index].get("id"))


def delete_slide(pkg, index):
    """슬라이드를 목록과 패키지에서 완전히 제거한다.

    목록에서만 빼 두면 고아 슬라이드 파트가 남아, python-pptx가 저장할 때
    슬라이드 파일 이름을 다시 매기다가 같은 이름의 항목이 중복될 수 있다.
    """
    prs_xml = _read_xml(pkg, "ppt/presentation.xml")
    prs_rels = _read_xml(pkg, "ppt/_rels/presentation.xml.rels")
    ct_xml = _read_xml(pkg, "[Content_Types].xml")

    sldIdLst = prs_xml.find(qn("p:sldIdLst"))
    sld_id = sldIdLst[index]
    rid = sld_id.get(qn("r:id"))
    sldIdLst.remove(sld_id)

    for rel in list(prs_rels):
        if rel.get("Id") == rid:
            slide_path = "ppt/" + rel.get("Target", "").lstrip("./")
            prs_rels.remove(rel)
            pkg.files.pop(slide_path, None)
            pkg.files.pop(_rels_path(slide_path), None)
            for ov in ct_xml.findall(qn("ct:Override")):
                if ov.get("PartName") == "/" + slide_path:
                    ct_xml.remove(ov)
            break

    pkg.files["ppt/presentation.xml"] = _xml_bytes(prs_xml)
    pkg.files["ppt/_rels/presentation.xml.rels"] = _xml_bytes(prs_rels)
    pkg.files["[Content_Types].xml"] = _xml_bytes(ct_xml)


# ── 슬라이드 등록 (공통) ──────────────────────


def _register_slide(pkg, prs_xml, prs_rels, ct_xml, slide_bytes, rels_root, insert_after):
    """새 슬라이드 파트를 패키지에 추가하고 순서 목록의 insert_after 뒤에 넣는다. 새 sldId 반환."""
    new_num = _max_slide_num(pkg) + 1
    new_slide_path = f"ppt/slides/slide{new_num}.xml"
    new_rels_path = f"ppt/slides/_rels/slide{new_num}.xml.rels"
    new_rid = f"rId{_max_rid(prs_rels)}"
    new_sld_id = _max_sld_id(prs_xml)

    part_name = "/" + new_slide_path
    ct_overrides = {el.get("PartName", "") for el in ct_xml.findall(qn("ct:Override"))}
    if part_name not in ct_overrides:
        ov = etree.SubElement(ct_xml, qn("ct:Override"))
        ov.set("PartName", part_name)
        ov.set("ContentType", _SLIDE_CT)

    pr_rel = etree.SubElement(prs_rels, qn("pr:Relationship"))
    pr_rel.set("Id", new_rid)
    pr_rel.set("Type", _REL_SLIDE)
    pr_rel.set("Target", f"slides/slide{new_num}.xml")

    sldIdLst = prs_xml.find(qn("p:sldIdLst"))
    new_el = etree.Element(qn("p:sldId"))
    new_el.set("id", str(new_sld_id))
    new_el.set(qn("r:id"), new_rid)
    pos = min(insert_after + 1, len(sldIdLst))
    sldIdLst.insert(pos, new_el)

    pkg.files[new_slide_path] = slide_bytes
    pkg.files[new_rels_path] = _xml_bytes(rels_root)
    pkg.files["ppt/presentation.xml"] = _xml_bytes(prs_xml)
    pkg.files["ppt/_rels/presentation.xml.rels"] = _xml_bytes(prs_rels)
    pkg.files["[Content_Types].xml"] = _xml_bytes(ct_xml)
    return new_sld_id


# ── 슬라이드 복사 / 복제 ──────────────────────


def copy_slide(src, src_slide_index, dst, insert_after):
    """src 패키지의 슬라이드를 dst 패키지의 insert_after 뒤로 복사한다 (dst를 직접 수정).

    같은 패키지 안의 복제(src is dst)는 이미지 등 미디어를 다시 복사하지 않고
    기존 파트를 그대로 참조한다. 새 슬라이드의 sldId를 반환.
    """
    src_slide_paths = _slide_paths_ordered(src)
    if src_slide_index >= len(src_slide_paths):
        raise ValueError(f"Slide index {src_slide_index} out of range")
    src_slide_path = src_slide_paths[src_slide_index]
    src_rels_path = _rels_path(src_slide_path)
    same_package = src is dst

    prs_xml = _read_xml(dst, "ppt/presentation.xml")
    prs_rels = _read_xml(dst, "ppt/_rels/presentation.xml.rels")
    ct_xml = _read_xml(dst, "[Content_Types].xml")

    src_rels_root = etree.Element("{%s}Relationships" % NSMAP["pr"])
    if src_rels_path in src.files:
        src_rels_root = _read_xml(src, src_rels_path)

    ct_defaults = {
        el.get("Extension", "").lower() for el in ct_xml.findall(qn("ct:Default"))
    }

    new_rels_root = etree.Element("{%s}Relationships" % NSMAP["pr"])
    extra_files = {}

    for rel in src_rels_root:
        rid = rel.get("Id", "")
        rel_type = rel.get("Type", "")
        target = rel.get("Target", "")
        tmode = rel.get("TargetMode", "")

        new_rel = etree.SubElement(new_rels_root, qn("pr:Relationship"))
        new_rel.set("Id", rid)
        new_rel.set("Type", rel_type)

        if tmode == "External":
            new_rel.set("Target", target)
            new_rel.set("TargetMode", "External")
            continue

        if target.startswith("../"):
            src_full = "ppt/" + target[3:]
        else:
            src_full = "ppt/slides/" + target

        if "slideLayout" in target or "slideMaster" in target:
            new_rel.set("Target", target)
            continue

        if src_full not in src.files:
            new_rel.set("Target", target)
            continue

        # 같은 파일 안에서의 복제: 이미지/미디어는 같은 파트를 공유
        if same_package and src_full.startswith("ppt/media/"):
            new_rel.set("Target", target)
            continue

        ext = os.path.splitext(src_full)[1].lower().lstrip(".")

        dst_target = src_full
        counter = 2
        while dst_target in dst.files or dst_target in extra_files:
            base, dot_ext = os.path.splitext(src_full)
            dst_target = f"{base}_{counter}{dot_ext}"
            counter += 1

        extra_files[dst_target] = src.files[src_full]

        if ext and ext not in ct_defaults:
            nd = etree.SubElement(ct_xml, qn("ct:Default"))
            nd.set("Extension", ext)
            nd.set("ContentType", EXT_MIME.get(ext, "application/octet-stream"))
            ct_defaults.add(ext)

        new_rel.set("Target", "../" + dst_target[4:])

    slide_bytes = src.files[src_slide_path]
    for name, data in extra_files.items():
        dst.files[name] = data

    return _register_slide(
        dst, prs_xml, prs_rels, ct_xml, slide_bytes, new_rels_root, insert_after
    )


def duplicate_slide(pkg, slide_index, insert_after):
    return copy_slide(pkg, slide_index, pkg, insert_after)


_BLACK_SLIDE_XML = (
    '<p:sld xmlns:a="%(a)s" xmlns:r="%(r)s" xmlns:p="%(p)s">'
    "<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val=\"000000\"/></a:solidFill>"
    "<a:effectLst/></p:bgPr></p:bg>"
    '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
    "</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/>"
    '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree>'
    "</p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
) % {"a": NSMAP["a"], "r": NSMAP["r"], "p": NSMAP["p"]}


def _blank_layout_target(pkg, prs_xml, prs_rels):
    """첫 슬라이드 마스터의 7번째(없으면 마지막) 레이아웃 경로 (slides/ 기준 상대 경로 포함)"""
    rid_to_t = {r.get("Id"): r.get("Target", "") for r in prs_rels}
    master_rid = prs_xml.find(qn("p:sldMasterIdLst"))[0].get(qn("r:id"))
    master_path = "ppt/" + rid_to_t[master_rid].lstrip("./")
    master_xml = _read_xml(pkg, master_path)
    layout_ids = master_xml.find(qn("p:sldLayoutIdLst"))
    layout_rid = layout_ids[min(6, len(layout_ids) - 1)].get(qn("r:id"))
    master_rels = _read_xml(pkg, _rels_path(master_path))
    for rel in master_rels:
        if rel.get("Id") == layout_rid:
            return rel.get("Target", "")  # 예: ../slideLayouts/slideLayout7.xml
    raise ValueError("빈 레이아웃을 찾지 못했습니다")


def add_black_slide(pkg, insert_after):
    """검은 배경의 빈 슬라이드를 insert_after 뒤에 추가. 새 sldId 반환."""
    prs_xml = _read_xml(pkg, "ppt/presentation.xml")
    prs_rels = _read_xml(pkg, "ppt/_rels/presentation.xml.rels")
    ct_xml = _read_xml(pkg, "[Content_Types].xml")

    rels_root = etree.Element("{%s}Relationships" % NSMAP["pr"])
    rel = etree.SubElement(rels_root, qn("pr:Relationship"))
    rel.set("Id", "rId1")
    rel.set("Type", _REL_LAYOUT)
    rel.set("Target", _blank_layout_target(pkg, prs_xml, prs_rels))

    slide_bytes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                   + _BLACK_SLIDE_XML).encode("utf-8")
    return _register_slide(
        pkg, prs_xml, prs_rels, ct_xml, slide_bytes, rels_root, insert_after
    )


# ── 찬송가 슬라이드 전처리 (배경 삽입 / 크기 스케일) ─────


def scale_slide_shapes(pkg, slide_index, dst_width, dst_height):
    """
    pkg의 slide_index 슬라이드 도형들을, 원본 자신의 슬라이드 크기(sldSz) 기준에서
    대상(dst_width, dst_height) 크기 기준으로 비율에 맞게 스케일한다 (pkg를 직접 수정).
    원본과 대상 크기가 (거의) 같으면 스케일할 필요가 없으므로 False를 반환한다.

    ZIP-레벨 raw XML 복사이기 때문에, 같은 16:9 비율이어도 원본과 대상의 절대 크기(EMU)가
    다르면 도형이 원래 크기 그대로 붙어 작게 보이는 문제가 생긴다 — 이를 방지하기 위한 함수.
    그룹 도형은 최상위 xfrm(off/ext)만 스케일하면 내부 좌표(chOff/chExt)는 비율이 자동 유지된다.
    """
    ns_p = NSMAP["p"]
    ns_a = NSMAP["a"]

    src_width, src_height = _get_zip_slide_size(pkg)
    if not src_width or not src_height or not dst_width or not dst_height:
        return False
    if abs(src_width - dst_width) < 1000 and abs(src_height - dst_height) < 1000:
        return False  # 이미 거의 동일한 크기 → 스케일 불필요

    scale_x = dst_width / src_width
    scale_y = dst_height / src_height

    slide_paths = _slide_paths_ordered(pkg)
    if slide_index >= len(slide_paths):
        return False
    slide_path = slide_paths[slide_index]
    slide_xml = _read_xml(pkg, slide_path)

    cSld = slide_xml.find(f"{{{ns_p}}}cSld")
    spTree = cSld.find(f"{{{ns_p}}}spTree") if cSld is not None else None
    if spTree is None:
        return False

    def scale_xfrm(xfrm):
        off = xfrm.find(f"{{{ns_a}}}off")
        ext = xfrm.find(f"{{{ns_a}}}ext")
        if off is not None:
            off.set("x", str(round(int(off.get("x", 0)) * scale_x)))
            off.set("y", str(round(int(off.get("y", 0)) * scale_y)))
        if ext is not None:
            ext.set("cx", str(round(int(ext.get("cx", 0)) * scale_x)))
            ext.set("cy", str(round(int(ext.get("cy", 0)) * scale_y)))

    # 최상위 도형들만 스케일 (그룹 내부 좌표는 그룹 자체 xfrm 스케일로 자동 유지됨)
    for child in spTree:
        tag = etree.QName(child).localname
        if tag in ("sp", "pic", "cxnSp", "grpSp"):
            spPr = child.find(f"{{{ns_p}}}spPr")
            if spPr is None:
                spPr = child.find(f"{{{ns_p}}}grpSpPr")
            if spPr is None:
                continue
            xfrm = spPr.find(f"{{{ns_a}}}xfrm")
            if xfrm is not None:
                scale_xfrm(xfrm)
        elif tag == "graphicFrame":
            xfrm = child.find(f"{{{ns_p}}}xfrm")
            if xfrm is not None:
                scale_xfrm(xfrm)

    pkg.files[slide_path] = _xml_bytes(slide_xml)
    return True


def embed_slide_background(pkg, slide_index):
    """
    슬라이드에 p:bg가 없으면 slideLayout → slideMaster 순으로 배경을 찾아
    슬라이드 XML에 직접 삽입한다 (pkg를 직접 수정).
    배경이 이미 있거나 찾지 못하면 False 반환.
    """
    ns_p = NSMAP["p"]
    ns_a = NSMAP["a"]
    ns_r = NSMAP["r"]
    pr_ns = NSMAP["pr"]

    slide_paths = _slide_paths_ordered(pkg)
    if slide_index >= len(slide_paths):
        return False
    slide_path = slide_paths[slide_index]
    slide_xml = _read_xml(pkg, slide_path)

    cSld = slide_xml.find(f"{{{ns_p}}}cSld")
    if cSld is None:
        return False

    # 슬라이드 자체에 이미 배경 있으면 불필요
    if cSld.find(f"{{{ns_p}}}bg") is not None:
        return False

    # slide rels → slideLayout 경로
    slide_rels_path = _rels_path(slide_path)
    layout_path = None
    if slide_rels_path in pkg.files:
        srels = _read_xml(pkg, slide_rels_path)
        for rel in srels:
            if "slideLayout" in rel.get("Type", ""):
                t = rel.get("Target", "")
                layout_path = (
                    ("ppt/" + t[3:]) if t.startswith("../") else ("ppt/slides/" + t)
                )
                break
    if not layout_path or layout_path not in pkg.files:
        return False

    # layout에서 p:bg 탐색
    layout_xml = _read_xml(pkg, layout_path)
    layout_cSld = layout_xml.find(f"{{{ns_p}}}cSld")
    bg_el = layout_cSld.find(f"{{{ns_p}}}bg") if layout_cSld is not None else None
    bg_rels_path = _rels_path(layout_path)  # 이미지 rid 기준 rels

    # layout에 없으면 slideMaster 탐색
    if bg_el is None:
        master_path = None
        if bg_rels_path in pkg.files:
            lrels = _read_xml(pkg, bg_rels_path)
            for rel in lrels:
                if "slideMaster" in rel.get("Type", ""):
                    t = rel.get("Target", "")
                    master_path = (
                        ("ppt/" + t[3:])
                        if t.startswith("../")
                        else ("ppt/slideLayouts/" + t)
                    )
                    break
        if not master_path or master_path not in pkg.files:
            return False
        master_xml = _read_xml(pkg, master_path)
        master_cSld = master_xml.find(f"{{{ns_p}}}cSld")
        bg_el = master_cSld.find(f"{{{ns_p}}}bg") if master_cSld is not None else None
        bg_rels_path = _rels_path(master_path)  # 이미지 rid는 master rels 기준

    if bg_el is None:
        return False

    bg_copy = copy.deepcopy(bg_el)

    # 배경 안 blip의 r:embed rid → 슬라이드 rels에 이미지 등록
    blips = bg_copy.findall(f".//{{{ns_a}}}blip")
    new_rels_to_add = []  # (new_rid, img_path, img_bytes)
    rid_remap = {}

    srels_xml = (
        _read_xml(pkg, slide_rels_path)
        if slide_rels_path in pkg.files
        else etree.Element(f"{{{pr_ns}}}Relationships")
    )

    if blips and bg_rels_path in pkg.files:
        bg_rels_xml = _read_xml(pkg, bg_rels_path)
        rid_to_target = {r.get("Id", ""): r.get("Target", "") for r in bg_rels_xml}

        # 슬라이드 기존 rels에서 최대 rid 번호 추출
        max_rid_num = max(
            (
                int(m.group(1))
                for r in srels_xml
                for m in [re.match(r"rId(\d+)", r.get("Id", ""))]
                if m
            ),
            default=0,
        )

        for blip in blips:
            old_rid = blip.get(f"{{{ns_r}}}embed", "")
            if not old_rid or old_rid in rid_remap:
                continue
            img_rel_target = rid_to_target.get(old_rid, "")
            if not img_rel_target:
                continue

            # 이미지 실제 경로 (bg_rels_path 기준)
            base_dir = bg_rels_path.replace("/_rels/", "/").rsplit("/", 1)[0]
            if img_rel_target.startswith("../"):
                img_path = "ppt/" + img_rel_target[3:]
            else:
                img_path = base_dir + "/" + img_rel_target

            if img_path not in pkg.files:
                continue

            max_rid_num += 1
            new_rid = f"rId{max_rid_num}"
            rid_remap[old_rid] = new_rid
            new_rels_to_add.append((new_rid, img_path, pkg.files[img_path]))

        for blip in blips:
            old_rid = blip.get(f"{{{ns_r}}}embed", "")
            if old_rid in rid_remap:
                blip.set(f"{{{ns_r}}}embed", rid_remap[old_rid])

    # 슬라이드 rels에 이미지 rid 추가
    for new_rid, img_path, _ in new_rels_to_add:
        new_rel = etree.SubElement(srels_xml, f"{{{pr_ns}}}Relationship")
        new_rel.set("Id", new_rid)
        new_rel.set("Type", f"{ns_r}/image")
        new_rel.set("Target", f"../media/{img_path.split('/')[-1]}")

    # 슬라이드 XML에 bg_copy 삽입 (cSld 첫 번째 자식)
    cSld.insert(0, bg_copy)

    pkg.files[slide_path] = _xml_bytes(slide_xml)
    if slide_rels_path in pkg.files or new_rels_to_add:
        pkg.files[slide_rels_path] = _xml_bytes(srels_xml)

    # 새 이미지 파일 추가
    for _, img_path, img_bytes in new_rels_to_add:
        dst = f"ppt/media/{img_path.split('/')[-1]}"
        if dst not in pkg.files:
            pkg.files[dst] = img_bytes

    return True
