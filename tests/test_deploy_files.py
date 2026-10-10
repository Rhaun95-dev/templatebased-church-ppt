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

    def test_render_deploys_only_after_ci_passes(self):
        self.assertIn("autoDeployTrigger: checksPass", read("render.yaml"))

    def test_ci_workflow_covers_pull_requests_and_master(self):
        ci = read(".github/workflows/ci.yml")
        for needle in ("pull_request:", "branches: [master]", "unittest discover",
                       "py_compile", "hymn-library.test.js", "node --check"):
            self.assertIn(needle, ci)

    def test_deploy_verify_waits_for_ci_and_checks_commit(self):
        v = read(".github/workflows/deploy-verify.yml")
        self.assertIn("workflows: [CI]", v)
        self.assertIn("/api/health", v)
        self.assertIn("head_sha", v)

    def test_health_reports_render_commit_only_when_set(self):
        from unittest import mock
        from app import create_app

        app = create_app({"TESTING": True, "STORAGE": "local",
                          "CONFIG_FILE": os.path.join(ROOT, "no-such-config.json")})
        with mock.patch.dict(os.environ, {"RENDER_GIT_COMMIT": "abc123"}):
            self.assertEqual(app.test_client().get("/api/health").get_json(),
                             {"ok": True, "commit": "abc123"})
        env = {k: v for k, v in os.environ.items() if k != "RENDER_GIT_COMMIT"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(app.test_client().get("/api/health").get_json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
