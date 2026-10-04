"""찬송가 폴더 검색 (파일명 규칙: 번호_제목.pptx)"""
import os
import re

HYMN_FILE_RE = re.compile(r"^(\d+)[\s_\-]*(.*?)\.pptx$", re.IGNORECASE)


def list_hymns(folder):
    hymns = []
    for f in sorted(os.listdir(folder)):
        if f.lower().endswith(".pptx"):
            m = HYMN_FILE_RE.match(f)
            if m:
                hymns.append(
                    {
                        "number": int(m.group(1)),
                        "title": m.group(2).strip(),
                        "filename": f,
                    }
                )
            else:
                hymns.append(
                    {"number": None, "title": f.replace(".pptx", ""), "filename": f}
                )
    return hymns


def search_hymn(folder, number):
    """번호에 해당하는 찬송가의 (파일명, 제목), 없으면 None"""
    for f in os.listdir(folder):
        m = HYMN_FILE_RE.match(f)
        if m and int(m.group(1)) == int(number):
            return f, m.group(2).strip()
    return None


def find_hymn_file(folder, number):
    if not folder or not os.path.exists(folder):
        return None
    found = search_hymn(folder, number)
    return os.path.join(folder, found[0]) if found else None
