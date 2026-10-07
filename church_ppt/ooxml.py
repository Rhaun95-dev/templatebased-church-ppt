"""OOXML 네임스페이스 헬퍼"""

NSMAP = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}


def qn(tag):
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        return "{%s}%s" % (NSMAP[prefix], local)
    return tag
