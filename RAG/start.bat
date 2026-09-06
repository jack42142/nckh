@echo off
chcp 65001 >nul
title Genshin RAG Server

cd /d "%~dp0"

echo ==========================================
echo   Genshin Impact Lore RAG
echo ==========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.12+.
    pause
    exit /b 1
)

REM Check dependencies
echo [1/3] Checking dependencies...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo [INSTALL] Installing dependencies...
    pip install fastapi uvicorn chromadb sentence-transformers tiktoken pydantic
)

REM Check chroma_data
echo [2/3] Checking database...
if not exist "chroma_data\chroma.sqlite3" (
    echo [WARNING] chroma_data not found. Run the pipeline first:
    echo   1. python crawl_enhanced.py --lang en
    echo   2. python chunk.py --input genshin_rag_pages_en.json --output genshin_chunks_en.json
    echo   3. python embed.py ingest --input genshin_chunks_en.json --collection genshin_lore
    echo.
)

REM Check collections
echo [3/3] Checking collections...
python -c "import sys; sys.path.insert(0,'.'); from embed import get_chroma_client, CHROMA_DIR; client = get_chroma_client(CHROMA_DIR); colls = [c.name for c in client.list_collections()]; print('Collections:', ', '.join(colls) if colls else 'none')" 2>nul

echo.
echo ==========================================
echo   Starting server...
echo ==========================================
echo.
echo   Open browser: http://localhost:8000/
echo   API docs:     http://localhost:8000/docs
echo   Stop:         Ctrl+C
echo.
echo ==========================================
echo.

REM Open browser (optional)
REM Uncomment the line below to auto-open browser:
REM start http://localhost:8000/

python app.py

pause
