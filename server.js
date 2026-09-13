const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 3300;

// Python RAG server endpoint
const RAG_PORT = 8001;
const RAG_HOST = '127.0.0.1';

const MIME_TYPES = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon'
};

// Mỗi bài viết là một file HTML riêng trong /data/post/
const DATA_DIR = path.join(__dirname, 'data');
const POST_DIR = path.join(DATA_DIR, 'post');
const LEGACY_POSTS_FILE = path.join(DATA_DIR, 'posts.json');

const INITIAL_POSTS = [
  {
    id: "post-default-1",
    title: "Hướng Dẫn Tìm Hiểu Về Mạng Máy Tính",
    category: "Công nghệ thông tin",
    date: "01/09/2026",
    content: `
      <h2>1. Mạng máy tính là gì?</h2>
      <p>Mạng máy tính là tập hợp các máy tính được kết nối với nhau để trao đổi dữ liệu và chia sẻ tài nguyên.</p>
      <div class="article-image">
        <img src="https://images.unsplash.com/photo-1544197150-b99a580bb7a8?w=800" alt="Mạng máy tính">
        <span class="caption">Hình 1: Hệ thống kết nối mạng dữ liệu.</span>
      </div>
      <h2>2. Các loại mạng phổ biến</h2>
      <h3>2.1. Mạng cục bộ (LAN)</h3>
      <p>LAN kết nối các thiết bị trong phạm vi hẹp như nhà ở, văn phòng.</p>
      <h3>2.2. Mạng diện rộng (WAN)</h3>
      <p>WAN kết nối các thiết bị ở khoảng cách xa qua nhiều quốc gia.</p>
    `
  }
];

