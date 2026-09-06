"""
# ============================================================
# Credit: Code được hỗ trợ bởi Claude Code (Anthropic)
# ============================================================

"""
crawl_enhanced.py — Cải tiến từ crawl.py / crawl_vi.py

Cải tiến chính so với bản gốc:
1. Parse Infobox (mwparserfromhell) để trích xuất metadata cấu trúc:
   element, region, weapon_type, rarity, etc.
2. SQLite cache để resume khi crawl bị gián đoạn (lưu title + pageid + last_modified)
3. Lọc nhiễu triệt để hơn: bảng stats (ATK/HP/DEF), drop tables, references, file links
4. Trả về dạng dict đã chuẩn hoá để chunk.py có thể xử lý tiếp

Cú pháp:
    python crawl_enhanced.py                          # mặc định EN
    python crawl_enhanced.py --lang vi                # tiếng Việt
    python crawl_enhanced.py --output my_chunks.json  # file output khác
    python crawl_enhanced.py --no-resume              # crawl lại từ đầu
"""

import argparse
import json
import re
import sqlite3
import time
from pathlib import Path

import mwparserfromhell
import requests
from tqdm import tqdm

API_URL_EN = "https://genshin-impact.fandom.com/api.php"
API_URL_VI = "https://genshin-impact.fandom.com/vi/api.php"

# ----------------------------- CATEGORIES (Lore-focused) -----------------------------

CATEGORIES_EN = [
    # Nhân vật
    "Playable_Characters",
    # Nhiệm vụ cốt truyện (xác minh có trên wiki)
    "Archon_Quests",
    "Story_Quests",
    "World_Quests",
    "Event_Quests",
    # Lore & Tài liệu (xác minh có trên wiki)
    "Books",
    "Lore",
    # Vũ khí & Thánh di vật (chứa Lore riêng)
    "Weapons",
    "Artifact_Sets",
    # Kẻ địch & Boss
    "Enemies",
    "Bosses",
]

CATEGORIES_VI = [
    "Nhân_vật_có_thể_chơi",
    "Nhiệm_Vụ_Ma_Thần",
    "Nhiệm_Vụ_Truyền_Thuyết",
    "Nhiệm_Vụ_Thế_Giới",
    "Sự_Kiện_Đồng_Hành",
    "Sách",
    "Cốt_Truyện",
    "Lịch_Sử",
    "Vũ_khí",
    "Bộ_Thánh_Di_Vật",
    "Kẻ_thù",
    "Sinh_vật",
]

# ----------------------------- FIELDS MONG MUỐN TỪ INFOBOX -----------------------------

# Mapping tên field trong Infobox → tên metadata chuẩn
# Genshin Impact Fandom dùng key tiếng Anh trong infobox, dù bài viết là tiếng Việt
INFOBOX_FIELDS = {
    "vision": "element",
    "element": "element",
    "weapon": "weapon_type",
    "weapontype": "weapon_type",
    "weapon_type": "weapon_type",
    "region": "region",
    "affiliation": "affiliation",
    "rarity": "rarity",
    "constellation": "constellation",
    "birthday": "birthday",
    "occupation": "occupation",
    "species": "species",
    "type": "enemy_type",
    "title": "title",
    "alias": "alias",
    "nation": "region",  # alias phổ biến
}

# ----------------------------- CACHE SQLITE -----------------------------

CACHE_DB = "crawl_cache.db"


def init_cache(db_path: str) -> sqlite3.Connection:
    """Tạo bảng cache nếu chưa có. Lưu: title, pageid, last_rev_id, last_modified, fetched_at"""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pages (
            title TEXT PRIMARY KEY,
            pageid INTEGER,
            last_rev_id INTEGER,
            last_modified TEXT,
            fetched_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS category_members (
            title TEXT PRIMARY KEY,
            category TEXT
        )
        """
    )
    conn.commit()
    return conn


def is_page_fresh(conn: sqlite3.Connection, title: str) -> bool:
    """Kiểm tra xem page đã được cào (bất kỳ rev) chưa. Nếu có rồi thì skip."""
    row = conn.execute(
        "SELECT last_rev_id FROM pages WHERE title = ?", (title,)
    ).fetchone()
    return row is not None


