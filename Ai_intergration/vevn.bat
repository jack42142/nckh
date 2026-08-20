@echo off
chcp 65001 > nul
title Moi truong ao - HUNG VENV

set "VENV_PATH=..\hung"

if exist "%VENV_PATH%\Scripts\activate.bat" (
    echo [*] Dang kích hoat venv tai: %VENV_PATH%
    call "%VENV_PATH%\Scripts\activate.bat"
    echo [OK] Da vao venv thanh cong!
    echo.
    cmd /k
) else (
    echo [X] Khong tim thay activate.bat tai duong dan tren!
    pause
)