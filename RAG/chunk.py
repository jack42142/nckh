"""
# ============================================================
# Credit: Code được hỗ trợ bởi Claude Code (Anthropic)
# ============================================================

"""
chunk.py — Smart chunking cho RAG

Cải tiến so với chunk_by_sections trong crawl.py:
- Cắt theo token count (tiktoken) thay vì chỉ theo heading
- Mỗi chunk 300-500 tokens, overlap 80 tokens
- Section ngắn (<300 tokens) được gộp với section kế tiếp
- Section dài (>500 tokens) được cắt nhỏ có overlap
- Giữ đầy đủ metadata (title, section, category, element, region, weapon_type, rarity, url)
- Hỗ trợ cả dữ liệu mới (từ crawl_enhanced.py) và dữ liệu cũ (genshin_rag_knowledge.json)

Cú pháp:
    python chunk.py --input genshin_rag_pages_en.json --output genshin_chunks_en.json
    python chunk.py --input genshin_rag_knowledge.json --output genshin_chunks_legacy.json --legacy
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import tiktoken

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ----------------------------- CONFIG -----------------------------

# Mô hình embedding dùng MiniLM (384-dim) → max 512 token.
# Chia nhỏ hơn một chút để an toàn với context.
TARGET_TOKENS = 400        # Kích thước mục tiêu mỗi chunk
MAX_TOKENS = 512           # Không vượt quá
MIN_TOKENS = 50            # Bỏ chunk quá ngắn
OVERLAP_TOKENS = 80        # Overlap giữa các chunk liên tiếp
SECTION_MIN_TOKENS = 100   # Section ngắn hơn sẽ gộp vào section kế

# Tên encoding dùng cl100k_base (tương thích GPT-4/MiniLM)
ENCODING_NAME = "cl100k_base"


def get_encoder():
    """Trả về tiktoken encoder. Lazy-load để import nhanh."""
    return tiktoken.get_encoding(ENCODING_NAME)


# ----------------------------- TOKEN UTILS -----------------------------


def count_tokens(text: str, enc) -> int:
    return len(enc.encode(text, disallowed_special=()))


def split_text_by_tokens(text: str, enc, max_tokens: int, overlap: int) -> list[str]:
    """Cắt text thành các chunk có overlap, theo token."""
    tokens = enc.encode(text, disallowed_special=())
    if len(tokens) <= max_tokens:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = enc.decode(chunk_tokens)
        if chunk_text.strip():
            chunks.append(chunk_text)
        if end >= len(tokens):
            break
        start = end - overlap  # tiến tới nhưng giữ overlap
    return chunks


# ----------------------------- SECTION PARSING -----------------------------

HEADING_RE = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$", re.MULTILINE)


def split_sections(text: str) -> list[tuple[str, str]]:
    """Tách text thành [(heading, content), ...]. Heading đầu = 'Overview' nếu không có."""
    sections = []
    current_heading = "Overview"
    current_lines: list[str] = []

    for line in text.split("\n"):
        m = HEADING_RE.match(line)
        if m:
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = m.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    return sections


# ----------------------------- CHUNKING -----------------------------


def chunk_page(
    title: str,
    clean_text: str,
    category: str,
    metadata: dict | None,
    url: str,
    enc,
) -> list[dict]:
    """Chunk một page thành list các chunk với metadata đầy đủ."""
    metadata = metadata or {}
    sections = split_sections(clean_text)
    chunks = []

    # Gộp section ngắn vào section kế tiếp
    merged: list[tuple[str, str]] = []
    buf_heading = None
    buf_content: list[str] = []

    for heading, content in sections:
        if count_tokens(content, enc) < SECTION_MIN_TOKENS:
            if buf_heading is None:
                buf_heading = heading
            buf_content.append(f"## {heading}\n{content}")
            continue
        # flush buffer nếu có
        if buf_content:
            merged.append((buf_heading or "Intro", "\n\n".join(buf_content)))
            buf_heading = None
            buf_content = []
        merged.append((heading, content))
    if buf_content:
        merged.append((buf_heading or "Intro", "\n\n".join(buf_content)))

    for heading, content in merged:
        if not content.strip():
            continue
        # Thêm context tiêu đề vào content
        # Tránh duplicate nếu content đã bắt đầu bằng "[Title - Section]"
        content_stripped = content.lstrip()
        if content_stripped.startswith(f"[{title}"):
            contexted = content
        else:
            contexted = f"[{title} — {heading}]\n{content}"
        piece_list = split_text_by_tokens(contexted, enc, MAX_TOKENS, OVERLAP_TOKENS)

        for i, piece in enumerate(piece_list):
            if count_tokens(piece, enc) < MIN_TOKENS:
                continue
            chunk_id = unique_id(title, heading, i, piece)
            chunks.append(
                {
                    "id": chunk_id,
                    "content": piece,
                    "metadata": {
                        "title": title,
                        "section": heading,
                        "category": category,
                        "element": metadata.get("element", ""),
                        "region": metadata.get("region", ""),
                        "weapon_type": metadata.get("weapon_type", ""),
                        "rarity": metadata.get("rarity", ""),
                        "affiliation": metadata.get("affiliation", ""),
                        "url": url,
                        "source": "Genshin Impact Wiki",
                        "chunk_index": i,
                        "token_count": count_tokens(piece, enc),
                    },
                }
            )

    return chunks