function escapeHtmlMeta(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Sinh nội dung file HTML hoàn chỉnh từ object bài viết
function postToHtml(post) {
  return `<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>${escapeHtmlMeta(post.title)}</title>
  <meta name="category" content="${escapeHtmlMeta(post.category)}">
  <meta name="date" content="${escapeHtmlMeta(post.date)}">
</head>
<body>
  <article>
${post.content}
  </article>
</body>
</html>
`;
}

// Parse ngược file HTML thành object bài viết
// Trả về null nếu file không đọc được / thiếu <article>
function htmlToPost(id, html) {
  try {
    const articleMatch = html.match(/<article>([\s\S]*?)<\/article>/);
    if (!articleMatch) return null;

    const titleMatch = html.match(/<title>([\s\S]*?)<\/title>/);
    const categoryMatch = html.match(/<meta name="category" content="([\s\S]*?)">/);
    const dateMatch = html.match(/<meta name="date" content="([\s\S]*?)">/);

    const unescapeMeta = (text) => {
      if (!text) return '';
      return text
        .replace(/&quot;/g, '"')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&');
    };

    return {
      id: id,
      title: unescapeMeta(titleMatch ? titleMatch[1].trim() : ''),
      category: unescapeMeta(categoryMatch ? categoryMatch[1].trim() : ''),
      date: unescapeMeta(dateMatch ? dateMatch[1].trim() : ''),
      content: articleMatch[1].replace(/^\n/, '').replace(/\n\s*$/, '')
    };
  } catch (err) {
    console.error(`Lỗi parse bài viết ${id}:`, err.message);
    return null;
  }
}

// Đọc toàn bộ bài viết từ thư mục /data/post/
// Sort theo thời gian sửa file giảm dần (mới nhất lên đầu)
function getPosts() {
  if (!fs.existsSync(POST_DIR)) return [];
  const files = fs.readdirSync(POST_DIR).filter(f => f.endsWith('.html'));
  const posts = [];
  for (const file of files) {
    const id = path.basename(file, '.html');
    try {
      const html = fs.readFileSync(path.join(POST_DIR, file), 'utf-8');
      const post = htmlToPost(id, html);
      if (post) posts.push(post);
    } catch (err) {
      console.error(`Lỗi đọc bài viết ${file}:`, err.message);
    }
  }
  posts.sort((a, b) => {
    const statA = fs.statSync(path.join(POST_DIR, a.id + '.html'));
    const statB = fs.statSync(path.join(POST_DIR, b.id + '.html'));
    return statB.mtimeMs - statA.mtimeMs;
  });
  return posts;
}

// Ghi một bài viết thành file HTML trong /data/post/
function savePost(post) {
  fs.mkdirSync(POST_DIR, { recursive: true });
  fs.writeFileSync(path.join(POST_DIR, post.id + '.html'), postToHtml(post), 'utf-8');
}

// Chỉ cho phép id an toàn (chống path traversal)
function isValidPostId(id) {
  return /^[A-Za-z0-9._-]+$/.test(id);
}

// Xóa file HTML của một bài viết. Trả về true nếu xóa được.
function deletePostFile(id) {
  if (!isValidPostId(id)) return false;
  const filePath = path.join(POST_DIR, id + '.html');
  if (!fs.existsSync(filePath)) return false;
  fs.unlinkSync(filePath);
  return true;
}

// Di dời dữ liệu cũ từ posts.json sang các file HTML riêng
function migrateLegacyPosts() {
  if (fs.existsSync(LEGACY_POSTS_FILE)) {
    try {
      const legacyPosts = JSON.parse(fs.readFileSync(LEGACY_POSTS_FILE, 'utf-8'));
      fs.mkdirSync(POST_DIR, { recursive: true });
      for (const post of legacyPosts) {
        if (post.id && post.title && post.content) {
          savePost(post);
        }
      }
      // Giữ lại file cũ làm backup
      fs.renameSync(LEGACY_POSTS_FILE, LEGACY_POSTS_FILE + '.migrated');
      console.log(`Đã di dời ${legacyPosts.length} bài viết từ posts.json sang ${POST_DIR}`);
      return;
    } catch (err) {
      console.error('Lỗi di dời posts.json:', err.message);
    }
  }

  // Lần khởi động đầu tiên: seed bài viết mặc định
  if (!fs.existsSync(POST_DIR)) {
    fs.mkdirSync(POST_DIR, { recursive: true });
    for (const post of INITIAL_POSTS) {
      savePost(post);
    }
  }
}

function getCookie(req, name) {
  const cookies = (req.headers.cookie || '').split(';');
  for (let cookie of cookies) {
    const [cookieName, cookieValue] = cookie.trim().split('=');
    if (cookieName === name) return cookieValue;
  }
  return null;
}

function isAdmin(req) {
  return getCookie(req, 'role') === 'admin';
}

function sendJSON(res, statusCode, data) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store'
  });
  res.end(JSON.stringify(data));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let chunks = [];
    req.on('data', chunk => {
      chunks.push(chunk);
      console.log('[NODE DEBUG] Raw chunk received:', chunk);
      console.log('[NODE DEBUG] Chunk as hex:', chunk.toString('hex'));
    });
    req.on('end', () => {
      try {
        const buffer = Buffer.concat(chunks);
        console.log('[NODE DEBUG] Full buffer:', buffer);
        console.log('[NODE DEBUG] Full buffer as hex:', buffer.toString('hex'));
        console.log('[NODE DEBUG] Full buffer as UTF-8 string:', buffer.toString('utf8'));
        const body = buffer.toString('utf8');
        resolve(body ? JSON.parse(body) : {});
      } catch (err) {
        console.log('[NODE DEBUG] JSON parse error:', err);
        reject(new Error('Dữ liệu không hợp lệ'));
      }
    });
    req.on('error', reject);
  });
}

