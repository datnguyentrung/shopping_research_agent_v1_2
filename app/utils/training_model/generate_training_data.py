"""
generate_training_data.py
=========================
Đọc nhiều file Amazon metadata (jsonl.gz) từ nhiều category,
trích xuất product title → search_query, map sang danh mục công ty.

Cải tiến:
  - Đọc nhiều file metadata cùng lúc (glob pattern)
  - Lấy title + description snippet làm query (đa dạng hơn)
  - Clean title kỹ (bỏ HTML, noise, brand prefix thừa)
  - Match bằng Amazon category field (O(1)) + text fallback
  - Sinh thêm query variation cho nhãn hiếm (< MIN_SAMPLES_THRESHOLD)
  - Progress bar + báo cáo chi tiết cuối
"""

import gzip
import json
import csv
import re
import os
import glob
from collections import defaultdict

# ─────────────────────────────────────────────
# CẤU HÌNH
# ─────────────────────────────────────────────
METADATA_GLOB  = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\meta_Clothing_Shoes_and_Jewelry.json.gz'

CATEGORY_FILE  = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\category.csv'
OUTPUT_FILE    = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\training_data.csv'

# Ngưỡng nhãn hiếm — sẽ sinh thêm variation nếu dưới mức này
MIN_SAMPLES_THRESHOLD = 500
# Giới hạn mẫu tối đa mỗi nhãn (tránh dominate)
MAX_SAMPLES_PER_CAT   = 15000
# Buffer flush
BUFFER_SIZE = 10_000

# ─────────────────────────────────────────────
# TỪ ĐIỂN SYNONYM — bổ sung cho nhãn hiếm/đặc thù
# ─────────────────────────────────────────────
SYNONYMS = {
    "Furisode Kimonos":               ["furisode", "coming of age kimono", "seijin no hi"],
    "Tomesode & Houmongi Kimonos":    ["tomesode", "houmongi", "homongi", "formal kimono"],
    "Iromuji Kimonos":                ["iromuji", "single color kimono", "plain kimono"],
    "Komon Kimonos":                  ["komon", "casual kimono"],
    "Bridal Kimonos":                 ["shiromuku", "uchikake", "wedding kimono"],
    "Kimono Coats":                   ["kimono coat", "michiyuki"],
    "Kimono Outerwear":               ["kimono cardigan", "kimono robe", "kimono wrap"],
    "Haori Jackets":                  ["haori", "japanese jacket"],
    "Yukata":                         ["yukata", "festival kimono", "summer kimono"],
    "Hakama Trousers":                ["hakama", "kendo pants", "aikido pants"],
    "Casual Kimonos":                 ["casual kimono", "everyday kimono"],
    "Baptism & Communion Dresses":    ["baptism dress", "christening dress", "communion dress"],
    "Dirndls":                        ["dirndl", "oktoberfest dress", "bavarian dress"],
    "Saris & Lehengas":               ["sari", "saree", "lehenga", "salwar"],
    "Ghillie Suits":                  ["ghillie suit", "sniper suit", "camouflage ghillie"],
    "Chaps":                          ["chaps", "leather chaps", "cowboy chaps", "rodeo chaps"],
    "Bicycle Skinsuits":              ["skinsuit", "aero suit", "triathlon suit", "trisuit"],
    "Bicycle Bibs":                   ["bib shorts", "cycling bib", "bib tights"],
    "Bicycle Tights":                 ["cycling tights", "bike tights", "bicycle tights"],
    "Bicycle Jerseys":                ["cycling jersey", "bike jersey", "bicycle jersey"],
    "Bicycle Activewear":             ["cycling wear", "bicycle activewear"],
    "Snow Pants & Suits":             ["snow pants", "ski pants", "snowsuit", "ski suit"],
    "Hunting & Tactical Pants":       ["tactical pants", "hunting pants", "camo pants"],
    "Hunting & Fishing Vests":        ["hunting vest", "fishing vest", "tackle vest"],
    "Motorcycle Suits":               ["motorcycle suit", "racing leathers"],
    "Motorcycle Jackets":             ["motorcycle jacket", "biker jacket", "moto jacket"],
    "Motorcycle Pants":               ["motorcycle pants", "moto pants", "riding pants"],
    "Martial Arts Uniforms":          ["gi", "dobok", "judogi", "karategi", "bjj gi"],
    "Martial Arts Shorts":            ["mma shorts", "bjj shorts", "grappling shorts"],
    "Boxing Shorts":                  ["boxing shorts", "boxing trunks"],
    "Wrestling Uniforms":             ["wrestling singlet", "wrestling uniform"],
    "Flight Suits":                   ["flight suit", "pilot suit", "aviator suit"],
    "Officiating Uniforms":           ["referee shirt", "umpire uniform"],
    "Garter Belts":                   ["garter belt", "suspender belt"],
    "Long Johns":                     ["long johns", "thermal underwear", "base layer"],
    "Hosiery":                        ["hosiery", "nylons", "pantyhose", "stockings"],
    "Food Service Uniforms":          ["chef uniform", "kitchen uniform", "server apron"],
    "Security Uniforms":              ["security guard uniform", "security shirt"],
    "Contractor Pants & Coveralls":   ["coveralls", "work coveralls", "mechanic coveralls"],
    "Rain Suits":                     ["rain suit", "waterproof suit"],
    "Rain Pants":                     ["rain pants", "waterproof pants"],
    "Paintball Clothing":             ["paintball pants", "paintball jersey"],
}

