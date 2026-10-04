"""PowerPoint(COM)를 이용한 .ppt → .pptx 변환 (Windows 전용)"""
import os

import pythoncom
import win32com.client


def convert_ppt_to_pptx(ppt_path):
    powerpoint = None
    presentation = None

    try:
        # COM 초기화
        pythoncom.CoInitialize()

        powerpoint = win32com.client.Dispatch("PowerPoint.Application")
        powerpoint.Visible = 1

        abs_path = os.path.abspath(ppt_path)

        presentation = powerpoint.Presentations.Open(
            abs_path,
            WithWindow=False
        )

        pptx_path = os.path.splitext(abs_path)[0] + ".pptx"

        # 24 = pptx format
        presentation.SaveAs(pptx_path, 24)

        return pptx_path

    finally:
        try:
            if presentation:
                presentation.Close()
        except:
            pass

        try:
            if powerpoint:
                powerpoint.Quit()
        except:
            pass

        try:
            pythoncom.CoUninitialize()
        except:
            pass
