import pandas as pd

CLEANNED_TRAINING_DATA_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\cleaned_training_data.csv'
TRAINING_DATA_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\training_data.csv'
CATEGORY_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\category.csv'
CATEGORY_MISSING_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\category_missing.csv'
CURRENT_CATEGORY_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\category_current.csv'

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


def print_count_per_category_having_depth(file_path):
    df = pd.read_csv(file_path)

    # Kiểm tra xem file có đủ 2 cột cần thiết không
    if 'category_name' in df.columns and 'depth' in df.columns:
        # Nhóm theo tên và depth, đếm số lượng, sau đó đổi tên cột đếm thành 'count'
        category_counts = df.groupby(['category_name', 'depth']).size().reset_index(name='count')

        # Sắp xếp theo số lượng đếm được giảm dần
        category_counts = category_counts.sort_values(by='count', ascending=False).reset_index(drop=True)

        # Thiết lập in không giới hạn số dòng
        pd.set_option('display.max_rows', None)

        print("=" * 50)
        print("THỐNG KÊ CHI TIẾT THEO NHÃN VÀ DEPTH:")
        # to_string(index=False) giúp in ra dạng bảng căn lề cực đẹp và bỏ cột index thừa (0, 1, 2...)
        print(category_counts.to_string(index=False))
        print("=" * 50)

        print(f"Tổng cộng có {len(category_counts)} nhãn đã có dữ liệu.")

        # Reset lại cấu hình sau khi in
        pd.reset_option('display.max_rows')
    else:
        print(f"Lỗi: File thiếu cột 'category_name' hoặc 'depth'. Vui lòng kiểm tra lại data.")


def save_missing_categories(category_path, data_path, output_path):
    print("--- Đang bắt đầu đối soát dữ liệu... ---")

    category_df = pd.read_csv(category_path, dtype={'id': str})
    data_df = pd.read_csv(data_path, dtype={'category_id': str})

    # 1. Tính toán số lượng trước trên TOÀN BỘ danh mục
    query_counts = data_df['category_id'].value_counts()

    # 2. Gắn số lượng vào category_df gốc (để bắt được cả bọn có 1-49 mẫu)
    category_df['query_count'] = category_df['id'].map(query_counts).fillna(0).astype(int)

    # 3. Lọc: Lấy những thằng có count < 300 (bao gồm cả bọn 0 mẫu)
    # Đồng thời bỏ qua Level 1, 2 vì bạn không cần bổ sung cho nhãn cha
    missing_df = category_df[
        (category_df['query_count'] < 300) &
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

def save_current_categories(category_path, data_path, output_path):
    print("--- Đang xử lý và lọc danh sách nhãn... ---")

    # 1. Đọc file category và rename cột ngay từ đầu cho chuẩn format output
    category_df = pd.read_csv(category_path)
    category_df = category_df.rename(columns={
        'Category ID': 'id',
        'Name': 'name',
        'Parent ID': 'parent_id',
        'Depth': 'depth'
    })
    # Đảm bảo ID là chuỗi để map chính xác
    category_df['id'] = category_df['id'].astype(str)

    # 2. Đọc file cleaned_data
    data_df = pd.read_csv(data_path, dtype={'category_id': str})

    # 3. Tính toán số lượng mẫu cho mỗi category_id từ cleaned_data
    query_counts = data_df['category_id'].value_counts()

    # 4. Gắn số lượng vào dataframe nhãn
    category_df['query_count'] = category_df['id'].map(query_counts).fillna(0).astype(int)

    # 5. Lọc: Chỉ lấy những nhãn có >= 500 mẫu dữ liệu
    current_df = category_df[category_df['query_count'] >= 500].copy()

    # 6. Sắp xếp theo thứ tự ưu tiên (nhiều mẫu lên trước)
    current_df = current_df.sort_values(by='query_count', ascending=False)

    # 7. Chỉ lấy các cột mục tiêu và ghi ra file
    final_columns = ['id', 'name', 'parent_id', 'depth']
    current_df[final_columns].to_csv(output_path, index=False, encoding='utf-8-sig')

    print("=" * 40)
    print(f"✅ Đã lưu thành công vào: {output_path}")
    print(f"📊 Tìm thấy {len(current_df)} nhãn thỏa mãn điều kiện (count >= 500).")
    print("Preview data:")
    print(current_df[final_columns].head())
    print("=" * 40)

if __name__ == "__main__":
    # save_missing_categories(CATEGORY_PATH, CLEANNED_TRAINING_DATA_PATH, CATEGORY_MISSING_PATH)
    # print_count_per_category_having_depth(CLEANNED_TRAINING_DATA_PATH)
    save_current_categories(CATEGORY_PATH,CLEANNED_TRAINING_DATA_PATH, CURRENT_CATEGORY_PATH)