# ─────────────────────────────────────────────
# CLEAN TITLE
# ─────────────────────────────────────────────
# Pattern compile 1 lần
_RE_HTML     = re.compile(r'<[^>]+>')
_RE_NOISE    = re.compile(r'\b(pack|set|lot|bundle|qty|quantity|piece|count)\s+of\s+\d+\b', re.I)
_RE_BRACKET  = re.compile(r'[\[\(][^\]\)]{0,40}[\]\)]')  # bỏ (Size: M), [Color: Blue]...
_RE_SPECIAL  = re.compile(r'[^\w\s\-\'\,\.]')
_RE_SPACES   = re.compile(r'\s{2,}')
_RE_PIPE     = re.compile(r'\s*[\|\/\\]\s*.*$')           # bỏ hết sau "|" hay "/"

def clean_title(title: str) -> str:
    if not title or not isinstance(title, str):
        return ""
    t = _RE_HTML.sub(' ', title)
    t = _RE_PIPE.sub('', t)          # bỏ suffix kiểu "Product Name | Brand"
    t = _RE_BRACKET.sub(' ', t)      # bỏ nội dung trong ngoặc ngắn
    t = _RE_NOISE.sub(' ', t)
    t = _RE_SPECIAL.sub(' ', t)
    t = _RE_SPACES.sub(' ', t)
    return t.strip()


def extract_desc_snippet(desc_field) -> str:
    """Lấy tối đa 20 từ đầu của description làm query bổ sung."""
    if not desc_field:
        return ""
    if isinstance(desc_field, list):
        text = ' '.join(str(x) for x in desc_field if x)
    else:
        text = str(desc_field)
    text = _RE_HTML.sub(' ', text)
    text = _RE_SPECIAL.sub(' ', text)
    words = text.split()
    return ' '.join(words[:20]).strip()


# ─────────────────────────────────────────────
# LOAD CATEGORIES
# ─────────────────────────────────────────────
STOP_WORDS = {
    'and', 'or', 'the', 'for', 'of', 'in', 'a', 'an',
    'clothing', 'accessories', 'apparel', 'products',
    'men', 'women', 'unisex', 'wear',
}

def load_categories(file_path):
    categories = []
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            original_name = row['name'].strip()
            if not original_name:
                continue

            clean_name = original_name.lower()
            words      = re.findall(r'\w+', clean_name)
            base_kws   = [w for w in words if w not in STOP_WORDS and len(w) > 2]
            extra_syns = SYNONYMS.get(original_name, [])

            short_kws = list(set(
                [kw for kw in base_kws if len(kw.split()) == 1] +
                [s.lower() for s in extra_syns if len(s.split()) == 1]
            ))
            long_kws = list(set(
                [kw for kw in base_kws if len(kw.split()) > 1] +
                [s.lower() for s in extra_syns if len(s.split()) > 1]
            ))

            compiled_regex = None
            if short_kws:
                pattern = r'\b(' + '|'.join(re.escape(k) for k in short_kws) + r')\b'
                compiled_regex = re.compile(pattern, re.IGNORECASE)

            amazon_keys = [clean_name] + [s.lower() for s in extra_syns]

            categories.append({
                'id':            row['id'],
                'original_name': original_name,
                'long_kws':      long_kws,
                'short_kws':     short_kws,
                'compiled_regex': compiled_regex,
                'amazon_keys':   amazon_keys,
            })
    return categories


