import time
import unittest
from unittest import mock

from itsdangerous import URLSafeTimedSerializer

from app import create_app
from church_ppt import auth


def client(**cfg):
    base = {"TESTING": True, "APP_PASSWORD": "pw", "SECRET_KEY": "k" * 32}
    base.update(cfg)
    app = create_app(base)
    return app.test_client()


class AuthTests(unittest.TestCase):
    def setUp(self):
        auth._failures.clear()

    def test_guard_blocks_without_cookie(self):
        self.assertEqual(client().get("/api/bible-meta").status_code, 401)

    def test_login_ok_then_access(self):
        c = client()
        r = c.post("/api/login", json={"password": "pw"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("HttpOnly", r.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", r.headers["Set-Cookie"])
        self.assertEqual(c.get("/api/bible-meta").status_code, 200)

    def test_wrong_password_generic_401(self):
        r = client().post("/api/login", json={"password": "nope"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json()["error"], "비밀번호가 올바르지 않아요")

    def test_forged_cookie_rejected(self):
        c = client()
        c.set_cookie("session_token", URLSafeTimedSerializer("other").dumps("ok"))
        self.assertEqual(c.get("/api/bible-meta").status_code, 401)

    def test_expired_cookie_rejected(self):
        c = client()
        c.post("/api/login", json={"password": "pw"})
        with mock.patch("church_ppt.auth.time.time", return_value=time.time() + auth.TOKEN_MAX_AGE + 5):
            self.assertEqual(c.get("/api/bible-meta").status_code, 401)

    def test_rate_limit_429_after_failures(self):
        c = client()
        for _ in range(auth.MAX_FAILURES):
            self.assertEqual(c.post("/api/login", json={"password": "x"}).status_code, 401)
        self.assertEqual(c.post("/api/login", json={"password": "pw"}).status_code, 429)

    def test_auth_off_when_password_unset(self):
        app = create_app({"TESTING": True})
        c = app.test_client()
        self.assertEqual(c.get("/api/bible-meta").status_code, 200)
        self.assertEqual(c.get("/api/session").get_json(), {"auth_required": False, "authenticated": True})

    def test_password_without_secret_key_fails_fast(self):
        with self.assertRaises(RuntimeError):
            create_app({"TESTING": True, "APP_PASSWORD": "pw", "SECRET_KEY": ""})

    def test_index_page_is_public(self):
        self.assertEqual(client().get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
