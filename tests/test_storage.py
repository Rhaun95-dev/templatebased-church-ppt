import json
import os
import tempfile
import unittest

import requests

from church_ppt.errors import NotFound, StorageUnavailable
from church_ppt.storage import LocalStorage, SupabaseStorage
from tests.helpers import make_pptx


class FakeResp:
    def __init__(self, status=200, content=b"", payload=None):
        self.status_code = status
        self.content = content
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.objects = {}
        self.fail = None

    def request(self, method, url, headers=None, data=None, timeout=None, **kw):
        if self.fail:
            raise self.fail
        key = url.split("/church-ppt/", 1)[1]
        if method == "GET":
            if key in self.objects:
                return FakeResp(200, self.objects[key])
            return FakeResp(404)
        if method == "POST":
            assert headers["x-upsert"] == "true"
            self.objects[key] = data if isinstance(data, bytes) else data.read()
            return FakeResp(200)
        raise AssertionError(method)


class SupabaseTests(unittest.TestCase):
    def setUp(self):
        self.sess = FakeSession()
        self.st = SupabaseStorage("https://x.supabase.co", "svc", session=self.sess)

    def test_config_default_when_missing(self):
        self.assertEqual(self.st.get_config()["hymn_slots"], [])

    def test_put_config_strips_local_paths(self):
        self.st.put_config({"hymn_slots": [{"name": "a", "after_slide_index": 0}],
                            "template_file": "R:\\x.pptx", "hymn_folder": "R:\\h", "mode": "supabase"})
        saved = json.loads(self.sess.objects["config.json"])
        self.assertNotIn("template_file", saved)
        self.assertNotIn("hymn_folder", saved)
        self.assertNotIn("mode", saved)
        self.assertNotIn("template_file", self.st.get_config())

    def test_get_config_drops_stray_local_paths(self):
        self.sess.objects["config.json"] = json.dumps(
            {"hymn_slots": [], "template_file": "R:\\x.pptx", "hymn_folder": "R:\\h"}).encode()
        cfg = self.st.get_config()
        self.assertNotIn("template_file", cfg)
        self.assertNotIn("hymn_folder", cfg)

    def test_open_template_missing_is_notfound(self):
        with self.assertRaises(NotFound):
            with self.st.open_template():
                pass

    def test_open_template_temp_deleted(self):
        d = tempfile.mkdtemp()
        p = make_pptx(os.path.join(d, "a.pptx"))
        with open(p, "rb") as f:
            self.st.put_template(f.read())
        with self.st.open_template() as path:
            self.assertTrue(os.path.exists(path))
        self.assertFalse(os.path.exists(path))

    def test_unreachable_is_503(self):
        self.sess.fail = requests.ConnectionError("down")
        with self.assertRaises(StorageUnavailable):
            self.st.get_config()


class LocalTests(unittest.TestCase):
    def test_local_ignores_cloud_and_roundtrips(self):
        d = tempfile.mkdtemp()
        st = LocalStorage(os.path.join(d, "config.json"))
        st.put_config({"template_file": "C:\\t.pptx", "hymn_slots": []})
        self.assertEqual(st.get_config()["template_file"], "C:\\t.pptx")


if __name__ == "__main__":
    unittest.main()