def build_lookup_indexes(categories):
    """Build O(1) lookup structures."""
    amazon_lookup = {}   # amazon_category_string → cat
    word_index    = defaultdict(list)
    phrase_index  = defaultdict(list)

    for cat in categories:
        for ak in cat['amazon_keys']:
            if ak not in amazon_lookup:
                amazon_lookup[ak] = cat
        for kw in cat['short_kws']:
            word_index[kw.lower()].append(cat)
        for ph in cat['long_kws']:
            phrase_index[ph.lower()].append(cat)

    return amazon_lookup, word_index, phrase_index


# ─────────────────────────────────────────────
# MATCHING
# ─────────────────────────────────────────────
def match_by_amazon_cat(amazon_cats, amazon_lookup):
    matched = {}
    for c in amazon_cats:
        key = c.lower().strip()
        if key in amazon_lookup:
            cat = amazon_lookup[key]
            matched[cat['id']] = cat
    return list(matched.values())


def match_by_text(full_text, word_index, phrase_index):
    matched = {}
    tl = full_text.lower()

    for phrase, cats in phrase_index.items():
        if phrase in tl:
            for cat in cats:
                matched[cat['id']] = cat

    words = set(re.findall(r'\b\w+\b', tl))
    for word in words:
        if word in word_index:
            for cat in word_index[word]:
                matched[cat['id']] = cat

    return list(matched.values())


