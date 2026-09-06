"""
# ============================================================
# Credit: Code được hỗ trợ bởi Claude Code (Anthropic)
# ============================================================

"""
app.py — FastAPI RAG Query Server cho Genshin Impact Lore

Cung cấp REST API để hỏi đáp về Lore Genshin Impact từ vector DB,
có tích hợp LLM (Qwen3.5-2B local) để sinh câu trả lời tự nhiên.

Cú pháp:
    python app.py                          # chạy server port 8000
    python app.py --no-llm                 # tắt load LLM (chỉ retrieval)
    python app.py --host 0.0.0.0 --port 8001

Endpoints:
    GET  /health                           # health check (kèm LLM status)
    POST /query                            # retrieval-only (raw chunks)
    POST /search                           # tìm kiếm thô
    POST /generate                         # RAG + LLM: trả câu trả lời tự nhiên
    GET  /collections                      # list collections hiện có
"""

import json
import time
import argparse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import embed.py functions
from embed import (
    get_chroma_client,
    query,
    DEFAULT_MODEL,
    CHROMA_DIR,
)

# Import generator (LLM)
from generate import (
    Generator,
    build_context,
    should_refuse,
    DEFAULT_LLM,
    SYSTEM_PROMPT,
    REFUSE_SYSTEM,
    USER_TEMPLATE,
)

# ----------------------------- CONFIG -----------------------------

APP_TITLE = "Genshin Impact Lore RAG API"
APP_VERSION = "1.0.0"

# Global state cho LLM
_llm: Generator | None = None
_llm_load_error: str | None = None
_no_llm: bool = False  # set ngay dưới từ CLI args (trước khi FastAPI load)

# ----------------------------- SCHEMAS -----------------------------


class QueryRequest(BaseModel):
    question: str
    top_k: int = 4
    filters: dict[str, Any] | None = None
    model: str = DEFAULT_MODEL
    collection: str = "genshin_lore"


class SearchRequest(BaseModel):
    text: str
    top_k: int = 5
    filters: dict[str, Any] | None = None
    model: str = DEFAULT_MODEL
    collection: str = "genshin_lore"


class GenerateRequest(BaseModel):
    question: str
    top_k: int = 6
    filters: dict[str, Any] | None = None
    collection: str = "genshin_lore"
    max_new_tokens: int = 400
    temperature: float = 0.5


class QueryResponse(BaseModel):
    question: str
    results: list[dict[str, Any]]
    execution_time_ms: float
    model: str


class GenerateResponse(BaseModel):
    question: str
    answer: str
    refused: bool
    sources: list[dict[str, Any]]
    retrieval_time_ms: float
    generation_time_ms: float
    total_time_ms: float
    model: str
    top_score: float


class HealthResponse(BaseModel):
    status: str
    version: str
    chroma_dir: str
    collections: list[str]
    llm_loaded: bool
    llm_model: str | None
    llm_error: str | None


# ----------------------------- APP -----------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load LLM ngay khi server khởi động (nếu không tắt bằng --no-llm)."""
    global _llm, _llm_load_error
    if _llm is None and not _no_llm:
        try:
            print(f"[+] Đang load LLM (lần đầu)...")
            _llm = Generator.get(DEFAULT_LLM)
            _llm_load_error = None
        except Exception as e:
            _llm_load_error = str(e)
            print(f"[!] Lỗi load LLM: {e}")
            print(f"[!] /generate sẽ trả lỗi cho đến khi fix.")
    yield
    # Cleanup nếu cần (giữ model trong memory để tái sử dụng)


# ----------------------------- CLI PARSE (phải chạy trước khi tạo FastAPI app) -----------------------------

# Parse argv 1 lần ở module level để các flag có hiệu lực trước khi lifespan chạy.
# (uvicorn.run("app:app", ...) sẽ re-import module này, nhưng _cli_args đã có sẵn)
_cli_parser = argparse.ArgumentParser(description="Chạy FastAPI server cho RAG Genshin", add_help=False)
_cli_parser.add_argument("--host", default="127.0.0.1")
_cli_parser.add_argument("--port", type=int, default=8000)
_cli_parser.add_argument("--reload", action="store_true")
_cli_parser.add_argument("--no-llm", action="store_true")
_cli_args, _unknown = _cli_parser.parse_known_args()
_no_llm = _cli_args.no_llm


def main():
    print(f"[+] Khởi động {APP_TITLE} v{APP_VERSION}")
    print(f"[+] Chroma dir: {CHROMA_DIR}")
    print(f"[+] Collections: {list_collections()}")
    if not _no_llm:
        print(f"[+] LLM: Qwen3.5-2B (sẽ load ngay lúc khởi động)")
    else:
        print(f"[+] LLM: DISABLED (--no-llm)")
    print(f"[+] Listening on http://{_cli_args.host}:{_cli_args.port}")
    print(f"[+] API docs: http://{_cli_args.host}:{_cli_args.port}/docs")

    uvicorn.run("app:app", host=_cli_args.host, port=_cli_args.port, reload=_cli_args.reload, log_level="info")


app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description="RAG Query API cho Genshin Impact Lore (từ Fandom Wiki)",
    lifespan=lifespan,
)

