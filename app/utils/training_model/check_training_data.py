import pandas as pd

CLEANNED_TRAINING_DATA_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\cleaned_training_data.csv'
TRAINING_DATA_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\training_data.csv'
CATEGORY_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\category.csv'
CATEGORY_MISSING_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\category_missing.csv'


def print_count_per_category(file_path):
    df = pd.read_csv(file_path)

    if 'category_name' in df.columns:
        category_counts = df['category_name'].value_counts()

        # DÒNG QUAN TRỌNG ĐÂY: Thiết lập in không giới hạn số dòng
        pd.set_option('display.max_rows', None)

        print("=" * 30)
        print("THỐNG KÊ CHI TIẾT TOÀN BỘ 130 NHÃN:")
        print(category_counts)
        print("=" * 30)

        print(f"Tổng cộng có {len(category_counts)} nhãn đã có dữ liệu.")

        # Reset lại cấu hình sau khi in (tùy chọn)
        pd.reset_option('display.max_rows')
    else:
        print(f"Lỗi: Không tìm thấy cột 'category_name'.")


def save_missing_categories(category_path, data_path, output_path):
    print("--- Đang bắt đầu đối soát dữ liệu... ---")

    category_df = pd.read_csv(category_path, dtype={'id': str})
    data_df = pd.read_csv(data_path, dtype={'category_id': str})

    # 1. Tính toán số lượng trước trên TOÀN BỘ danh mục
    query_counts = data_df['category_id'].value_counts()

    # 2. Gắn số lượng vào category_df gốc (để bắt được cả bọn có 1-49 mẫu)
    category_df['query_count'] = category_df['id'].map(query_counts).fillna(0).astype(int)

    # 3. Lọc: Lấy những thằng có count < 50 (bao gồm cả bọn 0 mẫu)
    # Đồng thời bỏ qua Level 1, 2 vì bạn không cần bổ sung cho nhãn cha
    missing_df = category_df[
        (category_df['query_count'] < 50) &
        (~category_df['level'].isin([1, 2]))
    ].copy()

    # 4. Sắp xếp tăng dần theo query_count để ưu tiên thằng thiếu nhất lên đầu
    missing_df = missing_df.sort_values(by='query_count', ascending=True)

    # 5. Ghi ra file
    missing_df.to_csv(output_path, index=False, encoding='utf-8-sig')

    print("=" * 30)
    print("DANH SÁCH NHÃN CẦN BỔ SUNG (COUNT < 50):")
    print(missing_df[['id', 'name', 'query_count']])
    print(f"Tổng cộng có {len(missing_df)} nhãn cần xử lý.")
    print("=" * 30)

    if not missing_df.empty:
        print("\nTop 5 nhãn thiếu đầu tiên:")
        print(missing_df[['id', 'name']].head(5))

if __name__ == "__main__":
    print_count_per_category(TRAINING_DATA_PATH)
