@echo off
REM ============================================
REM Full RAG Pipeline: Crawl → Chunk → Embed
REM ============================================

echo [1/4] Crawling Lore + Books + Characters + Quests...
python -c "
import sys; sys.path.insert(0, '.')
from crawl_enhanced import get_all_pages_in_category, get_page_content_and_meta, extract_infobox_metadata, clean_wikitext, init_cache
import json, time
from pathlib import Path

api_url = 'https://genshin-impact.fandom.com/api.php'
categories = ['Lore', 'Books', 'Playable_Characters', 'Archon_Quests', 'Story_Quests', 'World_Quests']
conn = init_cache('crawl_cache_lore.db')
all_chunks_raw = []
seen = set()

for cat in categories:
    print(f'Category: {cat}')
    members = get_all_pages_in_category(cat, api_url)
    print(f'  -> {len(members)} pages')
    for m in members:
        title = m['title']
        if title in seen: continue
        seen.add(title)
        page = get_page_content_and_meta(title, api_url)
        if not page or not page['wikitext']: continue
        infobox = extract_infobox_metadata(page['wikitext'])
        clean = clean_wikitext(page['wikitext'])
        conn.execute('''INSERT OR REPLACE INTO pages VALUES (?, ?, ?, ?, datetime('now'))''', (title, page['pageid'], page['last_rev_id'], page['last_modified']))
        conn.commit()
        all_chunks_raw.append({'title': page['title'], 'pageid': page['pageid'], 'wikitext': page['wikitext'], 'clean_text': clean, 'infobox': infobox, 'source_category': cat, 'lang': 'en', 'url': f'https://genshin-impact.fandom.com/wiki/{title.replace(\" \", \"_\")}'})
        time.sleep(0.1)

out = Path('genshin_pages_lore.json')
out.write_text(json.dumps(all_chunks_raw, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Done: {len(all_chunks_raw)} pages saved')
conn.close()
"

echo [2/4] Chunking...
python chunk.py --input genshin_pages_lore.json --output genshin_chunks_lore.json

echo [3/4] Embedding...
python embed.py ingest --input genshin_chunks_lore.json --collection genshin_lore --rebuild

echo [4/4] Done!
echo.
echo Now run: python app.py
pause