# ----------------------------- API HELPERS -----------------------------


def api_get(params: dict, api_url: str):
    """GET request tới MediaWiki API với error handling cơ bản."""
    try:
        res = requests.get(api_url, params=params, timeout=15)
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        print(f"\n[!] Lỗi request: {e}")
        return {}


def get_all_pages_in_category(category: str, api_url: str) -> list[dict]:
    """Trả về list {title, pageid, last_modified} cho tất cả trang trong category."""
    pages = []
    cmcontinue = ""
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": "max",
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = api_get(params, api_url)
        for m in data.get("query", {}).get("categorymembers", []):
            if m["ns"] == 0:
                pages.append({"title": m["title"], "pageid": m.get("pageid")})
        if "continue" in data:
            cmcontinue = data["continue"]["cmcontinue"]
        else:
            break
    return pages


def get_page_content_and_meta(title: str, api_url: str) -> dict | None:
    """Lấy wikitext + pageid + last_modified + last_rev_id của một trang."""
    params = {
        "action": "query",
        "prop": "revisions|info",
        "titles": title,
        "rvprop": "content|timestamp",
        "format": "json",
        "inprop": "lastmodified",
        "rvlimit": 1,
    }
    data = api_get(params, api_url)
    pages = data.get("query", {}).get("pages", {})
    for _, p_data in pages.items():
        if "revisions" not in p_data:
            return None
        rev = p_data["revisions"][0]
        return {
            "title": p_data.get("title", title),
            "pageid": p_data.get("pageid"),
            "last_modified": p_data.get("lastmodified") or rev.get("timestamp"),
            "last_rev_id": rev.get("revid"),
            "wikitext": rev.get("*", ""),
        }
    return None


# ----------------------------- INFOBOX PARSING -----------------------------


def extract_infobox_metadata(wikitext: str) -> dict:
    """Parse wikitext bằng mwparserfromhell, tìm Infobox và lấy các trường metadata."""
    metadata = {}
    if not wikitext:
        return metadata

    parsed = mwparserfromhell.parse(wikitext)
    for template in parsed.filter_templates():
        tpl_name = template.name.strip().lower()
        # Genshin Impact Fandom dùng "Infobox character", "Infobox weapon", v.v.
        if "infobox" not in tpl_name:
            continue
        for param in template.params:
            key = param.name.strip().lower()
            value = param.value.strip_code().strip()
            if key in INFOBOX_FIELDS and value:
                metadata[INFOBOX_FIELDS[key]] = value
    return metadata


# ----------------------------- CLEANING -----------------------------


# Loại bỏ các block nhiễu có thể xuất hiện trong wikitext
NOISE_TEMPLATES = {
    "infobox",
    "navbox",
    "gallery",
    "header",
    "footer",
    "stub",
    "clear",
    "switch",
    "t",
    "lang",
    "translation",
    "cite",
    "ref",
    "small",
    "icon",
    "color",
    "quote",
    "tab",
}

# Bảng stats vũ khí (cột ATK/HP/DEF) — loại bỏ dòng chứa header sau:
STATS_HEADER_RE = re.compile(
    r"^\s*(?:Lvl|Level|Lv|Phase|ATK|Base ATK|HP|DEF|SECONDARY STAT|Secondary Stat|1st Ascension|2nd Ascension|3rd Ascension|4th Ascension|5th Ascension|6th Ascension)\s*$",
    re.IGNORECASE,
)


