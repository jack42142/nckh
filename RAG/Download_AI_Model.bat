@echo off
chcp 65001 > nul
title Tai Model Qwen3 tu Hugging Face

echo ===================================================
echo     CONG CU TAI MODEL QWEN3 TU HUGGING FACE
echo ===================================================
echo.
set "VENV_PATH=..\hung"

if exist "%VENV_PATH%\Scripts\activate.bat" (
    echo [*] Dang kich hoat venv tai: %VENV_PATH%
    call "%VENV_PATH%\Scripts\activate.bat"
) else (
    echo [X] Khong tim thay activate.bat tai: %VENV_PATH%\Scripts
    echo Vui long kiem tra lai duong dan môi truong ao!
    pause
    exit /b
)
:: Kiem tra va cai dat huggingface_hub
python -c "import huggingface_hub" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Dang cai dat thu vien huggingface_hub...
    pip install -U "huggingface_hub[cli]"
    echo.
)

:MENU
echo Chon model ban muon tai:
echo  [1] Qwen/Qwen3-4B
echo  [2] Qwen/Qwen3-8B
echo  [3] Thoat
echo.
set /p CHOICE="Nhap lua chon cua ban (1-3): "

if "%CHOICE%"=="1" goto DOWNLOAD_4B
if "%CHOICE%"=="2" goto DOWNLOAD_8B
if "%CHOICE%"=="3" goto END
echo.
echo [X] Lua chon khong hop le. Vui long chon lai!
echo.
goto MENU

:DOWNLOAD_4B
echo.
echo Dang tai Qwen/Qwen3-4B
hf download Qwen/Qwen3-4B --revision main --local-dir ./models/Qwen3-4B
goto FINISH

:DOWNLOAD_8B
echo.
echo Dang tai Qwen/Qwen3-8B 
hf download Qwen/Qwen3-8B --revision main --local-dir ./models/Qwen3-8B
goto FINISH

:FINISH
echo.
echo [OK] Hoan thanh qua trinh tai model!
pause
exit

:END
echo Tam biệt!
pause
exit