// Proxy request to Python RAG server
function proxyToRAG(req, res, pathname, body) {
  const postData = body ? JSON.stringify(body) : null;
  console.log('[RAG Proxy] Sending postData:', postData);
  console.log('[RAG Proxy] postData length:', Buffer.byteLength(postData || '', 'utf8'));
  const options = {
    hostname: RAG_HOST,
    port: RAG_PORT,
    path: pathname,
    method: req.method,
    headers: {
      'Content-Type': 'application/json; charset=utf-8'
    }
  };

  const proxyReq = http.request(options, (proxyRes) => {
    let data = '';
    proxyRes.on('data', chunk => { data += chunk; });
    proxyRes.on('end', () => {
      try {
        const parsed = JSON.parse(data);
        sendJSON(res, 200, parsed);
      } catch (e) {
        sendJSON(res, 200, { answer: data, status: 'success' });
      }
    });
  });

  proxyReq.on('error', (err) => {
    console.error('[RAG Proxy] Lỗi kết nối:', err.message);
    // Fallback: return local answer
    sendJSON(res, 200, {
      answer: 'Hệ thống RAG đang khởi động hoặc tạm thời không khả dụng. Vui lòng thử lại sau!',
      status: 'fallback'
    });
  });

  if (postData) {
    // Use Buffer.byteLength to correctly calculate byte length for UTF-8
    const byteLength = Buffer.byteLength(postData, 'utf8');
    proxyReq.setHeader('Content-Length', byteLength);
    proxyReq.write(postData, 'utf8');
  }
  proxyReq.end();
}

