@echo off
chcp 65001 >nul
title RGPad - dong cua so nay de tat
cd /d "%~dp0"
where python >nul 2>nul || (
  echo Chua cai Python. Tai tai https://www.python.org/downloads/ ^(nho tick "Add python.exe to PATH"^)
  pause
  exit /b 1
)
python -c "import vgamepad" >nul 2>nul || python -m pip install vgamepad
echo Dang chay RGPad...
python rgpad_web.py %*
rem tat binh thuong (ma 0) thi cua so tu dong; co loi / da chay roi thi dung lai de doc
if errorlevel 1 pause
