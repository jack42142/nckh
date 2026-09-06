# ============================================================
# Credit: Code được hỗ trợ bởi Claude Code (Anthropic)
# ============================================================

import requests
import json
import re
import time
import mwparserfromhell
from tqdm import tqdm

API_URL = "https://genshin-impact.fandom.com/api.php"

# 1. Danh sách các Category cần cào dữ liệu
CATEGORIES = [
    "Playable_Characters",
    "Weapons",
    "Artifact_Sets",
    "Enemies",
    "Quests"
]

def get_all_pages_in_category(category_name):
    """Lấy danh sách tất cả các trang nằm trong một Category (xử lý cả phân trang)"""
    pages = []
    cmcontinue = ""
    
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category_name}",
            "cmlimit": "max",
            "format": "json"
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
            
        try:
            res = requests.get(API_URL, params=params, timeout=10).json()
            members = res.get("query", {}).get("categorymembers", [])
            for m in members:
                # Chỉ lấy namespace 0 (các trang bài viết chính thức)
                if m["ns"] == 0:
                    pages.append(m["title"])
                    
            if "continue" in res:
                cmcontinue = res["continue"]["cmcontinue"]
            else:
                break
        except Exception as e:
            print(f"\n[!] Lỗi khi lấy danh sách Category {category_name}: {e}")
            break
            
    return pages

def get_page_content(title):
    """Lấy nội dung Wikitext thô của một bài viết"""
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": title,
        "rvprop": "content",
        "format": "json"
    }
    try:
        res = requests.get(API_URL, params=params, timeout=10).json()
        pages = res.get("query", {}).get("pages", {})
        for p_id, p_data in pages.items():
            if "revisions" in p_data:
                return p_data["revisions"][0]["*"]
    except Exception as e:
        print(f"\n[!] Lỗi khi tải bài viết {title}: {e}")
    return None

def clean_wikitext(raw_text):
    """Làm sạch Wikitext bằng mwparserfromhell và Regex"""
    if not raw_text:
        return ""
    
    # Parse cấu trúc wikitext
    parsed = mwparserfromhell.parse(raw_text)
    
    # Loại bỏ các template không dùng đến (như Infobox, Gallery, Navbox)
    for template in parsed.filter_templates():
        # Giữ lại văn bản nếu cần, hoặc xóa các template hệ thống
        if any(bad_tp in template.name.lower() for bad_tp in ["infobox", "navbox", "gallery", "header"]):
            try:
                parsed.remove(template)
            except ValueError:
                pass

    # Chuyển thành văn bản thuần
    clean_text = parsed.strip_code()
    
    # Regex dọn dẹp các ký tự thừa/khoảng trắng thừa
    clean_text = re.sub(r'\{\{.*?\}\}', '', clean_text)  # Xóa template đúp còn sót
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)  # Thu gọn dòng trống
    clean_text = re.sub(r'\[\[Category:.*?\]\]', '', clean_text) # Xóa thẻ category
    
    return clean_text.strip()

def chunk_by_sections(clean_text, page_title, category):
    """Cắt nhỏ bài viết theo Section (Headings) để tối ưu cho RAG"""
    chunks = []
    # Tách bài viết bằng các dấu Section == Title ==
    sections = re.split(r'(==+[^=]+==+)', clean_text)
    
    current_heading = "Overview"
    current_content = ""
    
    for part in sections:
        part = part.strip()
        if not part:
            continue
            
        # Nếu là tiêu đề section
        if part.startswith("==") and part.endswith("=="):
            if current_content and len(current_content) > 50:
                chunks.append({
                    "content": f"[{page_title} - {current_heading}]\n{current_content}",
                    "metadata": {
                        "source": "Genshin Impact Wiki",
                        "title": page_title,
                        "section": current_heading,
                        "category": category,
                        "url": f"https://genshin-impact.fandom.com/wiki/{page_title.replace(' ', '_')}"
                    }
                })
                current_content = ""
            current_heading = part.strip("=").strip()
        else:
            current_content += "\n" + part
            
    # Lưu phần chunk cuối cùng
    if current_content and len(current_content) > 50:
        chunks.append({
            "content": f"[{page_title} - {current_heading}]\n{current_content}",
            "metadata": {
                "source": "Genshin Impact Wiki",
                "title": page_title,
                "section": current_heading,
                "category": category,
                "url": f"https://genshin-impact.fandom.com/wiki/{page_title.replace(' ', '_')}"
            }
        })
        
    return chunks

def run_pipeline():
    all_rag_chunks = []
    processed_titles = set()
    
    print("=== BẮT ĐẦU CÀO VÀ XỬ LÝ DỮ LIỆU GENSHIN IMPACT ===")
    
    for category in CATEGORIES:
        print(f"\n[+] Đang lấy danh sách trang thuộc Category: {category}...")
        titles = get_all_pages_in_category(category)
        print(f"-> Tìm thấy {len(titles)} trang.")
        
        # Dùng tqdm tạo thanh tiến trình
        for title in tqdm(titles, desc=f"Processing {category}"):
            # Tránh cào trùng lặp giữa các category
            if title in processed_titles:
                continue
            processed_titles.add(title)
            
            raw_content = get_page_content(title)
            if not raw_content:
                continue
                
            clean_text = clean_wikitext(raw_content)
            chunks = chunk_by_sections(clean_text, title, category)
            all_rag_chunks.extend(chunks)
            
            # Delay nhẹ 0.1s để không spam API
            time.sleep(0.1)
            
    # Xuất ra file JSON
    output_filename = "genshin_rag_knowledge.json"
    print(f"\n[+] Đang lưu {len(all_rag_chunks)} chunks vào file {output_filename}...")
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(all_rag_chunks, f, ensure_ascii=False, indent=2)
        
    print(f"=== HOÀN THÀNH! Đã xuất thành công dữ liệu cho RAG ===")

if __name__ == "__main__":
    run_pipeline()