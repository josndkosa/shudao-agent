# -*- coding: utf-8 -*-
"""用 PowerPoint COM 把 pptx 导出为 pdf（无 LibreOffice 时的本地方案）。

PPT 内容变更后必须重出 PDF：package.py 的占位闸只穿扫 pptx，PDF 里的旧下划线
不会被拦下，但评委会看到。所以这里把同步重出当成打包前的固定动作。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # 仓库根（本文件在 scripts/ 下）
pptx = ROOT / "ppt" / "蜀道智行.pptx"
pdf = ROOT / "ppt" / "蜀道智行.pdf"

if not pptx.is_file():
    sys.exit(f"找不到 {pptx}")

try:
    import win32com.client  # type: ignore
except ImportError:
    sys.exit("pywin32 未安装：pip install pywin32")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

app = win32com.client.Dispatch("PowerPoint.Application")
# COM 要求 Application 可见；WithWindow=False 打开演示文稿即可不弹窗
pres = app.Presentations.Open(str(pptx), ReadOnly=True, WithWindow=False)
try:
    pres.SaveAs(str(pdf), 32)          # 32 = ppSaveAsPDF
    print(f"已导出 {pdf.name}：{pdf.stat().st_size:,} 字节")
finally:
    pres.Close()
    app.Quit()