def clean_wikitext(raw: str) -> str:
    """Làm sạch wikitext: bỏ template, tham chiếu, link file, bảng nhiễu."""
    if not raw:
        return ""

    parsed = mwparserfromhell.parse(raw)

    # Bỏ các template không cần cho RAG
    for template in list(parsed.filter_templates()):
        tpl_name = template.name.strip().lower()
        if any(bad in tpl_name for bad in NOISE_TEMPLATES):
            try:
                parsed.remove(template)
            except ValueError:
                pass

    text = parsed.strip_code()

    # Bỏ thẻ category còn sót
    text = re.sub(r"\[\[(?:Category|Thể_loại):.*?\]\]", "", text, flags=re.IGNORECASE)
    # Bỏ tham chiếu <ref>...</ref> và <ref ... />
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<ref[^>]*/>", "", text, flags=re.IGNORECASE)
    # Bỏ file/Image link
    text = re.sub(r"\[\[(?:File|Tập_tin|Image|Hình):.*?\]\]", "", text, flags=re.IGNORECASE)
    # Bỏ các bảng stats (line-by-line): nếu gặp header thì skip dòng đó và các dòng số tiếp theo
    lines = text.split("\n")
    cleaned_lines = []
    in_stats_table = False
    for line in lines:
        if STATS_HEADER_RE.match(line):
            in_stats_table = True
            continue
        if in_stats_table:
            # Bỏ qua dòng số/dấu phân cách
            if re.match(r"^\s*[\d,\.\-\+]+\s*$", line) or set(line.strip()) <= {"-", "=", " "}:
                continue
            in_stats_table = False
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    # Bỏ template còn sót dạng {{...}} (đơn giản, không lồng nhau)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    # Thu gọn khoảng trắng
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ----------------------------- PIPELINE -----------------------------


def run(lang: str, output_path: str, use_resume: bool = True):
    api_url = API_URL_VI if lang == "vi" else API_URL_EN
    categories = CATEGORIES_VI if lang == "vi" else CATEGORIES_EN

    cache_path = f"crawl_cache_{lang}.db"
    conn = init_cache(cache_path)

    all_chunks = []
    seen_titles = set()
    stats = {"categories": 0, "pages_found": 0, "pages_skipped": 0, "pages_fetched": 0}

    print(f"=== BẮT ĐẦU CRAWL ({lang.upper()}) — {'RESUME' if use_resume else 'FRESH'} ===")

    for cat in categories:
        print(f"\n[+] Category: {cat}")
        members = get_all_pages_in_category(cat, api_url)
        print(f"    -> {len(members)} trang")
        stats["pages_found"] += len(members)
        stats["categories"] += 1

        for m in tqdm(members, desc=cat, unit="page"):
            title = m["title"]
            if title in seen_titles:
                continue
            seen_titles.add(title)

            if use_resume and is_page_fresh(conn, title):
                stats["pages_skipped"] += 1
                continue

            page = get_page_content_and_meta(title, api_url)
            if not page or not page["wikitext"]:
                continue

            infobox_meta = extract_infobox_metadata(page["wikitext"])
            clean_text = clean_wikitext(page["wikitext"])

            # Lưu cache để lần sau skip
            conn.execute(
                """INSERT OR REPLACE INTO pages
                   (title, pageid, last_rev_id, last_modified, fetched_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                (
                    title,
                    page["pageid"],
                    page["last_rev_id"],
                    page["last_modified"],
                ),
            )
            conn.commit()
            stats["pages_fetched"] += 1

            all_chunks.append(
                {
                    "title": page["title"],
                    "pageid": page["pageid"],
                    "wikitext": page["wikitext"],
                    "clean_text": clean_text,
                    "infobox": infobox_meta,
                    "source_category": cat,
                    "lang": lang,
                    "url": f"{api_url.split('/api.php')[0]}/wiki/{title.replace(' ', '_')}",
                }
            )

            time.sleep(0.1)  # tránh spam API

    # Lưu output
    out_path = Path(output_path)
    out_path.write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== THỐNG KÊ ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"\n[+] Đã lưu {len(all_chunks)} trang vào {out_path}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Crawl Genshin Impact Wiki (EN/VI)")
    parser.add_argument(
        "--lang", choices=["en", "vi"], default="en", help="Ngôn ngữ (mặc định: en)"
    )
    parser.add_argument(
        "--output",
        default="genshin_rag_pages_en.json",
        help="File output JSON (mặc định: genshin_rag_pages_en.json)",
    )
    parser.add_argument(
        "--no-resume", action="store_true", help="Bỏ qua cache, crawl lại từ đầu"
    )
    args = parser.parse_args()

    if not args.no_resume:
        # Tự động suffix file output theo ngôn ngữ nếu user dùng default
        if args.output == "genshin_rag_pages_en.json":
            args.output = f"genshin_rag_pages_{args.lang}.json"

    run(args.lang, args.output, use_resume=not args.no_resume)


if __name__ == "__main__":
    main()
