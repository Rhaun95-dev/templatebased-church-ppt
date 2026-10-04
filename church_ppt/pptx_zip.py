"""ZIP/XML 레벨 슬라이드 복사·복제·배경/크기 처리"""
import copy
import os
import re
import tempfile
import zipfile

from lxml import etree
from pptx import Presentation

from .ooxml import NSMAP, qn

# ── Core ZIP-level slide copy ─────────────────


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
def get_slide_size(pptx_path):
    prs = Presentation(pptx_path)
    return prs.slide_width, prs.slide_height


def _get_zip_slide_size(zf):
    """열려 있는 zip 파일 객체에서 presentation.xml의 sldSz(width, height) EMU 값을 읽는다."""
    prs_xml = _read_xml(zf, "ppt/presentation.xml")
    sldSz = prs_xml.find(qn("p:sldSz"))
    if sldSz is None:
        return None, None
    return int(sldSz.get("cx")), int(sldSz.get("cy"))


def scale_slide_shapes(src_path: str, slide_index: int, dst_width, dst_height):
    """
    src_path pptx의 slide_index 슬라이드 도형들을, 원본 자신의 슬라이드 크기(sldSz) 기준에서
    대상(dst_width, dst_height) 크기 기준으로 비율에 맞게 스케일한 새 임시파일 경로를 반환.
    원본과 대상 크기가 (거의) 같으면 스케일할 필요가 없으므로 None을 반환한다.

    ZIP-레벨 raw XML 복사이기 때문에, 같은 16:9 비율이어도 원본과 대상의 절대 크기(EMU)가
    다르면 도형이 원래 크기 그대로 붙어 작게 보이는 문제가 생긴다 — 이를 방지하기 위한 함수.
    그룹 도형은 최상위 xfrm(off/ext)만 스케일하면 내부 좌표(chOff/chExt)는 비율이 자동 유지된다.
    """
    ns_p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"

    with zipfile.ZipFile(src_path, "r") as zf:
        src_width, src_height = _get_zip_slide_size(zf)
        if not src_width or not src_height or not dst_width or not dst_height:
            return None
        if abs(src_width - dst_width) < 1000 and abs(src_height - dst_height) < 1000:
            return None  # 이미 거의 동일한 크기 → 스케일 불필요

        scale_x = dst_width / src_width
        scale_y = dst_height / src_height

        slide_paths = _slide_paths_ordered(zf)
        if slide_index >= len(slide_paths):
            return None
        slide_path = slide_paths[slide_index]
        slide_xml = _read_xml(zf, slide_path)

        cSld = slide_xml.find(f"{{{ns_p}}}cSld")
        spTree = cSld.find(f"{{{ns_p}}}spTree") if cSld is not None else None
        if spTree is None:
            return None

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

        out_fd, out_path = tempfile.mkstemp(suffix=".pptx")
        os.close(out_fd)
        with zipfile.ZipFile(src_path, "r") as zf2, zipfile.ZipFile(
            out_path, "w", zipfile.ZIP_DEFLATED
        ) as out_zf:
            for name in zf2.namelist():
                if name == slide_path:
                    out_zf.writestr(name, _xml_bytes(slide_xml))
                else:
                    out_zf.writestr(name, zf2.read(name))

    return out_path

