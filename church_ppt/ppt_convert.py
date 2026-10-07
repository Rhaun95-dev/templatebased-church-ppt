"""`.ppt` → `.pptx` 변환: PowerPoint(COM) 우선, 없으면 LibreOffice headless"""
import glob
import os
import shutil
import subprocess
import tempfile
import threading

from .errors import ConversionError

_LOCK = threading.Lock()
LIBREOFFICE_TIMEOUT = 90
RESAVE_HINT = "파일을 .pptx로 다시 저장해서 올려주세요"


def _com_available():
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    return True


def _convert_com(ppt_path):
    import pythoncom
    import win32com.client

    powerpoint = presentation = None
    try:
        pythoncom.CoInitialize()
        powerpoint = win32com.client.Dispatch("PowerPoint.Application")
        powerpoint.Visible = 1
        abs_path = os.path.abspath(ppt_path)
        presentation = powerpoint.Presentations.Open(abs_path, WithWindow=False)
        pptx_path = os.path.splitext(abs_path)[0] + ".pptx"
        presentation.SaveAs(pptx_path, 24)  # 24 = pptx
        return pptx_path
    except Exception as e:
        raise ConversionError(f"PowerPoint 변환 실패: {e}. {RESAVE_HINT}") from e
    finally:
        for fn in (
            lambda: presentation and presentation.Close(),
            lambda: powerpoint and powerpoint.Quit(),
            pythoncom.CoUninitialize,
        ):
            try:
                fn()
            except Exception:
                pass


def _convert_libreoffice(ppt_path):
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ConversionError(f"변환기를 찾을 수 없어요. {RESAVE_HINT}")
    outdir = tempfile.mkdtemp(prefix="lo_out_")
    profile = tempfile.mkdtemp(prefix="lo_profile_")
    try:
        with _LOCK:
            subprocess.run(
                [soffice, "--headless", "--norestore",
                 f"-env:UserInstallation=file:///{profile.replace(os.sep, '/')}",
                 "--convert-to", "pptx", "--outdir", outdir, ppt_path],
                check=True, capture_output=True, timeout=LIBREOFFICE_TIMEOUT,
            )
        produced = glob.glob(os.path.join(outdir, "*.pptx"))
        if not produced:
            raise ConversionError(f"변환 결과가 없어요. {RESAVE_HINT}")
        final = os.path.splitext(ppt_path)[0] + ".converted.pptx"
        shutil.move(produced[0], final)
        return final
    except subprocess.TimeoutExpired as e:
        raise ConversionError(f"변환 시간이 초과됐어요. {RESAVE_HINT}") from e
    except subprocess.CalledProcessError as e:
        raise ConversionError(f"변환 실패. {RESAVE_HINT}") from e
    finally:
        shutil.rmtree(outdir, ignore_errors=True)
        shutil.rmtree(profile, ignore_errors=True)


def convert_ppt_to_pptx(ppt_path):
    """변환된 pptx 경로 반환 (호출자가 삭제). 실패 시 ConversionError"""
    if _com_available():
        return _convert_com(ppt_path)
    return _convert_libreoffice(ppt_path)
