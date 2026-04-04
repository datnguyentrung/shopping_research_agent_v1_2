import logging

import pandas as pd


logger = logging.getLogger(__name__)

CLEANNED_TRAINING_DATA_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\cleaned_training_data.csv'
ADDITIONAL_TRAINING_DATA_PATH = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\additional_training_data.csv'

def add_additional_data_to_cleaned(drop_duplicates: bool = True) -> None:
    """Thêm dữ liệu từ `additional_training_data.csv` vào `cleaned_training_data.csv`.

    Logic:
    - Đọc 2 file CSV trong thư mục `data/`.
    - Append dữ liệu mới (additional) vào cleaned.
    - (Tuỳ chọn) Loại bỏ bản ghi trùng lặp dựa trên cột: `category_id`, `category_name`, `search_query`.
    - Ghi đè lại file `cleaned_training_data.csv`.

    Parameters
    ----------
    drop_duplicates: bool, optional
        Nếu True (mặc định), sẽ gọi `drop_duplicates` sau khi gộp.
    """

    logger.info("Loading cleaned data from %s", CLEANNED_TRAINING_DATA_PATH)
    cleaned_df = pd.read_csv(CLEANNED_TRAINING_DATA_PATH)

    logger.info("Loading additional data from %s", ADDITIONAL_TRAINING_DATA_PATH)
    additional_df = pd.read_csv(ADDITIONAL_TRAINING_DATA_PATH)

    if additional_df.empty:
        logger.warning("additional_training_data.csv is empty. Nothing to add.")
        return

    # Đảm bảo các cột quan trọng tồn tại (tránh lỗi do format khác)
    required_cols = {"category_id", "category_name", "search_query"}
    missing_in_additional = required_cols - set(additional_df.columns)
    missing_in_cleaned = required_cols - set(cleaned_df.columns)

    if missing_in_additional:
        raise ValueError(
            f"Missing required columns in additional_training_data.csv: {missing_in_additional}"
        )
    if missing_in_cleaned:
        raise ValueError(
            f"Missing required columns in cleaned_training_data.csv: {missing_in_cleaned}"
        )

    logger.info(
        "Current cleaned size: %d rows | additional size: %d rows",
        len(cleaned_df),
        len(additional_df),
    )

    combined_df = pd.concat([cleaned_df, additional_df], ignore_index=True)

    if drop_duplicates:
        before = len(combined_df)
        combined_df = combined_df.drop_duplicates(
            subset=["category_id", "category_name", "search_query"], keep="first"
        )
        after = len(combined_df)
        logger.info("Dropped %d duplicate rows", before - after)

    combined_df.to_csv(CLEANNED_TRAINING_DATA_PATH, index=False)

    logger.info(
        "Saved merged cleaned data to %s with %d rows",
        CLEANNED_TRAINING_DATA_PATH,
        len(combined_df),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    add_additional_data_to_cleaned()