function handleAPI(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = url.pathname;

  // GET /api/posts - Lấy danh sách bài viết (ai cũng xem được)
  if (req.method === 'GET' && pathname === '/api/posts') {
    sendJSON(res, 200, { posts: getPosts() });
    return true;
  }

  // POST /api/posts - Tạo bài viết mới (chỉ admin)
  if (req.method === 'POST' && pathname === '/api/posts') {
    if (!isAdmin(req)) {
      sendJSON(res, 403, { error: 'Bạn không có quyền tạo bài viết.' });
      return true;
    }
    readBody(req).then(post => {
      if (!post.title || !post.title.trim() || !post.category || !post.category.trim() || !post.content || !post.content.trim()) {
        sendJSON(res, 400, { error: 'Vui lòng điền đầy đủ tiêu đề, danh mục và nội dung.' });
        return;
      }
      const newPost = {
        id: post.id && isValidPostId(post.id) ? post.id : 'post-' + Date.now(),
        title: post.title.trim(),
        category: post.category.trim(),
        date: post.date || new Date().toLocaleDateString('vi-VN'),
        content: post.content
      };
      savePost(newPost);
      sendJSON(res, 201, { post: newPost });
    }).catch(err => sendJSON(res, 400, { error: err.message }));
    return true;
  }

  // PUT /api/posts/:id - Cập nhật bài viết (chỉ admin)
  const putMatch = pathname.match(/^\/api\/posts\/([^/]+)$/);
  if (req.method === 'PUT' && putMatch) {
    if (!isAdmin(req)) {
      sendJSON(res, 403, { error: 'Bạn không có quyền sửa bài viết.' });
      return true;
    }
    const postId = decodeURIComponent(putMatch[1]);
    if (!isValidPostId(postId)) {
      sendJSON(res, 400, { error: 'ID bài viết không hợp lệ.' });
      return true;
    }
    readBody(req).then(postData => {
      if (!postData.title || !postData.title.trim() || !postData.category || !postData.category.trim() || !postData.content || !postData.content.trim()) {
        sendJSON(res, 400, { error: 'Vui lòng điền đầy đủ tiêu đề, danh mục và nội dung.' });
        return;
      }
      const updatedPost = {
        id: postId,
        title: postData.title.trim(),
        category: postData.category.trim(),
        date: postData.date || new Date().toLocaleDateString('vi-VN'),
        content: postData.content
      };
      const filePath = path.join(POST_DIR, postId + '.html');
      if (!fs.existsSync(filePath)) {
        sendJSON(res, 404, { error: 'Không tìm thấy bài viết.' });
        return;
      }
      savePost(updatedPost);
      sendJSON(res, 200, { post: updatedPost });
    }).catch(err => sendJSON(res, 400, { error: err.message }));
    return true;
  }

  // DELETE /api/posts/:id - Xóa bài viết (chỉ admin)
  const deleteMatch = pathname.match(/^\/api\/posts\/([^/]+)$/);
  if (req.method === 'DELETE' && deleteMatch) {
    if (!isAdmin(req)) {
      sendJSON(res, 403, { error: 'Bạn không có quyền xóa bài viết.' });
      return true;
    }
    const postId = decodeURIComponent(deleteMatch[1]);
    if (!deletePostFile(postId)) {
      sendJSON(res, 404, { error: 'Không tìm thấy bài viết.' });
      return true;
    }
    sendJSON(res, 200, { success: true });
    return true;
  }

  // POST /api/chat - Chat RAG (ai cũng dùng được)
  if (req.method === 'POST' && pathname === '/api/chat') {
    readBody(req).then(body => {
      const question = (body.question || '').trim();
      console.log('Received question:', question);
      if (!question) {
        sendJSON(res, 400, { error: 'Câu hỏi không được để trống.' });
        return;
      }
      proxyToRAG(req, res, '/query', body);
    }).catch(err => sendJSON(res, 400, { error: err.message }));
    return true;
  }

  // POST /api/rag/rebuild - Rebuild RAG index (chỉ admin)
  if (req.method === 'POST' && pathname === '/api/rag/rebuild') {
    if (!isAdmin(req)) {
      sendJSON(res, 403, { error: 'Bạn không có quyền cập nhật dữ liệu RAG.' });
      return true;
    }
    proxyToRAG(req, res, '/rebuild', {});
    return true;
  }

  // GET /api/rag/status - Kiểm tra trạng thái RAG
  if (req.method === 'GET' && pathname === '/api/rag/status') {
    const options = {
      hostname: RAG_HOST,
      port: RAG_PORT,
      path: '/health',
      method: 'GET'
    };
    const proxyReq = http.request(options, (proxyRes) => {
      let data = '';
      proxyRes.on('data', chunk => { data += chunk; });
      proxyRes.on('end', () => {
        try {
          sendJSON(res, 200, JSON.parse(data));
        } catch (e) {
          sendJSON(res, 200, { rag_status: 'unreachable' });
        }
      });
    });
    proxyReq.on('error', () => {
      sendJSON(res, 200, { rag_status: 'unreachable' });
    });
    proxyReq.end();
    return true;
  }

  return false;
}

const server = http.createServer((req, res) => {
  // API endpoints
  if (req.url.startsWith('/api/')) {
    if (handleAPI(req, res)) return;
    sendJSON(res, 404, { error: 'Không tìm thấy API.' });
    return;
  }

  // Chỉ redirect root path "/" về login.html
  if (req.url === '/') {
    res.writeHead(302, { 'Location': '/login.html' });
    res.end();
    return;
  }

  let filePath = path.join(__dirname, req.url);
  let extname = path.extname(filePath);
  let contentType = MIME_TYPES[extname] || 'application/octet-stream';

  fs.readFile(filePath, (err, content) => {
    if (err) {
      if (err.code === 'ENOENT') {
        res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end('<h1>404 - Không tìm thấy trang</h1>');
      } else {
        res.writeHead(500);
        res.end(`Lỗi Server: ${err.code}`);
      }
    } else {
      res.writeHead(200, { 'Content-Type': `${contentType}; charset=utf-8` });
      res.end(content, 'utf-8');
    }
  });
});

migrateLegacyPosts();

server.listen(PORT, () => {
  console.log(`Server đang chạy tại: http://localhost:${PORT}`);
  console.log(`RAG server: http://localhost:${RAG_PORT} (nếu đang chạy)`);
});
