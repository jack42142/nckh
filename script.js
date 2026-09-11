// Cache trong bộ nhớ — nguồn dữ liệu thật nằm trên server (/data/post/)
let localPostsCache = [];

function escapeHtmlText(text) {
  if (!text) return '';
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeJsString(text) {
  if (!text) return '';
  return text.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function escapeHtmlAttrDouble(text) {
  if (!text) return '';
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function getOnclickAction(actionFn, value) {
  const functionCall = actionFn + "('" + escapeJsString(value) + "')";
  return escapeHtmlAttrDouble(functionCall);
}

let currentActivePostId = null;

document.addEventListener('DOMContentLoaded', () => {
  applyUserMode();
  loadPostsFromServer();
  animateElementsOnLoad();
  setupLogoEffect();
  setupEditorEvents();
});

function getCookie(name) {
  const cookies = document.cookie.split(';');
  for (let cookie of cookies) {
    const [cookieName, cookieValue] = cookie.trim().split('=');
    if (cookieName === name) return cookieValue;
  }
  return null;
}

function applyUserMode() {
  const userRole = getCookie('role') || 'user';
  const userRoleBadge = document.getElementById('userRoleBadge');

  if (userRole === 'admin') {
    if (userRoleBadge) {
      userRoleBadge.className = 'admin-badge';
      userRoleBadge.textContent = '🔧 Admin';
    }
  } else {
    if (userRoleBadge) {
      userRoleBadge.className = 'user-badge';
      userRoleBadge.textContent = '👤 Người dùng (Chỉ đọc)';
    }
    // Ẩn các chức năng admin cho user mode
    const createBtn = document.querySelector('.btn-primary[onclick*="toggleModal"]');
    if (createBtn) createBtn.style.display = 'none';

    // Ẩn các nút delete
    setTimeout(() => {
      const deleteBtns = document.querySelectorAll('.btn-danger[onclick*="deletePost"]');
      deleteBtns.forEach(btn => btn.style.display = 'none');
    }, 100);
  }
}

function logout() {
  if (confirm('Bạn có chắc chắn muốn đăng xuất?')) {
    document.cookie = 'role=; expires=Thu, 01 Jan 1970 00:00:00; path=/';
    document.cookie = 'loggedIn=; expires=Thu, 01 Jan 1970 00:00:00; path=/';
    window.location.href = 'login.html';
  }
}

function animateElementsOnLoad() {
  const introCards = document.querySelectorAll('.intro-card');
  introCards.forEach((card, index) => {
    setTimeout(() => { card.classList.add('animate-fade-in'); }, index * 100);
  });

  const introHero = document.querySelector('.intro-hero');
  if (introHero) introHero.classList.add('animate-scale-in');
}

function setupLogoEffect() {
  const logo = document.querySelector('.navbar .logo');
  if (logo) {
    logo.addEventListener('mousemove', (e) => {
      const rect = logo.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const rotateX = (y - rect.height / 2) / (rect.height / 2) * 10;
      const rotateY = (rect.width / 2 - x) / (rect.width / 2) * 10;
      logo.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(1.05)`;
    });
    logo.addEventListener('mouseleave', () => {
      logo.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale(1)';
    });
  }
}

// API client - tải bài viết từ server
async function fetchPosts() {
  try {
    const response = await fetch('/api/posts');
    const data = await response.json();
    localPostsCache = data.posts || [];
  } catch (err) {
    console.error('Lỗi tải bài viết từ server:', err);
    localPostsCache = [];
  }
  return localPostsCache;
}

// Lấy bài viết từ cache (đã đồng bộ với server)
function getStoredPosts() {
  return localPostsCache;
}

// Cập nhật cache và tải lại danh sách từ server
async function loadPostsFromServer() {
  await fetchPosts();
  renderPostsList();
}

function switchView(viewName) {
  const homeView = document.getElementById('view-home');
  const postsView = document.getElementById('view-posts');
  const readingView = document.getElementById('view-reading');

  const navHome = document.getElementById('nav-home');
  const navPosts = document.getElementById('nav-posts');
  const navReading = document.getElementById('nav-reading');

  navHome.classList.remove('active');
  navPosts.classList.remove('active');
  navReading.classList.remove('active');

  homeView.style.display = 'none';
  postsView.style.display = 'none';
  readingView.style.display = 'none';

  if (viewName === 'home') {
    homeView.style.display = 'block';
    navHome.classList.add('active');
  } else if (viewName === 'posts') {
    postsView.style.display = 'block';
    navPosts.classList.add('active');
    renderPostsList();
  } else if (viewName === 'reading') {
    if (currentActivePostId) {
      readingView.style.display = 'block';
      navReading.classList.add('active');
    } else {
      switchView('posts');
    }
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function renderPostsList() {
  const postsGrid = document.getElementById('postsGrid');
  if (!postsGrid) return;

  const posts = getStoredPosts();

  if (posts.length === 0) {
    postsGrid.innerHTML = `
      <div style="grid-column: 1/-1; text-align:center; padding:3rem; background:white; border-radius:12px;">
        <h3>Chưa có bài viết nào!</h3>
        <p>Bấm nút "+ Tạo bài viết mới" để bắt đầu soạn bài.</p>
      </div>
    `;
    return;
  }

  postsGrid.innerHTML = posts.map(post => {
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = post.content || '';
    const snippet = (tempDiv.textContent || tempDiv.innerText || '').substring(0, 110) + '...';

    const isAdmin = getCookie('role') === 'admin';
    const deleteButton = isAdmin ? `
      <button class="btn-danger" onclick="${getOnclickAction('deletePost', post.id)}">Xóa</button>` : '';

    return `
      <div class="post-card animate-fade-in">
        <div>
          <span class="badge">${escapeHtmlText(post.category)}</span>
          <h3 class="post-card-title">${escapeHtmlText(post.title)}</h3>
          <p class="post-card-snippet">${escapeHtmlText(snippet)}</p>
        </div>
        <div class="post-card-footer">
          <span>${escapeHtmlText(post.date)}</span>
          <div class="card-actions">
            <button class="btn-primary" onclick="${getOnclickAction('readPost', post.id)}" style="padding:0.3rem 0.8rem; font-size:0.85rem;">Đọc bài</button>
            ${isAdmin ? `<button class="btn-primary" onclick="${getOnclickAction('editPost', post.id)}" style="padding:0.3rem 0.8rem; font-size:0.85rem; background:#2563eb;">Chỉnh sửa</button>` : ''}
            ${deleteButton}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function readPost(postId) {
  const posts = getStoredPosts();
  const post = posts.find(p => p.id === postId);
  if (!post) return;

  currentActivePostId = post.id;

  const articleContent = document.getElementById('articleContent');
  articleContent.innerHTML = `
    <h1 class="post-title">${escapeHtmlText(post.title)}</h1>
    <div class="post-meta">Danh mục: ${escapeHtmlText(post.category)} | Ngày đăng: ${escapeHtmlText(post.date)}</div>
    <div class="article-body">${post.content}</div>
  `;

  const navReading = document.getElementById('nav-reading');
  navReading.textContent = `📖 ${post.title}`;
  navReading.style.display = 'inline-block';

  generateTOC();
  switchView('reading');
}

function generateTOC() {
  const articleBody = document.querySelector('.article-body');
  const tocList = document.getElementById('tocList');
  if (!articleBody || !tocList) return;

  tocList.innerHTML = '';
  const headings = articleBody.querySelectorAll('h2, h3');

  if (headings.length === 0) {
    tocList.innerHTML = '<li><em>Không có đề mục</em></li>';
    return;
  }

  headings.forEach((heading, index) => {
    const headingId = `heading-${index + 1}`;
    heading.id = headingId;

    const li = document.createElement('li');
    if (heading.tagName.toLowerCase() === 'h3') li.classList.add('toc-h3');

    const a = document.createElement('a');
    a.href = `#${headingId}`;
    a.textContent = heading.textContent;

    li.appendChild(a);
    tocList.appendChild(li);
  });
}

// Edit post functionality
function editPost(postId) {
  const posts = getStoredPosts();
  const post = posts.find(p => p.id === postId);
  if (!post) return;

  // Populate form with post data
  document.getElementById('postTitle').value = post.title;
  document.getElementById('postCategory').value = post.category;
  document.getElementById('postContentInput').innerHTML = post.content;

  // Update form submit handler to update instead of create
  const form = document.getElementById('createPostForm');
  form.onsubmit = async function (e) {
    e.preventDefault();

    const titleInput = document.getElementById('postTitle');
    const categoryInput = document.getElementById('postCategory');
    const postContentInput = document.getElementById('postContentInput');

    const title = titleInput ? titleInput.value.trim() : '';
    const category = categoryInput ? categoryInput.value.trim() : '';
    const contentHTML = postContentInput ? postContentInput.innerHTML.trim() : '';

    if (!title || !category) {
      alert('Vui lòng điền đầy đủ tiêu đề và danh mục!');
      return;
    }

    const isEmpty = !contentHTML || contentHTML === '<br>' || contentHTML === '<div><br></div>';
    if (isEmpty) {
      alert('Vui lòng nhập nội dung bài viết!');
      return;
    }

    const updatedPost = {
      id: postId,
      title: title,
      category: category,
      date: new Date().toLocaleDateString('vi-VN'),
      content: contentHTML
    };

    try {
      const response = await fetch(`/api/posts/${encodeURIComponent(postId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedPost)
      });

      const result = await response.json();

      if (!response.ok) {
        alert(result.error || 'Không thể cập nhật bài viết');
        return;
      }

      // Reload posts list
      await loadPostsFromServer();

      // Reset form and close modal
      toggleModal(false);
      resetPostForm();

      // Restore original form submit handler
      form.onsubmit = originalFormSubmit;

      // Optionally open the updated post for reading
      readPost(postId);
    } catch (err) {
      alert('Lỗi khi cập nhật bài viết: ' + err.message);
    }
  };

  toggleModal(true);
  document.getElementById('postModal').querySelector('.modal-header h3').textContent = 'Chỉnh Sửa Bài Viết';
  document.getElementById('createPostForm').querySelector('button[type="submit"]').textContent = 'Cập nhật bài viết';
}

// Store original form submit handler
let originalFormSubmit = null;

async function deletePost(postId) {
  if (!confirm('Bạn có chắc chắn muốn xóa bài viết này không?')) return;

  try {
    const response = await fetch(`/api/posts/${encodeURIComponent(postId)}`, {
      method: 'DELETE'
    });

    const result = await response.json();

    if (!response.ok) {
      alert(result.error || 'Không thể xóa bài viết');
      return;
    }

    let posts = getStoredPosts();
    posts = posts.filter(p => p.id !== postId);
    localPostsCache = posts;
    renderPostsList();

    if (currentActivePostId === postId) {
      currentActivePostId = null;
      document.getElementById('nav-reading').style.display = 'none';
      switchView('posts');
    }
  } catch (err) {
    alert('Lỗi khi xóa bài viết: ' + err.message);
  }
}

function toggleModal(show) {
  const modal = document.getElementById('postModal');
  if (modal) {
    modal.style.display = show ? 'flex' : 'none';
  }
}

function triggerImageUpload() {
  document.getElementById('imageFileInput').click();
}

function handleImageFile(input) {
  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = function (e) {
      const imgHTML = `\n<div class="article-image">\n  <img src="${e.target.result}" alt="Ảnh">\n</div>\n`;
      document.execCommand('insertHTML', false, imgHTML);
      updatePreview();
    };
    reader.readAsDataURL(input.files[0]);
    input.value = '';
  }
}

function insertImageUrl() {
  const url = prompt('Nhập đường dẫn URL của hình ảnh:');
  if (url) {
    const caption = prompt('Nhập chú thích ảnh:') || '';
    const imgHTML = `\n<div class="article-image">\n  <img src="${url}" alt="Hình ảnh">\n  <span class="caption">${caption}</span>\n</div>\n`;
    document.execCommand('insertHTML', false, imgHTML);
    updatePreview();
  }
}

// Store the original form submit handler for creating posts
originalFormSubmit = async function (e) {
  e.preventDefault();

  const titleInput = document.getElementById('postTitle');
  const categoryInput = document.getElementById('postCategory');
  const postContentInput = document.getElementById('postContentInput');

  const title = titleInput ? titleInput.value.trim() : '';
  const category = categoryInput ? categoryInput.value.trim() : '';
  const contentHTML = postContentInput ? postContentInput.innerHTML.trim() : '';

  if (!title || !category) {
    alert('Vui lòng điền đầy đủ tiêu đề và danh mục!');
    return;
  }

  const isEmpty = !contentHTML || contentHTML === '<br>' || contentHTML === '<div><br></div>';
  if (isEmpty) {
    alert('Vui lòng nhập nội dung bài viết!');
    return;
  }

  const newPost = {
    title: title,
    category: category,
    date: new Date().toLocaleDateString('vi-VN'),
    content: contentHTML
  };

  // Gửi bài viết lên server
  try {
    const response = await fetch('/api/posts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newPost)
    });

    const result = await response.json();

    if (!response.ok) {
      alert(result.error || 'Không thể tạo bài viết mới');
      return;
    }

    // Dùng bài viết trả về từ server (có id do server sinh)
    const savedPost = result.post;
    await loadPostsFromServer();

    toggleModal(false);
    resetPostForm();
    renderPostsList();
    readPost(savedPost.id);
  } catch (err) {
    alert('Lỗi khi tạo bài viết: ' + err.message);
  }
};

document.getElementById('createPostForm').addEventListener('submit', originalFormSubmit);

function formatText(command, value = null) {
  const contentInput = document.getElementById('postContentInput');
  if (contentInput) {
    contentInput.focus();
    document.execCommand(command, false, value);
    updatePreview();
  }
}

function showLinkDialog() {
  const url = prompt('Nhập URL siêu liên kết:');
  if (url) {
    document.execCommand('createLink', false, url);
    updatePreview();
  }
}

function applyTextColor(color) {
  document.execCommand('foreColor', false, color);
  updatePreview();
  hideColorDropdowns();
}

function applyBgColor(color) {
  document.execCommand('backColor', false, color);
  updatePreview();
  hideColorDropdowns();
}

function toggleColorDropdown(type) {
  const textOptions = document.getElementById('textColorOptions');
  const bgOptions = document.getElementById('bgColorOptions');

  if (type === 'textColor') {
    textOptions.style.display = textOptions.style.display === 'block' ? 'none' : 'block';
    bgOptions.style.display = 'none';
  } else if (type === 'bgColor') {
    bgOptions.style.display = bgOptions.style.display === 'block' ? 'none' : 'block';
    textOptions.style.display = 'none';
  }
}

function hideColorDropdowns() {
  const textOptions = document.getElementById('textColorOptions');
  const bgOptions = document.getElementById('bgColorOptions');
  if (textOptions) textOptions.style.display = 'none';
  if (bgOptions) bgOptions.style.display = 'none';
}

function updatePreview() {
  const postContentInput = document.getElementById('postContentInput');
  const previewArea = document.getElementById('previewArea');
  if (postContentInput && previewArea) {
    const contentHTML = postContentInput.innerHTML;
    if (!contentHTML.trim() || contentHTML === '<br>' || contentHTML === '<div><br></div>') {
      previewArea.innerHTML = '<em>Nội dung sẽ hiển thị ở đây...</em>';
    } else {
      previewArea.innerHTML = contentHTML;
    }
  }
}

function resetPostForm() {
  document.getElementById('createPostForm').reset();
  const contentDiv = document.getElementById('postContentInput');
  if (contentDiv) contentDiv.innerHTML = '';
  updatePreview();
}

function setupEditorEvents() {
  const postContentInput = document.getElementById('postContentInput');
  if (postContentInput) {
    postContentInput.addEventListener('input', updatePreview);
  }
}

function toggleChatbot() {
  const chatWin = document.getElementById('chatbotWindow');
  chatWin.style.display = (chatWin.style.display === 'flex') ? 'none' : 'flex';
}

function sendChatMessage() {
  const input = document.getElementById('chatInput');
  const msgContainer = document.getElementById('chatMessages');
  const text = input.value.trim();
  if (!text) return;

  const userMsg = document.createElement('div');
  userMsg.className = 'msg msg-user';
  userMsg.textContent = text;
  msgContainer.appendChild(userMsg);
  input.value = '';

  setTimeout(() => {
    const botMsg = document.createElement('div');
    botMsg.className = 'msg msg-bot';
    botMsg.textContent = `Hệ thống đã nhận câu hỏi: "${text}". Trợ lý sẽ cập nhật thông tin sớm nhất!`;
    msgContainer.appendChild(botMsg);
    msgContainer.scrollTop = msgContainer.scrollHeight;
  }, 400);
}

function handleChatKeyPress(e) {
  if (e.key === 'Enter') sendChatMessage();
}