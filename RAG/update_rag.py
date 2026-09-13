"""
# update_rag.py — Script cập nhật/rebuild dữ liệu RAG
# Chạy để đồng bộ lại index khi thay đổi dữ liệu trong /data/post/

Cú pháp:
    python update_rag.py                  # Rebuild index từ /data/post/
    python update_rag.py --posts-dir /path/to/posts
    python update_rag.py --status         # Kiểm tra trạng thái index hiện tại
    python update_rag.py --test "Câu hỏi"  # Test query nhanh

Tích hợp với web:
    Node.js server.js sẽ gọi endpoint này qua API để cập nhật.
    Hoặc chạy thủ công khi thay đổi dữ liệu.

Workflow cập nhật dữ liệu:
    1. Thêm/sửa bài viết trong /data/post/ (qua UI admin hoặc trực tiếp)
    2. Chạy script này để rebuild index (hoặc gọi API /api/rag/rebuild từ admin UI)
    3. RAG sẽ dùng dữ liệu mới cho các truy vấn kế tiếp
"""

import argparse
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure we can import thocung_rag
sys.path.insert(0, str(Path(__file__).parent))
from thocung_rag import (
    ThocungRAG,
    POST_DIR,
    CHROMA_DIR,
    COLLECTION_NAME,
)


def check_status(rag: ThocungRAG):
    """Kiểm tra trạng thái index hiện tại."""
    print("=== TRẠNG THÁI INDEX RAG ===\n")

    try:
        rag.init()
    except Exception as e:
        print(f"[!] Lỗi khởi tạo: {e}")
        return

    try:
        count = rag.collection.count()
        print(f"Collection: {COLLECTION_NAME}")
        print(f"Số chunks hiện tại: {count}")
        print(f"Chroma dir: {CHROMA_DIR}")
        print(f"Data dir: {POST_DIR}")

        # List posts
        posts = list(POST_DIR.glob("*.html")) if POST_DIR.exists() else []
        print(f"\nBài viết trong /data/post/: {len(posts)}")

        for p in sorted(posts):
            size = p.stat().st_size
            print(f"  - {p.name} ({size} bytes)")

        # Show sample of indexed data
        if count > 0:
            print(f"\nMẫu chunks đã index (3 mẫu đầu):")
            sample = rag.collection.peek(limit=3)
            for i, (doc_id, content, meta) in enumerate(zip(
                sample.get("ids", []),
                sample.get("documents", []),
                sample.get("metadatas", [])
            ), 1):
                title = meta.get("title", "N/A")
                snippet = content[:120] + "..." if len(content) > 120 else content
                print(f"\n  [{i}] ID: {doc_id}")
                print(f"      Title: {title}")
                print(f"      Content: {snippet}")

    except Exception as e:
        print(f"[!] Lỗi khi đọc status: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Cập nhật/rebuild RAG index từ /data/post/"
    )
    parser.add_argument(
        "--posts-dir",
        type=str,
        default=str(POST_DIR),
        help="Thư mục chứa bài viết HTML (mặc định: /data/post/)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Kiểm tra trạng thái index hiện tại"
    )
    parser.add_argument(
        "--test",
        type=str,
        default=None,
        help="Test query nhanh"
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Chỉ chạy status/test, không rebuild"
    )

    args = parser.parse_args()

    rag = ThocungRAG()

    if args.status or args.no_build:
        check_status(rag)
    else:
        print("=== CẬP NHẬT INDEX RAG ===\n")
        count = rag.build_index(args.posts_dir)
        print(f"\n[+] Hoàn tất! Đã index {count} chunks")

        if args.test:
            print(f"\n=== TEST QUERY: \"{args.test}\" ===\n")
            result = rag.generate_answer(args.test)
            print(f"Câu trả lời:\n{result['answer']}\n")
            print(f"Nguồn ({len(result['sources'])}):")
            for s in result["sources"]:
                print(f"  - {s.get('title', 'N/A')}")


if __name__ == "__main__":
    main()
