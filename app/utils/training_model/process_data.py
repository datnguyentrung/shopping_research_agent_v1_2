"""
process_data.py
===============
Làm sạch, cân bằng và validate training_data.csv
trước khi đưa vào fine-tuning RoBERTa.

Các bước:
  1. Load & kiểm tra schema
  2. Clean text (bỏ HTML, ký tự lạ, normalize)
  3. Lọc query không hợp lệ (quá ngắn, toàn số, không phải tiếng Anh...)
  4. Dedup (query + category_id)
  5. Cân bằng: cap MAX, đảm bảo MIN bằng cách cảnh báo rõ
  6. Báo cáo chi tiết + phân phối nhãn
  7. Lưu cleaned_training_data.csv
"""

import pandas as pd
import re
import os
import unicodedata
from collections import Counter

# ─────────────────────────────────────────────
# CẤU HÌNH
# ─────────────────────────────────────────────
INPUT_PATH  = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\training_data.csv'
OUTPUT_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\cleaned_training_data.csv'

MAX_SAMPLES_PER_CATEGORY = 10_000   # Cap trên mỗi nhãn
MIN_SAMPLES_WARNING      = 300      # Cảnh báo nếu nhãn < ngưỡng này sau clean
MIN_QUERY_WORDS          = 3        # Tối thiểu 3 từ
MAX_QUERY_WORDS          = 50       # Quá dài → cắt bớt thay vì bỏ
MIN_ALPHA_RATIO          = 0.5      # Tỷ lệ ký tự chữ tối thiểu

# ─────────────────────────────────────────────
# CLEAN TEXT
# ─────────────────────────────────────────────
_RE_HTML    = re.compile(r'<[^>]+>')
_RE_URL     = re.compile(r'https?://\S+|www\.\S+')
_RE_EMAIL   = re.compile(r'\S+@\S+\.\S+')
_RE_SPECIAL = re.compile(r'[^\w\s\-\'\,\.]')
_RE_SPACES  = re.compile(r'\s{2,}')
_RE_REPEAT  = re.compile(r'(.)\1{3,}')   # aaaa → a

def clean_query(text: str) -> str:
    if not isinstance(text, str):
        return ""
    # Normalize unicode (bỏ dấu accent lạ)
    text = unicodedata.normalize('NFKC', text)
    text = _RE_HTML.sub(' ', text)
    text = _RE_URL.sub(' ', text)
    text = _RE_EMAIL.sub(' ', text)
    text = _RE_REPEAT.sub(r'\1', text)      # "loooove" → "love"
    text = _RE_SPECIAL.sub(' ', text)
    text = _RE_SPACES.sub(' ', text)
    return text.strip()


def is_valid_query(text: str) -> bool:
    """Trả về True nếu query hợp lệ để training."""
    if not text:
        return False

    words = text.split()

    # Quá ngắn
    if len(words) < MIN_QUERY_WORDS:
        return False

    # Tỷ lệ ký tự chữ cái quá thấp (query toàn số/ký tự đặc biệt)
    alpha_chars = sum(c.isalpha() for c in text)
    if len(text) > 0 and alpha_chars / len(text) < MIN_ALPHA_RATIO:
        return False

    # Query chỉ là một từ lặp đi lặp lại
    if len(set(w.lower() for w in words)) == 1:
        return False

    return True


