"""
# thocung_rag.py — RAG engine cho website thocung.com
# Index dữ liệu từ /data/post/*.html và trả lời câu hỏi bằng RAG

Usage:
    python thocung_rag.py --build    # Xây dựng lại index từ /data/post/
    python thocung_rag.py --query "Câu hỏi..."  # Truy vấn nhanh
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Windows encoding fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Config
DATA_DIR = Path(__file__).parent.parent / "data"
POST_DIR = DATA_DIR / "post"
CHROMA_DIR = Path(__file__).parent / "chroma_data"
COLLECTION_NAME = "thocung_articles"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
VIETMODEL = "keepitreal/vietnamese-sbert"
MAX_CHARS = 8000  # Max chars per chunk

# Domain keywords for ancestor worship (thờ cúng gia tiên)
DOMAIN_KEYWORDS = {
    'thờ cúng', 'gia tiên', 'tổ tiên', 'lễ', 'dâng hương', 'bài văn khấn',
    'bàn thờ', 'phong thủy', 'nghi lễ', 'đạo hiếu', 'âm lịch', 'may mắn',
    'bình an', 'tích cực', 'sự thành kính', 'linh hồn', 'chân thành',
}

# Try to import optional dependencies
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


# Domain keywords for ancestor worship (thờ cúng gia tiên)
DOMAIN_KEYWORDS = {
    'thờ cúng', 'gia tiên', 'tổ tiên', 'lễ', 'dâng hương', 'bài văn khấn',
    'bàn thờ', 'phong thủy', 'nghi lễ', 'đạo hiếu', 'âm lịch', 'may mắn',
    'bình an', 'tích cực', 'sự thành kính', 'linh hồn', 'chân thành',
}


def is_domain_related(question: str) -> bool:
    """Check if the question is likely related to the ancestor worship domain."""
    question_lower = question.lower()
    # Check if any domain keyword appears in the question
    for keyword in DOMAIN_KEYWORDS:
        if keyword in question_lower:
            return True
    return False


# ----------------------------- HTML Parser -----------------------------

def extract_text_from_html(html_content: str) -> dict[str, str]:
    """
    Extract title, category, date, and article content from HTML.
    Returns dict with: title, category, date, content
    """
    # Extract title
    title_match = re.search(r'<title>([^<]+)</title>', html_content)
    title = title_match.group(1).strip() if title_match else "Không có tiêu đề"

    # Extract category
    category_match = re.search(r'<meta name="category" content="([^"]+)"', html_content)
    category = category_match.group(1).strip() if category_match else "Khác"

    # Extract date
    date_match = re.search(r'<meta name="date" content="([^"]+)"', html_content)
    date = date_match.group(1).strip() if date_match else ""

    # Extract article content (between <article> tags)
    article_match = re.search(r'<article[^>]*>(.*?)</article>', html_content, re.DOTALL)
    content = ""
    if article_match:
        article_html = article_match.group(1)
        # Remove script and style tags
        article_html = re.sub(r'<script[^>]*>.*?</script>', '', article_html, flags=re.DOTALL | re.IGNORECASE)
        article_html = re.sub(r'<style[^>]*>.*?</style>', '', article_html, flags=re.DOTALL | re.IGNORECASE)
        # Remove data-path-to-node attributes
        article_html = re.sub(r' data-path-to-node="[^"]*"', '', article_html)
        # Remove citation-related spans
        article_html = re.sub(r'<span class="citation[^"]*"[^>]*>.*?</span>', '', article_html, flags=re.DOTALL)
        # Parse HTML to text
        content = html_to_text(article_html)

    return {
        "title": title,
        "category": category,
        "date": date,
        "content": content
    }


def html_to_text(html: str) -> str:
    """Convert HTML to plain text, preserving structure for chunking."""
    # Replace closing tags with newlines where appropriate
    text = html

    # Handle headings
    text = re.sub(r'</h[1-6]>', r'\n\n', text)
    text = re.sub(r'<h[1-6][^>]*>', '', text)

    # Handle list items
    text = re.sub(r'</li>', r'\n', text)
    text = re.sub(r'<li[^>]*>', '', text)

    # Handle table cells
    text = re.sub(r'</td>', r'\t', text)
    text = re.sub(r'</tr>', r'\n', text)
    text = re.sub(r'<t[dh][^>]*>', '', text)
    text = re.sub(r'<table[^>]*>', '', text)
    text = re.sub(r'</table>', '\n', text)

    # Handle blockquote
    text = re.sub(r'</blockquote>', r'\n', text)
    text = re.sub(r'<blockquote[^>]*>', '', text)

    # Remove other tags
    text = re.sub(r'<[^>]+>', ' ', text)

    # Unescape HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')

    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)

    return text.strip()


def split_into_chunks(text: str, title: str, category: str, max_chars: int = MAX_CHARS) -> list[dict]:
    """Split text into chunks for indexing. Each chunk ~500-800 chars."""
    if not text.strip():
        return []

    chunks = []
    # Split by sections (marked by \\n\\n or \\n)
    sections = re.split(r'\n\s*\n+', text)

    current_chunk = []
    current_len = 0
    chunk_idx = 0

    for section in sections:
        section = section.strip()
        if not section:
            continue

        section_len = len(section)

        if current_len + section_len > max_chars and current_chunk:
            # Save current chunk
            chunk_text = '\n\n'.join(current_chunk)
            chunk_id = f"{slugify(title)}__{chunk_idx}__{hash(chunk_text) % 10000}"
            chunks.append({
                "id": chunk_id,
                "content": chunk_text,
                "metadata": {
                    "title": title,
                    "category": category,
                    "source": "thocung_articles",
                    "chunk_index": chunk_idx
                }
            })
            chunk_idx += 1
            current_chunk = [section]
            current_len = section_len
        else:
            current_chunk.append(section)
            current_len += section_len + 2

    # Save last chunk
    if current_chunk:
        chunk_text = '\n\n'.join(current_chunk)
        chunk_id = f"{slugify(title)}__{chunk_idx}__{hash(chunk_text) % 10000}"
        chunks.append({
            "id": chunk_id,
            "content": chunk_text,
            "metadata": {
                "title": title,
                "category": category,
                "source": "thocung_articles",
                "chunk_index": chunk_idx
            }
        })

    return chunks


def slugify(text: str) -> str:
    """Tạo slug từ chuỗi tiếng Việt."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s-]+', '_', text)
    return text[:50].strip('_')


