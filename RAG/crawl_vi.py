# ============================================================
# Credit: Code được hỗ trợ bởi Claude Code (Anthropic)
# ============================================================

import requests
import json
import re
import time
import mwparserfromhell
from tqdm import tqdm

# 1. Endpoint API cho Genshin Impact Wiki Tiếng Việt
API_URL = "https://genshin-impact.fandom.com/vi/api.php"

# 2. Danh sách các Category Tiếng Việt chuyên sâu về Thông tin & Lore
CATEGORIES = [
    # Nhân vật & Kẻ địch
    "Nhân_vật_có_thể_chơi",
    "Kẻ_thù",
    "Sinh_vật",
    
    # Vũ khí & Thánh di vật (mỗi món đều chứa Weapon/Artifact Lore)
    "Vũ_khí",
    "Bộ_Thánh_Di_Vật",
    
    # Nhiệm vụ & Hội thoại Cốt truyện
    "Nhiệm_Vụ",
    "Nhiệm_Vụ_Ma_Thần",
    "Nhiệm_Vụ_Truyền_Thuyết",
    "Nhiệm_Vụ_Thế_Giới",
    "Sự_Kiện_Đồng_Hành",
    
    # Sách báo, Tài liệu & Cốt truyện Teyvat
    "Sách",
    "Cốt_Truyện",
    "Lịch_Sử"
]

def get_all_pages_in_category(category_name):
    """Lấy danh sách tất cả các trang nằm trong một Category tiếng Việt"""
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
                # Chỉ lấy namespace 0 (trang bài viết chính thức)
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
    """Lấy nội dung Wikitext thô của một bài viết tiếng Việt"""
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
    """Làm sạch Wikitext tiếng Việt bằng mwparserfromhell và Regex"""
    if not raw_text:
        return ""
    
    parsed = mwparserfromhell.parse(raw_text)
    
    # Loại bỏ các template không cần thiết (Infobox, Navbox, Gallery)
    for template in parsed.filter_templates():
        if any(bad_tp in template.name.lower() for bad_tp in ["infobox", "navbox", "gallery", "header"]):
            try:
                parsed.remove(template)
            except ValueError:
                pass

    clean_text = parsed.strip_code()
    
    # Regex dọn dẹp các ký tự thừa
    clean_text = re.sub(r'\{\{.*?\}\}', '', clean_text)
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)
    clean_text = re.sub(r'\[\[Category:.*?\]\]', '', clean_text)
    clean_text = re.sub(r'\[\[Thể_loại:.*?\]\]', '', clean_text)
    
    return clean_text.strip()

def chunk_by_sections(clean_text, page_title, category):
    """Cắt nhỏ bài viết tiếng Việt theo các tiêu đề Section (== Mục ==)"""
    chunks = []
    sections = re.split(r'(==+[^=]+==+)', clean_text)
    
    current_heading = "Tổng quan"
    current_content = ""
    
    for part in sections:
        part = part.strip()
        if not part:
            continue
            
        if part.startswith("==") and part.endswith("=="):
            if current_content and len(current_content) > 50:
                chunks.append({
                    "content": f"[{page_title} - {current_heading}]\n{current_content}",
                    "metadata": {
                        "source": "Genshin Impact Wiki Tiếng Việt",
                        "title": page_title,
                        "section": current_heading,
                        "category": category,
                        "language": "vi",
                        "url": f"https://genshin-impact.fandom.com/vi/wiki/{page_title.replace(' ', '_')}"
                    }
                })
                current_content = ""
            current_heading = part.strip("=").strip()
        else:
            current_content += "\n" + part
            
    if current_content and len(current_content) > 50:
        chunks.append({
            "content": f"[{page_title} - {current_heading}]\n{current_content}",
            "metadata": {
                "source": "Genshin Impact Wiki Tiếng Việt",
                "title": page_title,
                "section": current_heading,
                "category": category,
                "language": "vi",
                "url": f"https://genshin-impact.fandom.com/vi/wiki/{page_title.replace(' ', '_')}"
            }
        })
        
    return chunks

def run_pipeline():
    all_rag_chunks = []
    processed_titles = set()
    
    print("=== BẮT ĐẦU CÀO VÀ XỬ LÝ DỮ LIỆU GENSHIN IMPACT (TIẾNG VIỆT) ===")
    
    for category in CATEGORIES:
        print(f"\n[+] Đang lấy danh sách trang thuộc Category: {category}...")
        titles = get_all_pages_in_category(category)
        print(f"-> Tìm thấy {len(titles)} trang.")
        
        for title in tqdm(titles, desc=f"Đang xử lý {category}"):
            if title in processed_titles:
                continue
            processed_titles.add(title)
            
            raw_content = get_page_content(title)
            if not raw_content:
                continue
                
            clean_text = clean_wikitext(raw_content)
            chunks = chunk_by_sections(clean_text, title, category)
            all_rag_chunks.extend(chunks)
            
            # Cào thêm các trang con câu thoại / cốt truyện (nếu có)
            sub_suffixes = ["/Câu_Thoại", "/Cốt_Truyện", "/Thoại"]
            for suffix in sub_suffixes:
                sub_title = title + suffix
                sub_raw = get_page_content(sub_title)
                if sub_raw:
                    sub_clean = clean_wikitext(sub_raw)
                    if sub_clean:
                        sub_chunks = chunk_by_sections(sub_clean, sub_title, f"{category}_Subpage")
                        all_rag_chunks.extend(sub_chunks)
            
            time.sleep(0.1)
            
    # Xuất file JSON dành riêng cho bản Tiếng Việt
    output_filename = "genshin_rag_knowledge_vi.json"
    print(f"\n[+] Đang lưu {len(all_rag_chunks)} chunks vào file {output_filename}...")
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(all_rag_chunks, f, ensure_ascii=False, indent=2)
        
    print(f"=== HOÀN THÀNH! Đã xuất dữ liệu Tiếng Việt ra file {output_filename} ===")

if __name__ == "__main__":
    run_pipeline()