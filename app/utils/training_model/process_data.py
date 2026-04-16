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
  5. Cắt bỏ nhãn thiếu dữ liệu (Loại bỏ các category < MIN)
  6. Cân bằng: cap MAX
  7. Cảnh báo nhãn mỏng
  8. Lưu cleaned_training_data.csv
  9. Báo cáo chi tiết + phân phối nhãn
"""
import os
import pandas as pd
import re
import glob
import unicodedata

# ─────────────────────────────────────────────
# CẤU HÌNH
# ─────────────────────────────────────────────
INPUT_PATH  = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\parquet_chunks_v2'
OUTPUT_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\cleaned_training_data.csv'

MAX_SAMPLES_PER_CATEGORY = 5_000   # Cap tối đa trên mỗi nhãn
MIN_SAMPLES_PER_CATEGORY = 500      # 🗑️ MỚI: XÓA HOÀN TOÀN nhãn nếu số lượng < ngưỡng này
MIN_SAMPLES_WARNING      = 1000     # Cảnh báo nếu nhãn < ngưỡng này (dành cho các nhãn đã qua ải MIN ở trên)
MIN_QUERY_WORDS          = 1        # Tối thiểu 1 từ
MAX_QUERY_WORDS          = 100      # Quá dài → cắt bớt thay vì bỏ
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
    print(f"\n📂 Tải dữ liệu từ thư mục: {input_path}")

    # Tìm tất cả file .parquet trong thư mục
    parquet_files = glob.glob(os.path.join(input_path, "*.parquet"))
    if not parquet_files:
        raise ValueError(f"❌ Không tìm thấy file .parquet nào trong: {input_path}")

    print(f"   Tìm thấy {len(parquet_files)} file. Đang gộp dữ liệu...")

    # Đọc và gộp tất cả các file
    df_list = [pd.read_parquet(f) for f in parquet_files]
    df = pd.concat(df_list, ignore_index=True)

    # Ép kiểu category_id về string để tránh lỗi mapping sau này
    df['category_id'] = df['category_id'].astype(str)

    initial_count = len(df)
    print(f"   Tổng dòng ban đầu: {initial_count:,}")

    required_cols = {
        'search_query', 'category_id', 'category_name',
        'depth' # TODO: Bỏ 'depth' nếu không cần nữa
    }
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(f"❌ File thiếu cột: {missing_cols}")

    # ── 2. Bỏ dòng null ──
    df = df.dropna(subset=[
        'search_query', 'category_id', 'category_name',
        'depth' # TODO: Bỏ 'depth' nếu không cần nữa
    ])
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

    # ── 6. Cắt bỏ nhãn thiếu dữ liệu (DROP MIN) ──
    print(f"\n✂️  Loại bỏ các nhãn có < {MIN_SAMPLES_PER_CATEGORY} mẫu...")
    cat_counts_before_drop = df['category_id'].value_counts()

    # Lấy danh sách các category_id ĐẠT yêu cầu
    valid_categories = cat_counts_before_drop[cat_counts_before_drop >= MIN_SAMPLES_PER_CATEGORY].index
    num_dropped_cats = len(cat_counts_before_drop) - len(valid_categories)

    # Lọc lại df
    df = df[df['category_id'].isin(valid_categories)]
    after_drop_min = len(df)

    print(f"   Đã xóa hoàn toàn {num_dropped_cats} nhãn quá ít data.")
    print(f"   Số dòng sau cắt: {after_drop_min:,} (bỏ {after_dedup - after_drop_min:,})")

    # ── 7. Cap & cân bằng (MAX) ──
    print(f"\n⚖️  Cân bằng dữ liệu (max {MAX_SAMPLES_PER_CATEGORY:,}/nhãn)...")
    sampled_list = []

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

    # ── 8. Kiểm tra nhãn mỏng dữ liệu ──
    cat_counts_after = df_final.groupby('category_id').size()
    low_cats = cat_counts_after[cat_counts_after < MIN_SAMPLES_WARNING]

    if len(low_cats) > 0:
        print(f"\n⚠️  {len(low_cats)} nhãn có < {MIN_SAMPLES_WARNING} mẫu (hơi mỏng, lưu ý):")
        for cid, cnt in low_cats.sort_values().items():
            cat_name = df_final[df_final['category_id'] == cid]['category_name'].iloc[0]
            print(f"   {cnt:>6,}  [{cid}] {cat_name}")
    else:
        print(f"\n✅ Tất cả các nhãn còn lại đều có ≥ {MIN_SAMPLES_WARNING} mẫu!")

    # ── 9. Lưu ──
    df_final = df_final[[
        'category_id', 'category_name', 'search_query',
        'depth'  # TODO: Bỏ 'depth' nếu không cần nữa
    ]]
    df_final.to_csv(output_path, index=False, encoding='utf-8-sig')

    # ── 10. Báo cáo tổng kết ──
    print(f"\n{'='*55}")
    print(f"  BÁO CÁO CUỐI")
    print(f"{'='*55}")
    print(f"  Dòng ban đầu          : {initial_count:>10,}")
    print(f"  Sau bỏ null           : {after_null:>10,}")
    print(f"  Sau filter            : {after_filter:>10,}")
    print(f"  Sau dedup             : {after_dedup:>10,}")
    print(f"  Sau cắt (<{MIN_SAMPLES_PER_CATEGORY:<4})     : {after_drop_min:>10,}")
    print(f"  Sau cân bằng (final)  : {after_balance:>10,}")
    print(f"  Số nhãn chốt          : {df_final['category_id'].nunique():>10,}")
    print(f"  File lưu tại          : {output_path}")
    print(f"{'='*55}")

    print(f"\n📊 Phân phối nhãn (top 5 nhiều nhất):")
    top5 = cat_counts_after.sort_values(ascending=False).head(5)
    for cid, cnt in top5.items():
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