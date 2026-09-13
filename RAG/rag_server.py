"""
# rag_server.py — FastAPI server cho RAG thocung.com
# Chạy song song với server.js (port 8000) để xử lý RAG

Cú pháp:
    python rag_server.py
    python rag_server.py --no-auto-build
"""

import argparse
import json
import os
import sys
import time
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
    from uvicorn import run
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from thocung_rag import ThocungRAG, POST_DIR


# ----------------------------- Config -----------------------------

APP_TITLE = "Thocung RAG API"
DEFAULT_PORT = 8001


# ----------------------------- Schemas -----------------------------

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(4, ge=1, le=10)


class RebuildRequest(BaseModel):
    posts_dir: str | None = None


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: list[dict[str, str]]
    retrieval_time_ms: float
    count: int
    model: str
    status: str


# ----------------------------- Global State -----------------------------

rag_engine = None
rag_engine_status = "idle"  # idle | building | ready | error
rag_engine_error = None
rag_start_time = None


def get_rag() -> ThocungRAG:
    """Lazy initialize RAG engine."""
    global rag_engine
    if rag_engine is None:
        rag_engine = ThocungRAG()
    return rag_engine


# ----------------------------- FastAPI App -----------------------------

app = FastAPI(
    title=APP_TITLE,
    version="1.0.0",
    description="RAG API cho website thocung.com"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    """Khởi tạo RAG engine khi server khởi động."""
    global rag_engine_status, rag_engine_error, rag_start_time
    rag_engine_status = "building"
    rag_engine_error = None
    rag_start_time = time.time()
    try:
        get_rag().init()
        rag_engine_status = "ready"
        print(f"[+] RAG engine ready at {time.strftime('%H:%M:%S')}")
    except Exception as e:
        rag_engine_status = "error"
        rag_engine_error = str(e)
        print(f"[!] Lỗi khởi tạo RAG: {e}")


@app.get("/health")
async def health():
    """Trả về trạng thái RAG engine."""
    return {
        "status": "ok",
        "rag_status": rag_engine_status,
        "rag_error": rag_engine_error,
        "rag_start_time": rag_start_time,
        "data_dir": str(POST_DIR)
    }


@app.get("/collections")
async def collections():
    """Liệt kê các collection trong ChromaDB."""
    try:
        client = get_rag()._init_chroma()
        return {"collections": [c.name for c in client.list_collections()]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rebuild", response_model=QueryResponse)
async def rebuild(request: RebuildRequest):
    """Xây dựng lại index từ thư mục bài viết."""
    global rag_engine_status, rag_engine_error

    if rag_engine_status == "building":
        raise HTTPException(status_code=409, detail="Đang xây dựng index")

    rag_engine_status = "building"
    rag_engine_error = None

    try:
        posts_dir = request.posts_dir if request.posts_dir else str(POST_DIR)
        count = get_rag().build_index(posts_dir)
        rag_engine_status = "ready"
        return {
            "question": "RAG index rebuilt",
            "answer": f"Đã cập nhật dữ liệu RAG thành công! Đã index {count} chunks.",
            "sources": [],
            "retrieval_time_ms": 0.0,
            "count": count,
            "model": "sentence-transformers",
            "status": "success"
        }
    except Exception as e:
        rag_engine_status = "error"
        rag_engine_error = str(e)
        raise HTTPException(status_code=500, detail=f"Lỗi rebuild RAG: {e}")


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """Truy vấn RAG và trả về câu trả lời."""
    try:
        # Debug: print the request
        print(f"DEBUG: Received question: {request.question!r}, top_k: {request.top_k!r}")
        print(f"DEBUG: Question bytes: {request.question.encode('utf-8')!r}")
        result = get_rag().generate_answer(request.question, request.top_k)
        print(f"DEBUG: Generated answer successfully")
        return {
            "question": request.question,
            "answer": result["answer"],
            "sources": result["sources"],
            "retrieval_time_ms": result["retrieval_time_ms"],
            "count": result["count"],
            "model": "sentence-transformers",
            "status": "success"
        }
    except Exception as e:
        print(f"DEBUG: Error in query endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Lỗi query RAG: {e}")


@app.get("/")
async def root():
    return {"message": "Thocung RAG API đang chạy", "docs": "/docs"}


# ----------------------------- CLI -----------------------------

def main():
    parser = argparse.ArgumentParser(description="FastAPI server cho RAG thocung.com")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-auto-build", action="store_true", help="Không auto-build index khi khởi động")
    args = parser.parse_args()

    if not FASTAPI_AVAILABLE:
        print("[!] FastAPI không khả dụng. Vui lòng cài đặt dependencies trong /RAG")
        return

    if not args.no_auto_build:
        try:
            print("[+] Đang xây dựng index RAG từ /data/post/...")
            get_rag().build_index(str(POST_DIR))
            print("[+] Đã xây dựng index thành công")
        except Exception as e:
            print(f"[!] Không thể auto-build: {e}")

    run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
