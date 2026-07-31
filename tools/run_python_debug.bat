@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\pythonw.exe" (
  echo Python environment not found. Install requirements first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "source\godimap_ocr_debug.py"
exit /b 0
