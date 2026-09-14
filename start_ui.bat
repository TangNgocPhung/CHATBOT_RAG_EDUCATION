@echo off
setlocal
cd /d "%~dp0"

rem Nap khoa Google Drive API neu co (xem khoa_api.mau.bat)
if exist "khoa_api.bat" call "khoa_api.bat"

if not exist ".venv\Scripts\python.exe" (
  echo [LOI] Chua co moi truong Python .venv.
  echo Hay chay: py -3.11 -m venv .venv
  echo Sau do: .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

echo Dang khoi dong Chatbot RAG Giao duc...
".venv\Scripts\python.exe" run_ui.py
if errorlevel 1 pause