def slugify(s: str) -> str:
    """Tạo slug an toàn cho id từ chuỗi (hỗ trợ tiếng Việt có dấu)."""
    s = re.sub(r"[^\w\s-]", "", s.lower())
    return re.sub(r"[\s-]+", "_", s).strip("_")[:40]


def unique_id(title: str, heading: str, idx: int, content: str) -> str:
    """Tạo id DUY NHẤT bằng cách thêm hash từ content."""
    base = f"{slugify(title)}__{slugify(heading)}__{idx}"
    # Hash 8 ký tự đầu của content để phân biệt các trang trùng heading
    h = hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()[:8]
    return f"{base}__{h}"


# ----------------------------- LOADERS -----------------------------


def load_enhanced(path: str, enc) -> list[dict]:
    """Load file output từ crawl_enhanced.py."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    all_chunks = []
    for page in data:
        all_chunks.extend(
            chunk_page(
                title=page["title"],
                clean_text=page["clean_text"],
                category=page.get("source_category", ""),
                metadata=page.get("infobox", {}),
                url=page.get("url", ""),
                enc=enc,
            )
        )
    return all_chunks


def load_legacy(path: str, enc) -> list[dict]:
    """Load file genshin_rag_knowledge.json cũ (chỉ có content + metadata)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    all_chunks = []
    for item in data:
        content = item.get("content", "")
        meta = item.get("metadata", {})
        title = meta.get("title", "unknown")
        category = meta.get("category", "")
        url = meta.get("url", "")
        # Re-chunk nội dung cũ với chiến lược mới
        all_chunks.extend(
            chunk_page(
                title=title,
                clean_text=content,
                category=category,
                metadata={},
                url=url,
                enc=enc,
            )
        )
    return all_chunks


# ----------------------------- MAIN -----------------------------


def main():
    parser = argparse.ArgumentParser(description="Chunk dữ liệu RAG Genshin Impact")
    parser.add_argument("--input", required=True, help="File JSON đầu vào")
    parser.add_argument("--output", required=True, help="File JSON đầu ra")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Đọc file format cũ (genshin_rag_knowledge.json)",
    )
    args = parser.parse_args()

    enc = get_encoder()
    print(f"[+] Đang đọc {args.input} ...")

    if args.legacy:
        chunks = load_legacy(args.input, enc)
    else:
        chunks = load_enhanced(args.input, enc)

    # Thống kê
    token_counts = [c["metadata"]["token_count"] for c in chunks]
    print(f"\n=== THỐNG KÊ CHUNKING ===")
    print(f"  Tổng số chunk: {len(chunks)}")
    if token_counts:
        print(f"  Token trung bình: {sum(token_counts) // len(token_counts)}")
        print(f"  Token nhỏ nhất: {min(token_counts)}")
        print(f"  Token lớn nhất: {max(token_counts)}")
        print(
            f"  Chunk trong khoảng [{MIN_TOKENS}, {MAX_TOKENS}]: "
            f"{sum(1 for t in token_counts if MIN_TOKENS <= t <= MAX_TOKENS)}/{len(token_counts)}"
        )

    out_path = Path(args.output)
    out_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[+] Đã lưu {len(chunks)} chunk vào {out_path}")


if __name__ == "__main__":
    main()