# ----------------------------- RAG Engine -----------------------------

class ThocungRAG:
    """RAG engine cho website thocung.com"""

    def __init__(self, chroma_dir: str = str(CHROMA_DIR), collection_name: str = COLLECTION_NAME):
        self.chroma_dir = chroma_dir
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        self.embedder = None
        self._initialized = False

    def _init_chroma(self):
        """Khởi tạo Chroma client."""
        if not CHROMADB_AVAILABLE:
            raise RuntimeError("chromadb not available")
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(self.chroma_dir),
            settings=Settings(anonymized_telemetry=False)
        )
        return self.client

    def _init_embedder(self):
        """Khởi tạo sentence transformer model."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise RuntimeError("sentence_transformers not available")
        # Try Vietnamese model first, fall back to MiniLM
        for model in [VIETMODEL, EMBEDDING_MODEL]:
            try:
                print(f"[+] Loading embedding model: {model}")
                self.embedder = SentenceTransformer(model)
                print(f"    -> Model loaded successfully")
                return
            except Exception as e:
                print(f"    -> Failed to load {model}: {e}")
                continue
        raise RuntimeError("Could not load any embedding model")

    def init(self):
        """Khởi tạo toàn bộ hệ thống."""
        if self._initialized:
            return

        print("[+] Initializing ThocungRAG...")
        self._init_chroma()
        self._init_embedder()

        # Get or create collection
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
            print(f"[+] Using existing collection: {self.collection_name}")
        except Exception:
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine", "hnsw:construction_ef": 100, "hnsw:M": 16}
            )
            print(f"[+] Created new collection: {self.collection_name}")

        self._initialized = True

    def build_index(self, posts_dir: str = str(POST_DIR)):
        """Xây dựng lại index từ thư mục bài viết."""
        posts_path = Path(posts_dir)
        if not posts_path.exists():
            print(f"[!] Thư mục {posts_dir} không tồn tại")
            return 0

        self.init()

        # Get all HTML files
        html_files = list(posts_path.glob("*.html"))
        print(f"[+] Tìm thấy {len(html_files)} file HTML trong {posts_dir}")

        all_chunks = []
        for html_file in html_files:
            print(f"    Processing: {html_file.name}")
            try:
                html_content = html_file.read_text(encoding="utf-8")
                data = extract_text_from_html(html_content)

                # Parse date from filename to avoid re-fetching
                file_date = ""  # Will use meta date

                chunks = split_into_chunks(
                    data["content"],
                    data["title"],
                    data["category"]
                )

                for chunk in chunks:
                    chunk["metadata"]["date"] = data.get("date", "")
                    chunk["metadata"]["source_file"] = html_file.name

                all_chunks.extend(chunks)
            except Exception as e:
                print(f"    [!] Lỗi đọc {html_file.name}: {e}")

        if not all_chunks:
            print("[!] Không có chunk nào để index")
            return 0

        # Remove existing and create new
        try:
            existing_ids = self.collection.get(include=[]).get("ids", [])
            if existing_ids:
                print(f"[+] Xóa {len(existing_ids)} chunks cũ...")
                self.collection.delete(ids=existing_ids)
        except Exception:
            pass

        # Filter out any chunks with invalid content
        valid_chunks = []
        for c in all_chunks:
            content = c.get("content")
            if content is not None and isinstance(content, str) and content.strip():
                valid_chunks.append(c)
            else:
                print(f"[!] Skipping chunk with invalid content: {c.get('id', 'unknown')}")

        if not valid_chunks:
            print("[!] Không có chunk hợp lệ để index sau khi lọc")
            return 0

        # Add new chunks
        ids = [c["id"] for c in valid_chunks]
        documents = [c["content"] for c in valid_chunks]
        metadatas = [c["metadata"] for c in valid_chunks]
        embeddings = self.embedder.encode(documents, batch_size=32, show_progress_bar=True)

        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings.tolist(),
            metadatas=metadatas
        )

        print(f"[+] Đã index {len(all_chunks)} chunks vào collection {self.collection_name}")
        return len(all_chunks)

    def query(self, question: str, top_k: int = 4) -> dict[str, Any]:
        """Truy vấn RAG và trả về kết quả."""
        if not self._initialized:
            self.init()

        # Ensure question is a valid string
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must be a non-empty string")

        # Encode query
        q_emb = self.embedder.encode([question.strip()], show_progress_bar=False)

        # Query collection
        results = self.collection.query(
            query_embeddings=q_emb.tolist(),
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )

        # Format results
        formatted_results = []
        for i in range(len(results["ids"][0])):
            # Handle potential None values from ChromaDB
            content = results["documents"][0][i]
            if content is None:
                content = ""
            metadata = results["metadatas"][0][i]
            if metadata is None:
                metadata = {}

            score = 1 - results["distances"][0][i]  # cosine similarity
            formatted_results.append({
                "id": results["ids"][0][i],
                "content": content,
                "metadata": metadata,
                "score": round(score, 4)
            })

        return {
            "question": question,
            "results": formatted_results,
            "count": len(formatted_results)
        }

    def generate_answer(self, question: str, top_k: int = 4) -> dict[str, Any]:
        """Truy vấn + tạo câu trả lời (extractive cải tiến để nghe tự nhiên hơn)."""
        import time
        start = time.time()

        # First check if the question is likely related to our domain
        if not is_domain_related(question):
            elapsed = time.time() - start
            return {
                "question": question,
                "answer": "Xin lỗi, tôi chỉ có thể trả lời các câu hỏi liên quan đến thờ cúng gia tiên và chủ đề tôn giáo truyền thống Việt Nam. Bạn có thể thử đặt câu hỏi khác về chủ đề này?",
                "sources": [],
                "retrieval_time_ms": round(elapsed * 1000, 2),
                "count": 0
            }

        query_result = self.query(question, top_k)
        results = query_result["results"]

        # Check if we have any results and if they are relevant enough
        if not results:
            elapsed = time.time() - start
            return {
                "question": question,
                "answer": "Xin lỗi, tôi không tìm thấy thông tin liên quan đến câu hỏi của bạn trong cơ sở dữ liệu.",
                "sources": [],
                "retrieval_time_ms": round(elapsed * 1000, 2),
                "count": 0
            }

        # Check relevance score - if the best match is too low, say we don't know
        # Cosine similarity scores typically range from 0-1, where >0.3 is usually relevant
        best_score = results[0]["score"] if results else 0
        RELEVANCE_THRESHOLD = 0.3  # Adjust this value based on testing

        if best_score < RELEVANCE_THRESHOLD:
            elapsed = time.time() - start
            return {
                "question": question,
                "answer": "Xin lỗi, tôi không có đủ thông tin để trả lời câu hỏi này một cách chính xác. Bạn có thể thử đặt câu hỏi khác liên quan đến chủ đề-thờ cúng gia tiên?",
                "sources": [],
                "retrieval_time_ms": round(elapsed * 1000, 2),
                "count": len(results)
            }

        # Improved extractive answer: select best sentences and make it sound more natural
        answer_parts = []
        sources = []

        # Add introductory phrase to make it sound more conversational
        intro_phrases = [
            "Theo các nguồn tài liệu về temas này, ",
            "Dựa trên thông tin được ghi lại, ",
            "Các bài viết về chủ đề này cho biết rằng, ",
            "Những nghiên cứu và ghi chép cho thấy, "
        ]
        import random
        answer_parts.append(random.choice(intro_phrases))

        # Process each result to extract meaningful information
        for i, r in enumerate(results, 1):
            content = r["content"]
            # Handle None content
            if content is None:
                content = ""

            # Clean up content
            content = content.strip()
            if not content:
                continue

            # Split into sentences and filter out very short ones
            sentences = re.split(r'[.!?]+', content)
            meaningful_sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

            if meaningful_sentences:
                # Take up to 2 best sentences from each source
                selected_sentences = meaningful_sentences[:2]
                for sentence in selected_sentences:
                    # Clean up the sentence
                    sentence = sentence.strip()
                    if sentence and not sentence.endswith(('.', '!', '?')):
                        sentence += '.'
                    answer_parts.append(sentence)

            # Add source
            sources.append({
                "title": r['metadata'].get("title", ""),
                "url": f"#article-{slugify(r['metadata'].get('title', ''))}"
            })

        # Combine answer parts
        if len(answer_parts) > 1:  # We have an intro plus content
            # Remove the intro if we didn't get any content
            if len(answer_parts) == 1:
                answer_text = "Các nguồn tài liệu có thể cung cấp một số thông tin liên quan, nhưng cần thêm nghiên cứu để trả lời đầy đủ."
            else:
                # Join content sentences, keeping the intro separate
                content_text = ' '.join(answer_parts[1:])  # Skip intro
                answer_text = answer_parts[0] + content_text
        else:
            answer_text = " ".join(answer_parts) if answer_parts else "Không thể trích xuất thông tin từ các nguồn có sẵn."

        # Limit answer length but try to end at a sentence boundary
        if len(answer_text) > 1200:
            # Try to cut at a sentence boundary
            cutoff = answer_text.rfind('.', 0, 1200)
            if cutoff != -1 and cutoff > 1000:  # Only if we find a reasonable breakpoint
                answer_text = answer_text[:cutoff + 1]
            else:
                answer_text = answer_text[:1200] + "..."

        elapsed = time.time() - start

        return {
            "question": question,
            "answer": answer_text.strip(),
            "sources": sources[:3],  # Limit sources
            "retrieval_time_ms": round(elapsed * 1000, 2),
            "count": len(results)
        }


# ----------------------------- CLI -----------------------------

def main():
    parser = argparse.ArgumentParser(description="RAG cho website thocung.com")
    parser.add_argument("--build", action="store_true", help="Xây dựng lại index")
    parser.add_argument("--query", type=str, help="Truy vấn nhanh")
    parser.add_argument("--posts-dir", type=str, default=str(POST_DIR), help="Thư mục bài viết")

    args = parser.parse_args()

    rag = ThocungRAG()

    if args.build:
        count = rag.build_index(args.posts_dir)
        print(f"[+] Hoàn thành! Đã index {count} chunks")
    elif args.query:
        result = rag.generate_answer(args.query)
        print(f"\n=== CÂU TRẢ LỜI ===")
        print(f"Câu hỏi: {args.query}")
        print(f"\n{result['answer']}\n")
        print(f"Nguồn: {len(result['sources'])} kết quả truy xuất")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()