def truncate_query(text: str, max_words: int = MAX_QUERY_WORDS) -> str:
    """Cắt bớt query quá dài thay vì bỏ."""
    words = text.split()
    if len(words) > max_words:
        return ' '.join(words[:max_words])
    return text


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def process_data(input_path: str, output_path: str):
    print("=" * 55)
    print("  PROCESS DATA — Làm sạch & cân bằng training data")
    print("=" * 55)

    # ── 1. Load ──
    print(f"\n📂 Tải: {input_path}")
    df = pd.read_csv(input_path, dtype={'category_id': str})
    initial_count = len(df)
    print(f"   Tổng dòng ban đầu: {initial_count:,}")

    required_cols = {'search_query', 'category_id', 'category_name'}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(f"❌ File thiếu cột: {missing_cols}")

    # ── 2. Bỏ dòng null ──
    df = df.dropna(subset=['search_query', 'category_id', 'category_name'])
    after_null = len(df)
    print(f"   Sau bỏ null: {after_null:,} (bỏ {initial_count - after_null:,})")

    # ── 3. Clean text ──
    print("\n🧹 Đang clean query...")
    df['search_query'] = df['search_query'].apply(clean_query)

    # Truncate query quá dài
    df['search_query'] = df['search_query'].apply(truncate_query)

    # ── 4. Filter ──
    print("🔍 Đang lọc query không hợp lệ...")
    valid_mask = df['search_query'].apply(is_valid_query)
    df = df[valid_mask]
    after_filter = len(df)
    print(f"   Sau lọc: {after_filter:,} (bỏ {after_null - after_filter:,})")

    # ── 5. Dedup ──
    print("🔁 Đang xóa trùng lặp...")
    df['_query_lower'] = df['search_query'].str.lower().str.strip()
    df = df.drop_duplicates(subset=['_query_lower', 'category_id'], keep='first')
    df = df.drop(columns=['_query_lower'])
    after_dedup = len(df)
    print(f"   Sau dedup: {after_dedup:,} (bỏ {after_filter - after_dedup:,})")

    # ── 6. Cap & cân bằng ──
    print(f"\n⚖️  Cân bằng dữ liệu (max {MAX_SAMPLES_PER_CATEGORY:,}/nhãn)...")
    sampled_list = []
    cat_counts_before = df.groupby('category_id').size()

    for cat_id, group in df.groupby('category_id'):
        if len(group) > MAX_SAMPLES_PER_CATEGORY:
            sampled_list.append(
                group.sample(n=MAX_SAMPLES_PER_CATEGORY, random_state=42)
            )
        else:
            sampled_list.append(group)

    df_final = pd.concat(sampled_list, ignore_index=True)
    # Shuffle để tránh nhãn bị gom cụm trong file
    df_final = df_final.sample(frac=1, random_state=42).reset_index(drop=True)

    after_balance = len(df_final)
    print(f"   Sau cân bằng: {after_balance:,}")

    # ── 7. Kiểm tra nhãn thiếu dữ liệu ──
    cat_counts_after = df_final.groupby('category_id').size()
    low_cats = cat_counts_after[cat_counts_after < MIN_SAMPLES_WARNING]

    if len(low_cats) > 0:
        print(f"\n⚠️  {len(low_cats)} nhãn có < {MIN_SAMPLES_WARNING} mẫu (cần bổ sung):")
        for cid, cnt in low_cats.sort_values().items():
            cat_name = df_final[df_final['category_id'] == cid]['category_name'].iloc[0]
            print(f"   {cnt:>6,}  [{cid}] {cat_name}")
    else:
        print(f"\n✅ Tất cả nhãn đều có ≥ {MIN_SAMPLES_WARNING} mẫu!")

    # ── 8. Lưu ──
    df_final = df_final[['category_id', 'category_name', 'search_query']]
    df_final.to_csv(output_path, index=False, encoding='utf-8-sig')

    # ── 9. Báo cáo tổng kết ──
    print(f"\n{'='*55}")
    print(f"  BÁO CÁO CUỐI")
    print(f"{'='*55}")
    print(f"  Dòng ban đầu          : {initial_count:>10,}")
    print(f"  Sau bỏ null           : {after_null:>10,}")
    print(f"  Sau filter            : {after_filter:>10,}")
    print(f"  Sau dedup             : {after_dedup:>10,}")
    print(f"  Sau cân bằng (final)  : {after_balance:>10,}")
    print(f"  Số nhãn               : {df_final['category_id'].nunique():>10,}")
    print(f"  File lưu tại          : {output_path}")
    print(f"{'='*55}")

    print(f"\n📊 Phân phối nhãn (top 10 nhiều nhất):")
    top10 = cat_counts_after.sort_values(ascending=False).head(10)
    for cid, cnt in top10.items():
        cat_name = df_final[df_final['category_id'] == cid]['category_name'].iloc[0]
        bar = '█' * (cnt // (MAX_SAMPLES_PER_CATEGORY // 20))
        print(f"   {cnt:>6,}  {bar:<20}  {cat_name[:40]}")

    imbalance = cat_counts_after.max() / max(cat_counts_after.min(), 1)
    print(f"\n   Imbalance ratio (max/min): {imbalance:.1f}x")
    if imbalance > 20:
        print("   ⚠️  Vẫn còn mất cân bằng cao — bật USE_CLASS_WEIGHTS trong train")
    else:
        print("   ✅ Imbalance ở mức chấp nhận được")


if __name__ == "__main__":
    process_data(INPUT_PATH, OUTPUT_PATH)