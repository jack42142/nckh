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
  initStorage();
  renderPostsList();
  animateElementsOnLoad();
  setupLogoEffect();
  setupEditorEvents();
});

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

function initStorage() {
  if (!localStorage.getItem('user_posts')) {
    localStorage.setItem('user_posts', JSON.stringify(INITIAL_POSTS));
  }
}

function getStoredPosts() {
  return JSON.parse(localStorage.getItem('user_posts')) || [];
}

function savePostsToStorage(posts) {
  localStorage.setItem('user_posts', JSON.stringify(posts));
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

function renderPostsList() {
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
            <button class="btn-danger" onclick="${getOnclickAction('deletePost', post.id)}">Xóa</button>
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
    <div class="post-meta">Danh mục: ${escapeHtmlText(post.category)} \vert{} Ngày đăng: ${escapeHtmlText(post.date)}</div>
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

function deletePost(postId) {
  if (confirm('Bạn có chắc chắn muốn xóa bài viết này không?')) {
    let posts = getStoredPosts();
    posts = posts.filter(p => p.id !== postId);
    savePostsToStorage(posts);
    renderPostsList();

    if (currentActivePostId === postId) {
      currentActivePostId = null;
      document.getElementById('nav-reading').style.display = 'none';
      switchView('posts');
    }
  }
}

function toggleModal(show) {
  document.getElementById('postModal').style.display = show ? 'flex' : 'none';
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

document.getElementById('createPostForm').addEventListener('submit', function (e) {
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
    id: 'post-' + Date.now(),
    title: title,
    category: category,
    date: new Date().toLocaleDateString('vi-VN'),
    content: contentHTML
  };

  const posts = getStoredPosts();
  posts.unshift(newPost);
  savePostsToStorage(posts);

  toggleModal(false);
  resetPostForm();
  renderPostsList();
  readPost(newPost.id);
});

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