def copy_slide_from_file_zip(src_path, src_slide_index, dst_path, insert_after):
    out_fd, out_path = tempfile.mkstemp(suffix=".pptx")
    os.close(out_fd)

    with zipfile.ZipFile(src_path, "r") as src_zf, zipfile.ZipFile(
        dst_path, "r"
    ) as dst_zf:

        src_slide_paths = _slide_paths_ordered(src_zf)
        if src_slide_index >= len(src_slide_paths):
            raise ValueError(f"Slide index {src_slide_index} out of range")
        src_slide_path = src_slide_paths[src_slide_index]
        src_rels_path = _rels_path(src_slide_path)

        dst_prs_xml = _read_xml(dst_zf, "ppt/presentation.xml")
        dst_prs_rels = _read_xml(dst_zf, "ppt/_rels/presentation.xml.rels")
        dst_ct_xml = _read_xml(dst_zf, "[Content_Types].xml")

        new_slide_num = _max_slide_num(dst_zf) + 1
        new_slide_path = f"ppt/slides/slide{new_slide_num}.xml"
        new_rels_path = f"ppt/slides/_rels/slide{new_slide_num}.xml.rels"
        new_rid = f"rId{_max_rid(dst_prs_rels)}"
        new_sld_id = _max_sld_id(dst_prs_xml)

        src_rels_root = etree.Element("{%s}Relationships" % NSMAP["pr"])
        if src_rels_path in src_zf.namelist():
            src_rels_root = _read_xml(src_zf, src_rels_path)

        dst_names = set(dst_zf.namelist())
        extra_files = {}
        ct_defaults = {
            el.get("Extension", "").lower()
            for el in dst_ct_xml.findall(qn("ct:Default"))
        }
        ct_overrides = {
            el.get("PartName", "") for el in dst_ct_xml.findall(qn("ct:Override"))
        }

        new_rels_root = etree.Element("{%s}Relationships" % NSMAP["pr"])

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

            if src_full not in src_zf.namelist():
                new_rel.set("Target", target)
                continue

            file_bytes = src_zf.read(src_full)
            ext = os.path.splitext(src_full)[1].lower().lstrip(".")

            dst_target = src_full
            counter = 2
            all_used = dst_names | set(extra_files.keys())
            while dst_target in all_used:
                base, dot_ext = os.path.splitext(src_full)
                dst_target = f"{base}_{counter}{dot_ext}"
                counter += 1

            extra_files[dst_target] = file_bytes

            if ext and ext not in ct_defaults:
                mime = EXT_MIME.get(ext, "application/octet-stream")
                nd = etree.SubElement(dst_ct_xml, qn("ct:Default"))
                nd.set("Extension", ext)
                nd.set("ContentType", mime)
                ct_defaults.add(ext)

            new_rel.set("Target", "../" + dst_target[4:])

        part_name = "/" + new_slide_path
        if part_name not in ct_overrides:
            ov = etree.SubElement(dst_ct_xml, qn("ct:Override"))
            ov.set("PartName", part_name)
            ov.set(
                "ContentType",
                "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
            )

        pr_rel = etree.SubElement(dst_prs_rels, qn("pr:Relationship"))
        pr_rel.set("Id", new_rid)
        pr_rel.set(
            "Type",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
        )
        pr_rel.set("Target", f"slides/slide{new_slide_num}.xml")

        sldIdLst = dst_prs_xml.find(qn("p:sldIdLst"))
        new_sldId_el = etree.Element(qn("p:sldId"))
        new_sldId_el.set("id", str(new_sld_id))
        new_sldId_el.set(qn("r:id"), new_rid)

        children = list(sldIdLst)
        pos = min(insert_after + 1, len(children))
        for c in children:
            sldIdLst.remove(c)
        children.insert(pos, new_sldId_el)
        for c in children:
            sldIdLst.append(c)

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as out_zf:
            skip = {
                "ppt/presentation.xml",
                "ppt/_rels/presentation.xml.rels",
                "[Content_Types].xml",
            }
            for name in dst_zf.namelist():
                if name not in skip:
                    out_zf.writestr(name, dst_zf.read(name))
            out_zf.writestr(new_slide_path, src_zf.read(src_slide_path))
            out_zf.writestr(new_rels_path, _xml_bytes(new_rels_root))
            for dst_name, fb in extra_files.items():
                if dst_name not in dst_zf.namelist():
                    out_zf.writestr(dst_name, fb)
            out_zf.writestr("ppt/presentation.xml", _xml_bytes(dst_prs_xml))
            out_zf.writestr("ppt/_rels/presentation.xml.rels", _xml_bytes(dst_prs_rels))
            out_zf.writestr("[Content_Types].xml", _xml_bytes(dst_ct_xml))

    return out_path


def duplicate_slide_zip(pptx_path, slide_index, insert_after):
    return copy_slide_from_file_zip(pptx_path, slide_index, pptx_path, insert_after)


