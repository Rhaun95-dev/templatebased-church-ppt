import io
import json
import os
import tempfile
import unittest
from unittest import mock

from pptx import Presentation

from app import create_app
from church_ppt import ppt_convert
from tests.helpers import make_pptx


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.template = make_pptx(os.path.join(self.tmp, "t.pptx"), 3)
        self.hymn = make_pptx(os.path.join(self.tmp, "h.pptx"), 2)
        self.client = create_app({"TESTING": True}).test_client()

    def _payload(self):
        return {"hymn_slots": [{"name": "a", "after_slide_index": 0, "upload_key": "hymn_file_0", "skip": False}]}

    def _post(self, payload, template=True, **files):
        data = {"payload": json.dumps(payload), **files}
        if template:
            data["template"] = (open(self.template, "rb"), "t.pptx")
        return self.client.post("/api/generate", data=data)

    def test_generate_with_uploaded_hymn_adds_slides(self):
        with open(self.hymn, "rb") as f:
            res = self._post(self._payload(), hymn_file_0=(f, "h.pptx"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(Presentation(io.BytesIO(res.data)).slides), 5)

    def test_generate_uses_template_uploaded_with_request(self):
        res = self._post({"hymn_slots": []})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(Presentation(io.BytesIO(res.data)).slides), 3)

    def test_generate_without_template_is_400(self):
        res = self._post({"hymn_slots": []}, template=False)
        self.assertEqual(res.status_code, 400)
        self.assertIn("템플릿", res.get_json()["error"])

    def test_client_template_path_is_ignored(self):
        res = self._post({"template_file": "R:\\evil.pptx", "hymn_slots": []}, template=False)
        self.assertEqual(res.status_code, 400)

    def test_uploaded_template_must_be_pptx(self):
        res = self.client.post("/api/generate", data={
            "payload": json.dumps({"hymn_slots": []}),
            "template": (io.BytesIO(b"not a zip"), "t.pptx")})
        self.assertEqual(res.status_code, 422)

    def test_removed_server_routes(self):
        self.assertEqual(self.client.post("/api/scan-hymns", json={"folder": "x"}).status_code, 404)
        self.assertEqual(self.client.post("/api/search-hymn", json={"folder": "x", "number": 1}).status_code, 404)
        self.assertEqual(self.client.get("/api/config").status_code, 404)
        self.assertEqual(self.client.post("/api/template-info", json={}).status_code, 404)

    def test_unconvertible_ppt_returns_422_and_cleans_temp(self):
        before = set(os.listdir(tempfile.gettempdir()))
        # Force the LibreOffice path with no converter installed, so the result
        # does not depend on whether PowerPoint (COM) exists on the test machine.
        with mock.patch.object(ppt_convert, "_com_available", return_value=False), \
                mock.patch.object(ppt_convert.shutil, "which", return_value=None):
            res = self._post(self._payload(), hymn_file_0=(io.BytesIO(b"not a ppt"), "bad.ppt"))
        self.assertEqual(res.status_code, 422)
        self.assertIn("pptx", res.get_json()["error"])
        leaked = [f for f in set(os.listdir(tempfile.gettempdir())) - before if f.endswith((".ppt", ".pptx"))]
        self.assertEqual(leaked, [])


if __name__ == "__main__":
    unittest.main()
