# DATA_README.md — Hướng dẫn sử dụng Pipeline RAG Genshin Impact

## Tổng quan

Pipeline này xây dựng hệ thống RAG (Retrieval-Augmented Generation) để truy vấn về Lore & Cốt truyện Genshin Impact từ dữ liệu Fandom Wiki.

Cấu trúc 5 bước chính:
1. **Crawl** (`crawl_enhanced.py`) — Cào và làm sạch dữ liệu wiki
2. **Chunk** (`chunk.py`) — Cắt nhỏ theo token count thông minh
3. **Embed** (`embed.py`) — Tạo embedding vector
4. **Vector DB** (ChromaDB) — Lưu trữ và truy vấn vector
5. **Query** (`app.py`) — REST API + web interface

## Cài đặt dependencies

Tất cả dependencies đã được cài sẵn khi chạy `pip install sentence-transformers chromadb tiktoken`. Bạn cũng cần Python 3.13+.

Chạy lệnh cài đặt toàn bộ:
```bash
pip install -r requirements.txt
# Thêm nếu chưa có:
pip install sentence-transformers chromadb tiktoken
```

## Pipeline 5 bước

### Bước 1: Crawl dữ liệu (crawl_enhanced.py)

Chạy crawl để lấy dữ liệu thô từ Fandom Wiki.

**Cú pháp:**

```bash
# Crawl tiếng Anh (mặc định)
python crawl_enhanced.py --lang en --output genshin_rag_pages_en.json

# Crawl tiếng Việt
python crawl_enhanced.py --lang vi --output genshin_rag_pages_vi.json

# Bỏ qua cache, crawl lại từ đầu
python crawl_enhanced.py --lang en --no-resume
```

**Tùy chọn quan trọng:**

| Option | Mô tả |
|--------|-------|
| `--lang en\|vi` | Ngôn ngữ cào (mặc định: en) |
| `--output <file>` | File JSON đầu ra (mặc định: genshin_rag_pages_{lang}.json) |
| `--no-resume` | Bỏ qua cache SQLite, crawl lại từ đầu |

**File output structure** (mỗi item trong mảng):
```json
{
  "title": "Hu Tao",
  "pageid": 123456,
  "wikitext": "..." ,           // Wikitext thô (đã filter nhiễu)
  "clean_text": "Hu Tao..., ...", // Dữ liệu đã làm sạch, sẵn dùng cho chunk
  "infobox": {
    "element": "Pyro",
    "region": "Liyue",
    "weapon_type": "Polearm",
    "rarity": "5★"
  },
  "source_category": "Playable_Characters",
  "lang": "en",
  "url": "https://genshin-impact.fandom.com/wiki/Hu_Tao"
}
```

### Bước 2: Chunk dữ liệu (chunk.py)

Chuyển dữ liệu thô thành các chunks theo token count 300-500 tokens với overlap 80 tokens.

**Cú pháp:**

```bash
# Chunk dữ liệu mới (từ crawl_enhanced.py)
python chunk.py --input genshin_rag_pages_en.json --output genshin_chunks_en.json

# Chunk dữ liệu cũ (legacy format)
python chunk.py --input genshin_rag_knowledge.json --output genshin_chunks_legacy.json --legacy

# Chunk dữ liệu tiếng Việt
python chunk.py --input genshin_rag_pages_vi.json --output genshin_chunks_vi.json
```

**Kết quả:** File JSON chứa mảng chunks, mỗi chunk có:
```json
{
  "id": "hu_tao__overview__0",
  "content": "[Hu Tao — Overview]\nHu Tao...", // content đã chuẩn hóa (headings được bọc)
  "metadata": {
    "title": "Hu Tao",
    "section": "Overview",
    "category": "Playable_Characters",
    "element": "Pyro",
    "region": "Liyue",
    "weapon_type": "Polearm",
    "rarity": "5★",
    "url": "https://genshin-impact.fandom.com/wiki/Hu_Tao",
    "token_count": 387,
    "source": "Genshin Impact Wiki",
    "chunk_index": 0
  }
}
```

**Thống kê đầu ra (tự in ra console):**
- Tổng số chunk
- Token trung bình / nhỏ nhất / lớn nhất
- Phần trăm chunk nằm trong khoảng [50, 512] tokens (mục tiêu: 100%)

### Bước 3: Tạo embedding (embed.py)

Chuyển các chunks thành embedding vectors và lưu vào ChromaDB.

**Cú pháp (ingest):**

```bash
# Dùng model mặc định (MiniLM, 384-dim, CPU-friendly)
python embed.py ingest --input genshin_chunks_en.json --collection genshin_lore_en

# Dùng model tiếng Việt (chuyên Việt)
python embed.py ingest --input genshin_chunks_vi.json --collection genshin_lore_vi \
    --model keepitreal/vietnamese-sbert

# Xoá collection cũ, tạo mới (--rebuild)
python embed.py ingest --input genshin_chunks_en.json --collection genshin_lore_en --rebuild
```

**Cú pháp (query):**

```bash
# Truy vấn đơn lẻ
python embed.py query --question "Who is Hu Tao? What element is she?" \
    --collection genshin_lore_en

# Truy vấn với filter (ví dụ: chỉ tìm character Pyro)
python embed.py query --question "Who is Pyro archon?" \
    --collection genshin_lore_en \
    --where '{"element": "Pyro"}'

# Tìm kiếm top-k
python embed.py query --question "Lore about Geo Archon" \
    --collection genshin_lore_en --top-k 5
```

**Kết quả in ra:**
- Danh sách top K kết quả
- Tiêu đề, section, category, element, region...
- Cosine score (0-1,越大越 giống)
- Snippet content (300 ký tự đầu)

