import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


class DeployFileTests(unittest.TestCase):
    def test_requirements_marks_pywin32_windows_only(self):
        req = read("requirements.txt")
        self.assertIn("gunicorn", req)
        self.assertIn("pywin32; sys_platform == 'win32'", req)

    def test_dockerfile_essentials(self):
        d = read("Dockerfile")
        for needle in ("python:3.12-slim", "libreoffice-impress", "fonts-nanum", "--workers 1", "app:app"):
            self.assertIn(needle, d)

    def test_dockerignore_excludes_secrets_and_config(self):
        ig = read(".dockerignore")
        for needle in (".env", "config.json", ".git", "public"):
            self.assertIn(needle, ig)

    def test_health_path_used_by_render_and_keepalive(self):
        self.assertIn("healthCheckPath: /api/health", read("render.yaml"))
        self.assertIn("/api/health", read(".github/workflows/keepalive.yml"))


if __name__ == "__main__":
    unittest.main()
