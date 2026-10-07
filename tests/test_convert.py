import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from church_ppt import ppt_convert
from church_ppt.errors import ConversionError


class ConvertTests(unittest.TestCase):
    def test_module_imports_without_pywin32(self):
        with mock.patch.dict(sys.modules, {"pythoncom": None, "win32com": None, "win32com.client": None}):
            importlib.reload(ppt_convert)  # must not raise ImportError
        importlib.reload(ppt_convert)

    def test_libreoffice_missing_raises_conversion_error(self):
        fd, p = tempfile.mkstemp(suffix=".ppt"); os.close(fd)
        try:
            with mock.patch.object(ppt_convert, "_com_available", return_value=False), \
                 mock.patch.object(ppt_convert.shutil, "which", return_value=None):
                with self.assertRaises(ConversionError):
                    ppt_convert.convert_ppt_to_pptx(p)
        finally:
            os.unlink(p)

    def test_libreoffice_timeout_cleans_outdir(self):
        fd, p = tempfile.mkstemp(suffix=".ppt"); os.close(fd)
        created = []
        real_mkdtemp = tempfile.mkdtemp

        def spy(*a, **k):
            d = real_mkdtemp(*a, **k); created.append(d); return d
        try:
            with mock.patch.object(ppt_convert, "_com_available", return_value=False), \
                 mock.patch.object(ppt_convert.shutil, "which", return_value="soffice"), \
                 mock.patch.object(ppt_convert.tempfile, "mkdtemp", side_effect=spy), \
                 mock.patch.object(ppt_convert.subprocess, "run",
                                   side_effect=subprocess.TimeoutExpired("soffice", 1)):
                with self.assertRaises(ConversionError):
                    ppt_convert.convert_ppt_to_pptx(p)
            self.assertTrue(created)
            self.assertFalse(any(os.path.exists(d) for d in created))
        finally:
            os.unlink(p)


if __name__ == "__main__":
    unittest.main()