# CORS cho web interface (localhost:3000, file://)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------- HELPERS -----------------------------


def list_collections() -> list[str]:
    client = get_chroma_client(CHROMA_DIR)
    return [c.name for c in client.list_collections()]


def format_result(r: dict) -> dict:
    """Chuẩn hóa response format cho frontend."""
    md = r["metadata"]
    return {
        "id": r["id"],
        "score": round(r["score"], 4),
        "title": md.get("title", ""),
        "section": md.get("section", ""),
        "category": md.get("category", ""),
        "element": md.get("element", ""),
        "region": md.get("region", ""),
        "weapon_type": md.get("weapon_type", ""),
        "rarity": md.get("rarity", ""),
        "url": md.get("url", ""),
        "content": r["content"],
        "content_preview": r["content"][:300] + ("..." if len(r["content"]) > 300 else ""),
    }


def get_llm() -> Generator:
    """Lấy LLM, raise nếu chưa load được."""
    if _llm is None:
        raise HTTPException(
            status_code=503,
            detail=f"LLM chưa sẵn sàng: {_llm_load_error or 'chưa load'}",
        )
    return _llm


# ----------------------------- ROUTES -----------------------------


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        chroma_dir=CHROMA_DIR,
        collections=list_collections(),
        llm_loaded=_llm is not None,
        llm_model="Qwen3.5-2B" if _llm else None,
        llm_error=_llm_load_error,
    )


@app.get("/collections")
async def collections():
    return {"collections": list_collections()}


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest):
    start = time.perf_counter()
    # Tách collection ra khỏi filters (không mutate request)
    filters = dict(req.filters or {})
    collection_name = filters.pop("collection", req.collection)
    where = filters if filters else None
    try:
        results = query(
            question=req.question,
            collection_name=collection_name,
            model_name=req.model,
            top_k=req.top_k,
            where=where,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query error: {e}")

    elapsed_ms = (time.perf_counter() - start) * 1000
    return QueryResponse(
        question=req.question,
        results=[format_result(r) for r in results],
        execution_time_ms=round(elapsed_ms, 2),
        model=req.model,
    )


@app.post("/search")
async def search_endpoint(req: SearchRequest):
    """Tìm kiếm thô, trả về full content."""
    filters = dict(req.filters or {})
    collection_name = filters.pop("collection", req.collection)
    where = filters if filters else None
    try:
        results = query(
            question=req.text,
            collection_name=collection_name,
            model_name=req.model,
            top_k=req.top_k,
            where=where,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {e}")

    return {
        "query": req.text,
        "results": [format_result(r) for r in results],
        "total": len(results),
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate_endpoint(req: GenerateRequest):
    """RAG + LLM: sinh câu trả lời tự nhiên từ retrieved chunks."""
    total_start = time.perf_counter()

    # 1. Retrieve top-K chunks
    filters = dict(req.filters or {})
    collection_name = filters.pop("collection", req.collection)
    where = filters if filters else None

    retrieval_start = time.perf_counter()
    try:
        chunks = query(
            question=req.question,
            collection_name=collection_name,
            top_k=req.top_k,
            where=where,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query error: {e}")
    retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

    top_score = chunks[0]["score"] if chunks else 0.0

    # 2. Decide: refuse vs generate
    refused = should_refuse(chunks)

    if refused:
        # Ngoài phạm vi → dùng refuse prompt
        system = REFUSE_SYSTEM
        user = f"Câu hỏi: {req.question}\nTrả lời:"
    else:
        # Trong phạm vi → dùng context thực
        context = build_context(chunks)
        system = SYSTEM_PROMPT
        user = USER_TEMPLATE.format(context=context, question=req.question)

    # 3. Generate
    gen_start = time.perf_counter()
    try:
        llm = get_llm()
        answer, ntok, gen_secs = llm.generate(
            system=system,
            user=user,
            max_new_tokens=req.max_new_tokens,
            temperature=req.temperature,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation error: {e}")
    generation_ms = (time.perf_counter() - gen_start) * 1000

    total_ms = (time.perf_counter() - total_start) * 1000

    return GenerateResponse(
        question=req.question,
        answer=answer,
        refused=refused,
        sources=[format_result(r) for r in chunks],
        retrieval_time_ms=round(retrieval_ms, 2),
        generation_time_ms=round(generation_ms, 2),
        total_time_ms=round(total_ms, 2),
        model="Qwen3.5-2B",
        top_score=round(top_score, 4),
    )


# ----------------------------- STATIC FILES (Web UI) -----------------------------

# Phục vụ index.html ở root (file đặt cùng thư mục với app.py)
html_file = Path(__file__).parent / "index.html"


@app.get("/", include_in_schema=False)
async def root_index():
    if html_file.exists():
        return FileResponse(html_file)
    return {"message": "Chưa tìm thấy index.html. Đặt file cùng thư mục với app.py"}


@app.get("/index.html", include_in_schema=False)
async def html_index():
    if html_file.exists():
        return FileResponse(html_file)
    return {"message": "Chưa tìm thấy index.html"}


# Nếu có thư mục static (HTML/JS/CSS) thì phục vụ
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/ui")
    async def ui_index():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Web UI chưa được cài đặt. Tạo file static/index.html"}


if __name__ == "__main__":
    main()