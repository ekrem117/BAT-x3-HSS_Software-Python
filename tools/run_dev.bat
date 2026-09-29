@echo off
REM Gelistirme baslatici: main.py'yi ayri bir konsol penceresinde acar,
REM sonra test_receiver.py'yi mevcut terminalde calistirir.
REM
REM Uretim kodunun parcasi degildir; elle calistirilir.
REM
REM Kullanim (proje kokunden):
REM     tools\run_dev.bat
REM
REM main.py'yi durdurmak icin acilan "BAT-X3 main" penceresinde Ctrl+C.

setlocal

cd /d "%~dp0.."

REM venv varsa onu kullan, yoksa PATH'teki python'a dus.
if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

start "BAT-X3 main" cmd /k "%PYTHON% main.py"

REM Kamera/servisler ayaga kalksin diye kisa bekleme.
timeout /t 2 >nul

%PYTHON% tools\test_receiver.py

endlocal
