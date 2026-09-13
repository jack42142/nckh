# 🤖 Hệ thống RAG cho website thocung.com

## Tổng quan

Hệ thống RAG (Retrieval-Augmented Generation) được tích hợp vào website thocung.com để cung cấp câu trả lời thông minh dựa trên dữ liệu bài viết trong thư mục `/data/post/`.

## Thành phần

1. **thocung_rag.py** - Engine RAG chính (chunking, embedding, querying)
2. **rag_server.py** - FastAPI server cung cấp API RAG trên port 8000
3. **update_rag.py** - Script quản lý rebuild và kiểm tra trạng thái index
4. **server.js** - Node.js server đã được cập nhật để proxy API `/api/chat` và `/api/rag/rebuild`
5. **script.js** - Cập nhật chức năng chat để gọi RAG thực sự
6. **index.html** - Thêm nút "Cập nhật RAG" cho admin
7. **style.css** - Thêm animation cho loading indicator

## Pipeline Hoạt động

```
/data/post/*.html --> thocung_rag.py --> ChromaDB --> rag_server.py (port 8000)
                              ↑
                    Node.js server.js (port 3000) --> /api/chat --> proxy to rag_server
                              ↑
                          script.js (chat UI)
```

## Cài đặt & Chạy

### Yêu cầu
- Python 3.12+ với dependencies từ `RAG/requirements.txt`
- Node.js 16+ (đã có sẵn)
- Đã cài đặt `pip install -r RAG/requirements.txt`

### Chạy hệ thống

1. **Khởi động RAG engine** (chạy một lần để build index):
   ```bash
   cd RAG
   python thocung_rag.py --build
   ```

2. **Khởi động cả hai server**:
   ```bash
   # Terminal 1: Node.js server (port 3000)
   cd /path/to/nckh
   node server.js

   # Terminal 2: Python RAG server (port 8000)  
   cd RAG
   python rag_server.py
   ```

3. **Truy cập website**: http://localhost:3000

### Tích hợp với hệ thống hiện có

- Chat widget trong `index.html` giờ gọi `/api/chat` → Node.js proxy → Python RAG API
- Admin có thể click nút "🔄 RAG" trong danh sách bài viết để rebuild index
- Nút "Cập nhật bài viết" vẫn hoạt động bình thường
- Khi tạo/sửa bài viết qua UI, admin cần ręng rebuild RAG để cập nhật dữ liệu mới

## API Endpoints

### Từ Node.js (port 3000)
- `POST /api/chat` - Chat với RAG (proxy tới Python)
- `POST /api/rag/rebuild` - Rebuild index (yêu cầu admin)
- `GET /api/rag/status` - Kiểm tra trạng thái RAG

### Từ Python (port 8000)
- `POST /query` - Truy vấn RAG (extractive answer)
- `POST /rebuild` - Rebuild index
- `GET /health` - Health check
- `GET /collections` - Liệt kê collections

## Quản lý dữ liệu

### Thêm/sửa bài viết
1. Thêm file `.html` mới vào `/data/post/` hoặc
2. Sửa file hiện có qua admin UI (tạo/sửa bài viết)

### Cập nhật RAG index
- **Cách 1 (tự động)**: Admin click nút "🔄 RAG" trong danh sách bài viết
- **Cách 2 (thủ công)**: Chạy `python update_rag.py` trong thư mục RAG
- **Cách 3 (API)**: Gọi `POST /api/rag/rebuild` với cookie admin

## Kiểm tra hoạt động

### Test nhanh
```bash
# Test Python RAG trực tiếp
cd RAG
python thocung_rag.py --query "Tục thờ cúng tổ tiên là gì?"

# Test API
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":"hello"}'

# Test Node.js proxy
curl -X POST http://localhost:3000/api/chat -H "Content-Type: application/json" -d '{"question":"hello"}'
```

## Giải pháp dự phòng

Nếu Python RAG server không khả dụng:
- Chat sẽ hiển thị thông báo fallback: "Hệ thống RAG đang khởi động..."
- Các tính năng khác của website (đọc bài, tạo bài) vẫn hoạt động bình thường

## Tùy chỉnh nâng cao

### Thay đổi model embedding
Sửa trong `thocung_rag.py`:
```python
VIETMODEL = "keepitreal/vietnamese-sbert"  # hoặc "intfloat/multilingual-e5-base"
```

### Điều chỉnh chunk size
Sửa trong `thocung_rag.py`:
```python
MAX_CHARS = 8000  # Tăng/giảm tùy thuộc vào độ dài trả lời mong muốn
```

## Cấu trúc file

```
nckh/
├── RAG/
│   ├── thocung_rag.py          # RAG engine
│   ├── rag_server.py           # FastAPI server
│   ├── update_rag.py           # Management script
│   ├── requirements.txt        # Python dependencies
│   ├── README_THOCUNG.md       # This file
│   └── chroma_data/            # Vector DB (tự động tạo)
├── data/
│   └── post/                   # HTML articles
├── node_modules/               # Node.js deps
├── server.js                   # Node.js server (đã cập nhật)
├── script.js                   # Frontend logic (đã cập nhật)
├── index.html                  # Main page (đã cập nhật)
└── style.css                   # Styles (đã cập nhật)
```