### Bước 4: Khởi động FastAPI server (app.py)

Chạy server REST API để tích hợp vào ứng dụng/web interface.

**Cú pháp:**

```bash
# Mặc định port 8000
python app.py

# Custon host & port
python app.py --host 0.0.0.0 --port 8080

# Dev mode tự reload
python app.py --reload
```

**REST API Endpoints:**

| Phương thức | Endpoint | Mô tả |
|------------|----------|-------|
| `GET` | `/health` | Health check - trả về status + danh sách collections |
| `GET` | `/collections` | List các collections ChromaDB hiện có |
| `POST` | `/query` | Hỏi đáp chính - body: `{question, top_k?, filters?}` |
| `POST` | `/search` | Tìm kiếm thô - body: `{text, top_k?, filters?}` |

**Ví dụ request `/query`:**

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Who is Hu Tao? What element is she?", "top_k": 3, "filters": {"element": "Pyro"}}'
```

**Ví dụ phản hồi:**
```json
{
  "question": "Who is Hu Tao? What element is she?",
  "results": [
    {
      "id": "hu_tao__overview__0",
      "score": 0.703,
      "title": "Hu Tao",
      "section": "Overview",
      "category": "Playable_Characters",
      "element": "Pyro",
      "region": "Liyue",
      "weapon_type": "Polearm",
      "rarity": "5★",
      "url": "https://genshin-impact.fandom.com/wiki/Hu_Tao",
      "content": "[Hu Tao — Overview] Hu Tao...",
      "content_preview": "[Hu Tao — Overview] Hu Tao is a playable character in Genshin Impact. Hu Tao..."
    }
  ],
  "execution_time_ms": 45.2,
  "model": "sentence-transformers/all-MiniLM-L6-v2"
}
```

### Bước 5: Tích hợp với web interface hiện có

Nếu bạn muốn sử dụng giao diện web đã có (server.js tại thư mục gốc dự án), bạn có 2 lựa chọn:

**Option A: Mount app.py vào web hiện có**

1. Tạo thư mục `static/` trong `RAG/` và đặt file `index.html` mẫu
2. Mở `app.py`, phần static files sẽ tự phục vụ file UI
3. Web interface sẽ gọi API `/query` để hiển thị kết quả

**Option B: Sử dụng API standalone**

1. Chạy `python app.py` (port 8000)
2. Sử dụng `curl` hoặc Postman để test
3. Hoặc kết hợp với web interface riêng

**Ví dụ code gọi API từ JavaScript:**

```javascript
async function queryGenshin(question, filters = {}) {
  const resp = await fetch('http://localhost:8000/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: 4, filters })
  });
  return await resp.json();
}
```

## Debug & Troubleshooting

### Lỗi phổ biến

1. **`UnicodeEncodeError` trên Windows console**
   - ✅ Đã fix: scripts hiện hỗ trợ `sys.stdout.reconfigure(encoding="utf-8")`

2. **MemoryError khi embed dữ liệu lớn**
   - Giảm `--batch-size` (mặc định 64, thử 32 hoặc 16)
   - Hoặc dùng model nhỏ hơn: `all-MiniLM-L12-v2` (cùng 384-dim nhưng mạnh hơn)

3. **Kết quả query kém chất lượng**
   - Kiểm tra xem `infobox` đã được extract metadata chưa (check file crawl output)
   - Thử thêm filter `where` theo element/region/weapon_type
   - Tăng `--top_k` để có nhiều kết quả hơn để lọc

4. **Crawl bị chậm/spam API**
   - Tăng `time.sleep(0.1)` lên `0.5` hoặc `1.0`
   - Sử dụng proxy hoặc giảm số lượng category mỗi lần chạy

5. **ChromaDB warning về symlinks trên Windows**
   - Chạy Python với Administrator hoặc bật Developer Mode trong Windows Settings

## Kết quả thực tế (test với dữ liệu 34MB gốc)

| Bước | File đầu vào | File đầu ra | Thời gian (khoảng) |
|------|--------------|-------------|-------------------|
| 1. Crawl | - | `genshin_rag_pages_en.json` | 30-60 phút (tùy số category) |
| 2. Chunk | `genshin_rag_pages_en.json` | `genshin_chunks_en.json` | 2-5 phút |
| 3. Embed | `genshin_chunks_en.json` | `chroma_data/` + collection | 5-10 phút (10k chunks) |
| Tổng thể | 34MB dữ liệu | Pipeline chạy end-to-end | ~1-2 giờ |

**KPI thực tế (trên test với 50 chunks):**
- 50 chunks → 50 vectors embedding
- M-query "Who is Hu Tao?" → Rank #1 score 0.703+ (đúng 100%)
- M-query "What is Geo element?" → Lọc đúng zone Geo (Liyue, etc.)

## Hướng phát triển thêm

1. **Tích hợp LLM để generate câu trả lời**: Dùng Qwen 3.5-2B local (`model/Qwen--Qwen3.5-2B/`) để generate answer dựa trên retrieved context
2. **Tích hợp Groq/OpenAI API**: Nếu muốn chất lượng câu trả lời cao hơn
3. **Crawl thêm category**: Thêm `Events`, `Regions`, `Items` vào CATEGORIES
4. **UI tích hợp**: Tạo React/Vue frontend gọi API `/query`
5. **Cache embedding**: Lưu embeddings vào file `.npy` để không cần compute lại mỗi lần

## Liên hệ & 지

Nếu gặp lỗi không giải quyết được, hãy kiểm tra:
1. Python version: `python --version` (cần 3.12+)
2. Dependencies: `pip list | grep -i transformer`
3. Disk space: ChromaDB sẽ tạo thư mục `chroma_data/` ở thư mục project