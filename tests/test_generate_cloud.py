import io
import json
import os
import tempfile
import unittest
from contextlib import contextmanager

from pptx import Presentation

from app import create_app
from church_ppt.errors import NotFound
from tests.helpers import make_pptx


class FakeCloud:
    mode = "supabase"

    def __init__(self, template_bytes=None):
        self.template = template_bytes
        self.cfg = {"hymn_slots": []}
        self.opened = []

    @contextmanager
    def open_template(self, override=None):
        if self.template is None:
            raise NotFound("템플릿을 업로드해주세요")
        fd, p = tempfile.mkstemp(suffix=".pptx")
        os.close(fd)
        with open(p, "wb") as f:
            f.write(self.template)
        self.opened.append(p)
        try:
            yield p
        finally:
            os.unlink(p)

    def put_template(self, data):
        self.template = data

    def get_config(self):
        return dict(self.cfg)

    def put_config(self, cfg):
        self.cfg = cfg


class CloudGenerateTests(unittest.TestCase):
    def make_client(self, storage):
        app = create_app({"TESTING": True})
        app.extensions["storage"] = storage
        return app.test_client()

    def test_generate_uses_cloud_template_and_cleans_up(self):
        d = tempfile.mkdtemp()
        with open(make_pptx(os.path.join(d, "t.pptx"), 3), "rb") as f:
            tpl = f.read()
        with open(make_pptx(os.path.join(d, "h.pptx"), 2), "rb") as f:
            hymn = f.read()
        st = FakeCloud(tpl)
        c = self.make_client(st)
        res = c.post("/api/generate", data={
            "payload": json.dumps({"template_file": "R:\\evil.pptx", "hymn_slots": [
                {"name": "a", "after_slide_index": 0, "upload_key": "hymn_file_0"}]}),
            "hymn_file_0": (io.BytesIO(hymn), "h.pptx")})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(Presentation(io.BytesIO(res.data)).slides), 5)
        self.assertFalse(any(os.path.exists(p) for p in st.opened))

    def test_generate_without_template_is_404_message(self):
        c = self.make_client(FakeCloud(None))
        res = c.post("/api/generate", data={"payload": json.dumps({"hymn_slots": []})})
        self.assertEqual(res.status_code, 404)
        self.assertIn("템플릿", res.get_json()["error"])

    def test_config_get_has_mode_and_no_paths(self):
        st = FakeCloud(None)
        st.cfg = {"hymn_slots": []}
        r = self.make_client(st).get("/api/config").get_json()
        self.assertEqual(r["mode"], "supabase")
        self.assertNotIn("template_file", r)

    def test_template_upload_validates_pptx(self):
        c = self.make_client(FakeCloud(None))
        bad = c.post("/api/template", data={"file": (io.BytesIO(b"junk"), "t.pptx")})
        self.assertEqual(bad.status_code, 422)
        d = tempfile.mkdtemp()
        with open(make_pptx(os.path.join(d, "t.pptx")), "rb") as f:
            good = f.read()
        ok = c.post("/api/template", data={"file": (io.BytesIO(good), "t.pptx")})
        self.assertEqual(ok.status_code, 200)

    def test_template_upload_rejected_in_local_mode(self):
        app = create_app({"TESTING": True, "STORAGE": "local"})
        r = app.test_client().post("/api/template", data={"file": (io.BytesIO(b"x"), "t.pptx")})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