def embed_slide_background(src_path: str, slide_index: int):
    """
    슬라이드에 p:bg가 없으면 slideLayout → slideMaster 순으로 배경을 찾아
    슬라이드 XML에 직접 삽입한 새 임시파일 경로를 반환.
    배경이 이미 있거나 찾지 못하면 None 반환.
    """
    ns_p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ns_r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pr_ns = NSMAP["pr"]

    with zipfile.ZipFile(src_path, "r") as zf:
        slide_paths = _slide_paths_ordered(zf)
        if slide_index >= len(slide_paths):
            return None
        slide_path = slide_paths[slide_index]
        slide_xml = _read_xml(zf, slide_path)

        cSld = slide_xml.find(f"{{{ns_p}}}cSld")
        if cSld is None:
            return None

        # 슬라이드 자체에 이미 배경 있으면 불필요
        if cSld.find(f"{{{ns_p}}}bg") is not None:
            return None

        # slide rels → slideLayout 경로
        slide_rels_path = _rels_path(slide_path)
        layout_path = None
        if slide_rels_path in zf.namelist():
            srels = _read_xml(zf, slide_rels_path)
            for rel in srels:
                if "slideLayout" in rel.get("Type", ""):
                    t = rel.get("Target", "")
                    layout_path = (
                        ("ppt/" + t[3:]) if t.startswith("../") else ("ppt/slides/" + t)
                    )
                    break
        if not layout_path or layout_path not in zf.namelist():
            return None

        # layout에서 p:bg 탐색
        layout_xml = _read_xml(zf, layout_path)
        layout_cSld = layout_xml.find(f"{{{ns_p}}}cSld")
        bg_el = layout_cSld.find(f"{{{ns_p}}}bg") if layout_cSld is not None else None
        bg_rels_path = _rels_path(layout_path)  # 이미지 rid 기준 rels

        # layout에 없으면 slideMaster 탐색
        if bg_el is None:
            master_path = None
            if bg_rels_path in zf.namelist():
                lrels = _read_xml(zf, bg_rels_path)
                for rel in lrels:
                    if "slideMaster" in rel.get("Type", ""):
                        t = rel.get("Target", "")
                        master_path = (
                            ("ppt/" + t[3:])
                            if t.startswith("../")
                            else ("ppt/slideLayouts/" + t)
                        )
                        break
            if not master_path or master_path not in zf.namelist():
                return None
            master_xml = _read_xml(zf, master_path)
            master_cSld = master_xml.find(f"{{{ns_p}}}cSld")
            bg_el = (
                master_cSld.find(f"{{{ns_p}}}bg") if master_cSld is not None else None
            )
            bg_rels_path = _rels_path(master_path)  # 이미지 rid는 master rels 기준

        if bg_el is None:
            return None

        bg_copy = copy.deepcopy(bg_el)

        # 배경 안 blip의 r:embed rid → 슬라이드 rels에 이미지 등록
        blips = bg_copy.findall(f".//{{{ns_a}}}blip")
        new_rels_to_add = []  # (new_rid, img_dst_path, img_bytes)
        rid_remap = {}

        if blips and bg_rels_path in zf.namelist():
            bg_rels_xml = _read_xml(zf, bg_rels_path)
            rid_to_target = {r.get("Id", ""): r.get("Target", "") for r in bg_rels_xml}

            # 슬라이드 기존 rels에서 최대 rid 번호 추출
            srels_xml = (
                _read_xml(zf, slide_rels_path)
                if slide_rels_path in zf.namelist()
                else etree.Element(f"{{{pr_ns}}}Relationships")
            )
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

                if img_path not in zf.namelist():
                    continue

                img_bytes = zf.read(img_path)
                max_rid_num += 1
                new_rid = f"rId{max_rid_num}"
                rid_remap[old_rid] = new_rid
                new_rels_to_add.append((new_rid, img_path, img_bytes))

            for blip in blips:
                old_rid = blip.get(f"{{{ns_r}}}embed", "")
                if old_rid in rid_remap:
                    blip.set(f"{{{ns_r}}}embed", rid_remap[old_rid])

        # 새 pptx 작성
        out_fd, out_path = tempfile.mkstemp(suffix=".pptx")
        os.close(out_fd)

        with zipfile.ZipFile(src_path, "r") as zf2, zipfile.ZipFile(
            out_path, "w", zipfile.ZIP_DEFLATED
        ) as out_zf:

            # 슬라이드 rels에 이미지 rid 추가
            srels_xml2 = (
                _read_xml(zf2, slide_rels_path)
                if slide_rels_path in zf2.namelist()
                else etree.Element(f"{{{pr_ns}}}Relationships")
            )
            for new_rid, img_path, img_bytes in new_rels_to_add:
                new_rel = etree.SubElement(srels_xml2, f"{{{pr_ns}}}Relationship")
                new_rel.set("Id", new_rid)
                new_rel.set("Type", f"{ns_r}/image")
                img_filename = img_path.split("/")[-1]
                new_rel.set("Target", f"../media/{img_filename}")

            # 슬라이드 XML에 bg_copy 삽입 (cSld 첫 번째 자식)
            slide_xml2 = _read_xml(zf2, slide_path)
            cSld2 = slide_xml2.find(f"{{{ns_p}}}cSld")
            if cSld2 is not None:
                cSld2.insert(0, bg_copy)

            for name in zf2.namelist():
                if name == slide_path:
                    out_zf.writestr(name, _xml_bytes(slide_xml2))
                elif name == slide_rels_path:
                    out_zf.writestr(name, _xml_bytes(srels_xml2))
                else:
                    out_zf.writestr(name, zf2.read(name))

            # 새 이미지 파일 추가
            for new_rid, img_path, img_bytes in new_rels_to_add:
                img_filename = img_path.split("/")[-1]
                dst = f"ppt/media/{img_filename}"
                if dst not in zf2.namelist():
                    out_zf.writestr(dst, img_bytes)

    return out_path
