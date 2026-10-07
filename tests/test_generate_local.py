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


class GenerateLocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.template = make_pptx(os.path.join(self.tmp, "t.pptx"), 3)
        self.hymn = make_pptx(os.path.join(self.tmp, "h.pptx"), 2)
        self.app = create_app({"TESTING": True, "STORAGE": "local",
                               "CONFIG_FILE": os.path.join(self.tmp, "config.json")})
        self.client = self.app.test_client()

    def _payload(self):
        return {"template_file": self.template,
                "hymn_slots": [{"name": "a", "after_slide_index": 0, "upload_key": "hymn_file_0", "skip": False}]}

    def test_generate_with_uploaded_hymn_adds_slides(self):
        with open(self.hymn, "rb") as f:
            res = self.client.post("/api/generate", data={
                "payload": json.dumps(self._payload()),
                "hymn_file_0": (f, "h.pptx")})
        self.assertEqual(res.status_code, 200)
        prs = Presentation(io.BytesIO(res.data))
        self.assertEqual(len(prs.slides), 5)

    def test_removed_server_hymn_routes(self):
        self.assertEqual(self.client.post("/api/scan-hymns", json={"folder": "x"}).status_code, 404)
        self.assertEqual(self.client.post("/api/search-hymn", json={"folder": "x", "number": 1}).status_code, 404)

    def test_unconvertible_ppt_returns_422_and_cleans_temp(self):
        before = set(os.listdir(tempfile.gettempdir()))
        # Force the LibreOffice path with no converter installed, so the result
        # does not depend on whether PowerPoint (COM) exists on the test machine.
        with mock.patch.object(ppt_convert, "_com_available", return_value=False),              mock.patch.object(ppt_convert.shutil, "which", return_value=None):
            res = self.client.post("/api/generate", data={
                "payload": json.dumps(self._payload()),
                "hymn_file_0": (io.BytesIO(b"not a ppt"), "bad.ppt")})
        self.assertEqual(res.status_code, 422)
        self.assertIn("pptx", res.get_json()["error"])
        leaked = [f for f in set(os.listdir(tempfile.gettempdir())) - before if f.endswith((".ppt", ".pptx"))]
        self.assertEqual(leaked, [])


if __name__ == "__main__":
    unittest.main()
