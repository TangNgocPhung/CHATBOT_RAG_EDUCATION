@echo off
setlocal
cd /d "%~dp0"

rem Co dinh cong 8010. Khong dat thi run_ui.py lay cong trong dau tien tu
rem 8000, ma cong 8000 tren may nay dang co ung dung khac chiem o IPv6 ->
rem mo localhost:8000 se ra nham app. Neu 8010 bi chiem, ung dung bao loi
rem ro rang thay vi im lang nhay sang cong khac.
set "RAG_PORT=8010"

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
