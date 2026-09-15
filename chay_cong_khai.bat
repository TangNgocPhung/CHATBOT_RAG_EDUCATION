@echo off
setlocal
cd /d "%~dp0"

rem ============================================================
rem  CHAY BAN CONG KHAI (co mat khau + duong ham Cloudflare)
rem ============================================================
rem  Khac start_ui.bat o hai diem:
rem    - Bat RAG_CONG_KHAI=1: thieu mat khau la ung dung TU CHOI chay,
rem      de khong bao gio mo duong ham ra ma quen khoa cua.
rem    - Mo duong ham Cloudflare, in ra dia chi cong khai.
rem ============================================================

if not exist "mat_khau.bat" (
  echo [LOI] Chua co mat_khau.bat - xem mat_khau.mau.bat de tao.
  pause
  exit /b 1
)
call "mat_khau.bat"

if exist "khoa_api.bat" call "khoa_api.bat"

set "RAG_PORT=8010"
set "RAG_CONG_KHAI=1"
rem Da co mat khau thi run_ui.py khong do duoc /api/status de tu mo tab,
rem tat han cho do cho 60 lan vo ich.
set "RAG_OPEN_BROWSER=0"

if not exist ".venv\Scripts\python.exe" (
  echo [LOI] Chua co moi truong Python .venv.
  pause
  exit /b 1
)

echo Dang khoi dong ung dung (nap kho tri thuc mat vai phut)...
start "Chatbot RAG" /min ".venv\Scripts\python.exe" run_ui.py

echo.
echo Dang mo duong ham Cloudflare. Dia chi cong khai se hien o duoi
echo dang https://....trycloudflare.com - dua dia chi do cho nguoi can dung.
echo Tai khoan: %RAG_TAI_KHOAN%   (mat khau nam trong mat_khau.bat)
echo.
echo DONG CUA SO NAY LA DONG LUON DUONG HAM.
echo.
cloudflared tunnel --url http://127.0.0.1:8010
