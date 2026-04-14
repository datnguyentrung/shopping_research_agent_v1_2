import gzip
import json
import csv
import re
import os
import glob
from itertools import islice
from collections import defaultdict
import pyarrow as pa
import pyarrow.parquet as pq

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
METADATA_GLOB = r'D:\Thực tập MB\data\meta_Clothing_Shoes_and_Jewelry.jsonl.gz'
CATEGORY_FILE = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\category.csv'
OUTPUT_DIR    = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\parquet_chunks_v2'
os.makedirs(OUTPUT_DIR, exist_ok=True)

BUFFER_SIZE       = 500_000
MAX_CATEGORY_SCAN = 5   # Số lượng category item tối đa cần duyệt mỗi sản phẩm

# ─────────────────────────────────────────────
# TEXT CLEANING
# ─────────────────────────────────────────────
_RE_HTML    = re.compile(r'<[^>]+>')
_RE_BRACKET = re.compile(r'[\[\(][^\]\)]{0,40}[\]\)]')
_RE_SPECIAL = re.compile(r'[^\w\s\-\'\,\.]')
_RE_SPACES  = re.compile(r'\s{2,}')
_RE_PIPE    = re.compile(r'\s*[\|\/\\]\s*.*$')

def clean_title(title: str) -> str:
    if not title or not isinstance(title, str):
        return ""
    t = _RE_HTML.sub(' ', title)
    t = _RE_PIPE.sub('', t)
    t = _RE_BRACKET.sub(' ', t)
    t = _RE_SPECIAL.sub(' ', t)
    t = _RE_SPACES.sub(' ', t)
    return t.strip()

def load_categories(category_file: str):
    category_map  = {}
    category_list = []

    try:
        with open(category_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                depth_val = int(row['Depth'])
                if depth_val > 5:
                    continue

                row['Depth'] = depth_val
                row['children'] = []  # GIỮ NGUYÊN LÀ LIST
                cat_id = row['Category ID']
                category_list.append(row)
                category_map[cat_id] = row

        # Gắn con vào cha
        for cat_id, cat_data in category_map.items():
            parent_id = cat_data['Parent ID']
            if parent_id and str(parent_id).strip().lower() not in ('', 'nan', 'root'):
                if parent_id in category_map:
                    category_map[parent_id]['children'].append(cat_data)
                else:
                    print(f"⚠️ Không tìm thấy cha {parent_id} cho danh mục {cat_id}")

    except Exception as e:
        print(f"❌ Lỗi khi đọc file danh mục: {e}")

    # TRẢ VỀ DƯỚI DẠNG LIST (Không dùng dict)
    root_nodes = [
        cat_data for cat_data in category_map.values()
        if str(cat_data.get('Parent ID', '')).strip().lower() in ('', 'nan', 'root')
    ]

    return category_map, category_list, root_nodes


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def generate_pro_v3():
    meta_files = sorted(glob.glob(METADATA_GLOB))
    if not meta_files:
        print(f"❌ Không tìm thấy file: {METADATA_GLOB}")
        return

    print(f"\n📂 Tải danh mục...")
    category_map, _, root_nodes = load_categories(CATEGORY_FILE)

    per_cat_count = defaultdict(int)
    total_read    = 0
    total_match   = 0
    total_no_match = 0

    # ✅ CẢI TIẾN #2: 3 list riêng biệt theo cột thay vì list-of-lists
    # → build pa.table() trực tiếp, không qua pandas DataFrame
    buf_ids:   list[str] = []
    buf_names: list[str] = []
    buf_depths: list[int] = []
    buf_titles: list[str] = []
    chunk_id = 0

    def save_chunk():
        nonlocal chunk_id
        if not buf_ids:
            return

        # ✅ CẢI TIẾN #2 (tiếp): build PyArrow table trực tiếp
        table = pa.table({
            'category_id':   pa.array(buf_ids,    type=pa.string()),
            'category_name': pa.array(buf_names,  type=pa.string()),
            'depth':         pa.array(buf_depths, type=pa.int32()),
            'search_query':  pa.array(buf_titles,  type=pa.string()),
        })

        file_path = os.path.join(OUTPUT_DIR, f'cleaned_chunk_{chunk_id}.parquet')
        pq.write_table(table, file_path, compression='snappy')
        print(f"   ✅ Đã lưu: {file_path} ({len(buf_ids):,} dòng)")

        buf_ids.clear()
        buf_names.clear()
        buf_depths.clear()
        buf_titles.clear()
        chunk_id += 1

    # ──────────────────────────────────────────
    # VÒNG CHÍNH
    # ──────────────────────────────────────────
    for meta_file in meta_files:
        fname = os.path.basename(meta_file)
        print(f"\n📖 Đang đọc: {fname}")

        with gzip.open(meta_file, 'rt', encoding='utf-8', errors='replace') as f:
            for line in f:
                # ✅ CẢI TIẾN #3: except cụ thể — nhanh hơn và không nuốt lỗi khác
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                total_read += 1
                if total_read % 100_000 == 0:
                    print(f"   - Đã đọc {total_read:>10,} dòng | Match: {total_match:>8,}")

                # 1. EARLY SKIP: Lấy title thô, nếu rỗng bỏ qua luôn
                raw_title = data.get('title', '')
                if not raw_title:
                    continue

                # Lấy category thô, nếu rỗng bỏ qua luôn
                raw_cat = data.get('categories', data.get('category', []))
                if not raw_cat:
                    continue

                # 2. XỬ LÝ LIST OF LISTS CỦA AMAZON
                if isinstance(raw_cat, list) and len(raw_cat) > 0 and isinstance(raw_cat[0], list):
                    category = raw_cat[0]
                else:
                    category = [raw_cat] if isinstance(raw_cat, str) else raw_cat

                # 3. LOGIC MATCHING CHUỖI CON (Chạy trước khi Clean Text)
                current_nodes = root_nodes
                deepest_match = None

                for cat_item in islice(category, MAX_CATEGORY_SCAN):
                    match_found = False
                    for node in current_nodes:
                        if cat_item in node['Name']:
                            deepest_match = node
                            current_nodes = node['children']
                            match_found = True
                            break
                    if not match_found:
                        break

                # 4. LAZY CLEANING: Chỉ clean text NẾU match thành công
                if deepest_match:
                    clean_t = clean_title(raw_title)
                    if not clean_t:  # Nhỡ clean xong chuỗi biến mất (chỉ toàn ký tự rác)
                        continue

                    total_match += 1
                    cat_id = deepest_match['Category ID']
                    cat_name = deepest_match['Name']
                    cat_depth = deepest_match['Depth']
                    per_cat_count[cat_id] += 1

                    buf_ids.append(cat_id)
                    buf_names.append(cat_name)
                    buf_depths.append(cat_depth)
                    buf_titles.append(clean_t)  # Lưu chuỗi đã clean

                    if len(buf_ids) >= BUFFER_SIZE:
                        save_chunk()
                else:
                    total_no_match += 1

    # Lưu phần còn lại trong buffer
    save_chunk()

    print(f"\n{'=' * 30} HOÀN TẤT {'=' * 30}")
    print(f"Tổng đọc  : {total_read:,}")
    print(f"Tổng match: {total_match:,}")
    print(f"Không match: {total_no_match:,}")
    print(f"Số chunk  : {chunk_id}")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    generate_pro_v3()