# ─────────────────────────────────────────────
# QUERY VARIATION — cho nhãn hiếm
# ─────────────────────────────────────────────
def generate_variations(title: str) -> list:
    """
    Sinh các biến thể query đơn giản từ title:
    1. title gốc
    2. bỏ 2 từ đầu (thường là brand)
    3. bỏ 2 từ cuối (thường là spec)
    4. lấy 4 từ giữa
    """
    words = title.split()
    variants = [title]

    if len(words) > 4:
        variants.append(' '.join(words[2:]))       # bỏ brand đầu
    if len(words) > 4:
        variants.append(' '.join(words[:-2]))      # bỏ spec cuối
    if len(words) > 6:
        mid = len(words) // 2
        variants.append(' '.join(words[mid-2:mid+2]))

    # Dedup, loại quá ngắn
    seen = set()
    result = []
    for v in variants:
        v = v.strip()
        if v and len(v.split()) >= 3 and v not in seen:
            seen.add(v)
            result.append(v)
    return result


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def generate():
    # Tìm tất cả file metadata
    meta_files = sorted(glob.glob(METADATA_GLOB))
    if not meta_files:
        print(f"❌ Không tìm thấy file metadata tại: {METADATA_GLOB}")
        print("   Đảm bảo file đặt tên dạng: meta_<Category>.jsonl.gz")
        return

    print(f"✅ Tìm thấy {len(meta_files)} file metadata:")
    for f in meta_files:
        print(f"   - {os.path.basename(f)}")

    # Load categories
    print(f"\n📂 Tải danh mục từ: {CATEGORY_FILE}")
    categories = load_categories(CATEGORY_FILE)
    amazon_lookup, word_index, phrase_index = build_lookup_indexes(categories)
    print(f"   {len(categories)} nhãn | {len(word_index)} word keys | {len(phrase_index)} phrase keys")

    # Counters
    per_cat_count = defaultdict(int)   # đếm số mẫu mỗi nhãn
    per_cat_rows  = defaultdict(list)  # lưu rows để sau generate variation
    total_read    = 0
    total_match   = 0
    amazon_hits   = 0
    text_hits     = 0

    # Đọc từng file
    for meta_file in meta_files:
        fname = os.path.basename(meta_file)
        print(f"\n📖 Đang đọc: {fname}")
        file_count = 0

        with gzip.open(meta_file, 'rt', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                total_read += 1
                file_count += 1

                # Lấy title
                title = clean_title(data.get('title', ''))
                if not title or len(title.split()) < 3:
                    continue

                # Lấy description snippet (bổ sung context cho matching)
                desc_snippet = extract_desc_snippet(data.get('description', ''))

                # Amazon category field
                amazon_cats = data.get('category', [])
                if isinstance(amazon_cats, str):
                    amazon_cats = [amazon_cats]

                # Match bước 1: Amazon category
                matched_cats = match_by_amazon_cat(amazon_cats, amazon_lookup)
                if matched_cats:
                    amazon_hits += 1
                else:
                    # Match bước 2: text fallback (title + desc)
                    full_text = title + ' ' + desc_snippet
                    matched_cats = match_by_text(full_text, word_index, phrase_index)
                    if matched_cats:
                        text_hits += 1

                # Ghi rows (chưa flush ngay — gom vào per_cat_rows)
                for cat in matched_cats:
                    cid = cat['id']
                    if per_cat_count[cid] < MAX_SAMPLES_PER_CAT:
                        per_cat_rows[cid].append({
                            'category_id':   cid,
                            'category_name': cat['original_name'],
                            'search_query':  title,
                        })
                        per_cat_count[cid] += 1
                        total_match += 1

                        # Nếu có desc snippet và nhãn còn thiếu → thêm dòng desc
                        if (desc_snippet
                                and len(desc_snippet.split()) >= 4
                                and per_cat_count[cid] < MAX_SAMPLES_PER_CAT):
                            per_cat_rows[cid].append({
                                'category_id':   cid,
                                'category_name': cat['original_name'],
                                'search_query':  desc_snippet,
                            })
                            per_cat_count[cid] += 1
                            total_match += 1

                if file_count % 200_000 == 0:
                    print(f"   {file_count:>8,} dòng | matches tích lũy: {total_match:,}")

        print(f"   ✓ Xong {fname}: {file_count:,} dòng")

    # ── Sinh thêm variation cho nhãn hiếm ──
    print(f"\n🔧 Sinh variation cho nhãn có < {MIN_SAMPLES_THRESHOLD} mẫu ...")
    variation_added = 0
    for cid, rows in per_cat_rows.items():
        current = per_cat_count[cid]
        if current >= MIN_SAMPLES_THRESHOLD:
            continue

        need = MIN_SAMPLES_THRESHOLD - current
        # Lấy các title duy nhất đã có → sinh variation
        existing_titles = list({r['search_query'] for r in rows})
        candidates = []
        for t in existing_titles:
            for v in generate_variations(t):
                if v not in {r['search_query'] for r in rows}:
                    candidates.append(v)
            if len(candidates) >= need * 2:
                break

        cat_name = rows[0]['category_name'] if rows else cid
        added = 0
        for v in candidates:
            if added >= need:
                break
            per_cat_rows[cid].append({
                'category_id':   cid,
                'category_name': cat_name,
                'search_query':  v,
            })
            added += 1

        variation_added += added
        per_cat_count[cid] += added

    print(f"   ✓ Đã thêm {variation_added:,} variation rows")

    # ── Ghi toàn bộ ra CSV ──
    print(f"\n💾 Ghi file output: {OUTPUT_FILE}")
    total_written = 0
    with open(OUTPUT_FILE, mode='w', encoding='utf-8', newline='') as f_out:
        writer = csv.writer(f_out)
        writer.writerow(['category_id', 'category_name', 'search_query'])

        buffer = []
        for rows in per_cat_rows.values():
            for row in rows:
                buffer.append([row['category_id'], row['category_name'], row['search_query']])
                total_written += 1
                if len(buffer) >= BUFFER_SIZE:
                    writer.writerows(buffer)
                    buffer.clear()
        if buffer:
            writer.writerows(buffer)

    # ── Báo cáo ──
    print(f"\n{'='*55}")
    print(f"  HOÀN THÀNH GENERATE TRAINING DATA")
    print(f"{'='*55}")
    print(f"  Tổng dòng đã đọc      : {total_read:>12,}")
    print(f"  Match Amazon field    : {amazon_hits:>12,}")
    print(f"  Match text fallback   : {text_hits:>12,}")
    print(f"  Variation thêm vào    : {variation_added:>12,}")
    print(f"  Tổng dòng ghi ra      : {total_written:>12,}")
    print(f"  File lưu tại          : {OUTPUT_FILE}")
    print(f"{'='*55}")

    # Top 15 nhãn ít nhất
    sorted_cats = sorted(per_cat_count.items(), key=lambda x: x[1])
    print(f"\n📊 Top 15 nhãn ÍT dữ liệu nhất:")
    cat_name_map = {cat['id']: cat['original_name'] for cat in categories}
    for cid, cnt in sorted_cats[:15]:
        flag = "⚠️ " if cnt < MIN_SAMPLES_THRESHOLD else "  "
        print(f"  {flag}{cnt:>7,}  {cat_name_map.get(cid, cid)}")

    # Nhãn 0 mẫu
    all_ids = {cat['id'] for cat in categories}
    missing = all_ids - set(per_cat_count.keys())
    if missing:
        print(f"\n❌ Nhãn KHÔNG có dữ liệu ({len(missing)} nhãn):")
        for cid in sorted(missing):
            print(f"   ✗ {cat_name_map.get(cid, cid)}")
    else:
        print(f"\n✅ Tất cả {len(categories)} nhãn đều có dữ liệu!")


if __name__ == "__main__":
    generate()