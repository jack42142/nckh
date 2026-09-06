"""
# ============================================================
# Credit: Code được hỗ trợ bởi Claude Code (Anthropic)
# ============================================================

"""
embed.py — Tạo embedding và lưu vào ChromaDB

Mô hình mặc định: sentence-transformers/all-MiniLM-L6-v2
- 384-dim, ~80MB, chạy được trên CPU
- Đủ tốt cho RAG tiếng Anh (tiếng Việt có thể yếu hơn)

Nếu muốn chất lượng tốt hơn cho tiếng Việt, có thể đổi sang:
- keepitreal/vietnamese-sbert (chuyên cho tiếng Việt)
- intfloat/multilingual-e5-base (đa ngôn ngữ)

Cú pháp:
    python embed.py --input genshin_chunks_en.json --collection genshin_lore_en
    python embed.py --input genshin_chunks_en.json --collection genshin_lore_en --rebuild
    python embed.py --model keepitreal/vietnamese-sbert --input genshin_chunks_vi.json --collection genshin_lore_vi
"""

import argparse
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Tắt cảnh báo của huggingface & telemetry
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Set model cache vào thư mục ./model để dùng chung với model Qwen
os.environ.setdefault(
    "HF_HOME", str(Path(__file__).parent / "model" / "hf_cache")
)
os.environ.setdefault(
    "SENTENCE_TRANSFORMERS_HOME",
    str(Path(__file__).parent / "model" / "sbert_cache"),
)

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_VI_MODEL = "keepitreal/vietnamese-sbert"
CHROMA_DIR = "./chroma_data"


# ----------------------------- EMBEDDER -----------------------------


class Embedder:
    """Bao bọc SentenceTransformer với cache để tránh load lại."""

    _instances: dict[str, "Embedder"] = {}

    def __init__(self, model_name: str):
        print(f"[+] Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        # Đảm bảo model sống trên CPU nếu không có CUDA
        try:
            import torch

            if not torch.cuda.is_available():
                self.model = self.model.to("cpu")
        except ImportError:
            pass
        self.dim = self.model.get_sentence_embedding_dimension()
        print(f"    -> dim={self.dim}, device={self.model.device}")

    @classmethod
    def get(cls, model_name: str) -> "Embedder":
        if model_name not in cls._instances:
            cls._instances[model_name] = cls(model_name)
        return cls._instances[model_name]

    def encode(self, texts: list[str], batch_size: int = 32, show_progress: bool = True):
        """Encode batch các text. Tự động normalize để dùng cosine similarity."""
        return self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )


# ----------------------------- CHROMA -----------------------------


def get_chroma_client(chroma_dir: str = CHROMA_DIR):
    """Tạo PersistentClient để giữ data qua các lần chạy."""
    Path(chroma_dir).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=chroma_dir, settings=Settings(anonymized_telemetry=False)
    )


def get_or_create_collection(client, name: str, dim: int):
    """Lấy collection. Nếu chưa có thì tạo với cosine similarity."""
    existing = {c.name for c in client.list_collections()}
    if name in existing:
        print(f"[+] Collection '{name}' đã tồn tại, sẽ giữ nguyên (dùng --rebuild để xoá).")
        return client.get_collection(name)
    print(f"[+] Tạo mới collection '{name}' (dim={dim})")
    return client.create_collection(
        name=name,
        metadata={
            "hnsw:space": "cosine",
            "hnsw:construction_ef": 100,
            "hnsw:M": 16,
        },
    )


def reset_collection(client, name: str):
    """Xoá collection để xây lại từ đầu."""
    if name in {c.name for c in client.list_collections()}:
        client.delete_collection(name)
        print(f"[+] Đã xoá collection '{name}'")


# ----------------------------- INGEST -----------------------------


def ingest_chunks(
    chunks_path: str,
    collection_name: str,
    model_name: str = DEFAULT_MODEL,
    chroma_dir: str = CHROMA_DIR,
    rebuild: bool = False,
    batch_size: int = 64,
):
    """Đọc chunks JSON, sinh embedding, lưu vào Chroma collection."""
    chunks = json.loads(Path(chunks_path).read_text(encoding="utf-8"))
    if not chunks:
        print("[!] File input rỗng, dừng.")
        return
    print(f"[+] Đọc {len(chunks)} chunks từ {chunks_path}")

    embedder = Embedder.get(model_name)
    client = get_chroma_client(chroma_dir)

    if rebuild:
        reset_collection(client, collection_name)
    collection = get_or_create_collection(client, collection_name, embedder.dim)

    # Bỏ qua những id đã có (tránh duplicate khi chạy lại)
    existing_ids = set()
    try:
        existing_ids = set(collection.get(include=[]).get("ids", []))
        if existing_ids:
            print(f"[+] Đã có {len(existing_ids)} chunks trong collection, sẽ skip.")
    except Exception:
        pass

    pending = [c for c in chunks if c["id"] not in existing_ids]
    if not pending:
        print("[+] Không có chunk mới, kết thúc.")
        return

    # Encode & add theo batch
    for i in tqdm(range(0, len(pending), batch_size), desc="Embedding+add"):
        batch = pending[i : i + batch_size]
        texts = [c["content"] for c in batch]
        embeddings = embedder.encode(texts, batch_size=batch_size, show_progress=False)

        ids = [c["id"] for c in batch]
        # Metadata của Chroma chỉ chấp nhận int/float/str/bool → ép kiểu
        metadatas = []
        for c in batch:
            md = {}
            for k, v in c["metadata"].items():
                if v in (None, "", []):
                    continue
                if isinstance(v, (int, float, str, bool)):
                    md[k] = v
                else:
                    md[k] = str(v)
            metadatas.append(md)

        collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
        )

    final_count = collection.count()
    print(f"\n[+] Hoàn tất. Collection '{collection_name}' hiện có {final_count} vectors.")


# ----------------------------- QUERY -----------------------------


def query(
    question: str,
    collection_name: str,
    model_name: str = DEFAULT_MODEL,
    chroma_dir: str = CHROMA_DIR,
    top_k: int = 4,
    where: dict | None = None,
):
    """Truy vấn collection, trả về list kết quả (content, metadata, score)."""
    embedder = Embedder.get(model_name)
    client = get_chroma_client(chroma_dir)
    collection = client.get_collection(collection_name)

    q_emb = embedder.encode([question], show_progress=False)
    res = collection.query(
        query_embeddings=q_emb.tolist(),
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    out = []
    for i in range(len(res["ids"][0])):
        out.append(
            {
                "id": res["ids"][0][i],
                "content": res["documents"][0][i],
                "metadata": res["metadatas"][0][i],
                "score": 1 - res["distances"][0][i],  # cosine similarity
            }
        )
    return out


# ----------------------------- CLI -----------------------------


def main():
    parser = argparse.ArgumentParser(description="Embed + ingest + query RAG")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Embed chunks và lưu vào Chroma")
    p_ingest.add_argument("--input", required=True)
    p_ingest.add_argument("--collection", required=True)
    p_ingest.add_argument("--model", default=DEFAULT_MODEL)
    p_ingest.add_argument("--chroma-dir", default=CHROMA_DIR)
    p_ingest.add_argument("--rebuild", action="store_true")
    p_ingest.add_argument("--batch-size", type=int, default=64)

    p_query = sub.add_parser("query", help="Truy vấn collection")
    p_query.add_argument("--question", required=True)
    p_query.add_argument("--collection", required=True)
    p_query.add_argument("--model", default=DEFAULT_MODEL)
    p_query.add_argument("--chroma-dir", default=CHROMA_DIR)
    p_query.add_argument("--top-k", type=int, default=4)
    p_query.add_argument("--where", help="Chroma filter, dạng JSON: '{\"element\": \"Pyro\"}'")

    args = parser.parse_args()

    if args.cmd == "ingest":
        ingest_chunks(
            chunks_path=args.input,
            collection_name=args.collection,
            model_name=args.model,
            chroma_dir=args.chroma_dir,
            rebuild=args.rebuild,
            batch_size=args.batch_size,
        )
    elif args.cmd == "query":
        where = json.loads(args.where) if args.where else None
        results = query(
            question=args.question,
            collection_name=args.collection,
            model_name=args.model,
            chroma_dir=args.chroma_dir,
            top_k=args.top_k,
            where=where,
        )
        print(f"\n=== Top {len(results)} kết quả cho: \"{args.question}\" ===\n")
        for i, r in enumerate(results, 1):
            print(f"--- [{i}] {r['id']} (score={r['score']:.3f}) ---")
            md = r["metadata"]
            for k in ("title", "section", "category", "element", "region"):
                if md.get(k):
                    print(f"  {k}: {md[k]}")
            print(f"  url: {md.get('url', '')}")
            snippet = r["content"][:280].replace("\n", " ")
            print(f"  content: {snippet}{'...' if len(r['content']) > 280 else ''}")
            print()


if __name__ == "__main__":
    main()
