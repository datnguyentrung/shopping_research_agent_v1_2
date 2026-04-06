"""
train_model.py
==============
Fine-tune RoBERTa-base từ đầu cho bài toán phân loại danh mục sản phẩm.
"""

import os

# 1. Ép hệ thống chỉ dùng GPU số 0
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
# 2. Tắt Weights & Biases
os.environ["WANDB_DISABLED"] = "true"
# 3. Tắt cảnh báo Tokenizer đa luồng
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# --- BÂY GIỜ MỚI IMPORT CÁC THƯ VIỆN KHÁC ---
import json
import joblib
import gc
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_class_weight
from torch.nn import CrossEntropyLoss
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)

# ─────────────────────────────────────────────
# CẤU HÌNH
# ─────────────────────────────────────────────
CSV_PATH = '/kaggle/input/datasets/datnguyentrung/dataset/cleaned_training_data.csv'
BASE_DIR = '/kaggle/working/Shopping_Research_Agent'

MODEL_DIR    = os.path.join(BASE_DIR, 'models/query_category_classifier_v3')
OUTPUT_MODEL = os.path.join(MODEL_DIR, 'query_category_classifier')
RESULTS_DIR  = os.path.join(MODEL_DIR, 'training_results')
LOG_DIR      = os.path.join(MODEL_DIR, 'logs')

os.makedirs(OUTPUT_MODEL, exist_ok=True)
os.makedirs(RESULTS_DIR,  exist_ok=True)
os.makedirs(LOG_DIR,      exist_ok=True)

PRETRAINED_MODEL = "roberta-base"
PER_DEVICE_BATCH = 32
GRAD_ACCUM_STEPS = 2
MAX_EPOCHS       = 3
LEARNING_RATE    = 3e-5
WARMUP_RATIO     = 0.06
MAX_LENGTH       = 128
AUTO_CLASS_WEIGHT_THRESHOLD = 10.0
EARLY_STOP_PATIENCE = 3


# ─────────────────────────────────────────────
# PYTORCH DATASET (LAZY TOKENIZATION - ĐÃ SỬA CHUẨN)
# ─────────────────────────────────────────────
class ShoppingDataset(torch.utils.data.Dataset):
    def __init__(self, texts, labels, tokenizer, max_length):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __getitem__(self, idx):
        # Chỉ tokenize 1 dòng đang được gọi tới -> Không bao giờ tốn RAM
        encoding = self.tokenizer(
            self.texts[idx],
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt"
        )
        # Squeeze để bỏ chiều batch vô ích
        item = {k: v.squeeze(0) for k, v in encoding.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
        return item

    def __len__(self):
        return len(self.labels)


def main():
    # ─────────────────────────────────────────────
    # 1. LOAD DATA
    # ─────────────────────────────────────────────
    print("=" * 55)
    print("  FINE-TUNE RoBERTa — Product Category Classifier v2")
    print("=" * 55)

    print(f"\n📂 Tải data: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, dtype={'category_id': str})
    df = df[["search_query", "category_id", "category_name"]].dropna()
    print(f"   Tổng mẫu: {len(df):,} | Số nhãn: {df['category_id'].nunique()}")

    counts = df["category_id"].value_counts()
    imbalance_ratio = counts.max() / counts.min()
    print(f"   Imbalance ratio: {imbalance_ratio:.1f}x")

    use_class_weights = imbalance_ratio > AUTO_CLASS_WEIGHT_THRESHOLD
    print(f"   Class weights: {'ON (auto)' if use_class_weights else 'OFF'}")

    # ─────────────────────────────────────────────
    # 2. LABEL ENCODING
    # ─────────────────────────────────────────────
    label_encoder = LabelEncoder()
    df["label"] = label_encoder.fit_transform(df["category_id"])
    num_labels = len(label_encoder.classes_)

    cat_name_map = (
        df.drop_duplicates("category_id")
          .set_index("category_id")["category_name"]
          .to_dict()
    )
    id2label = {
        i: cat_name_map.get(label_encoder.classes_[i], str(label_encoder.classes_[i]))
        for i in range(num_labels)
    }
    label2id = {v: k for k, v in id2label.items()}

    texts  = df["search_query"].tolist()
    labels = df["label"].tolist()

    # ─────────────────────────────────────────────
    # 3. STRATIFIED SPLIT
    # ─────────────────────────────────────────────
    X_train, X_temp, y_train, y_temp = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.5, random_state=42, stratify=y_temp
    )
    print(f"\n   Train: {len(X_train):,} | Val: {len(X_val):,} | Test: {len(X_test):,}")

    # Dọn dẹp RAM rác rưởi của DataFrame trước khi nạp model
    del df, X_temp, y_temp
    gc.collect()

    # ─────────────────────────────────────────────
    # 4. TOKENIZATION & DATASET INIT (LAZY LOADING)
    # ─────────────────────────────────────────────
    print(f"\n🔤 Tải tokenizer: {PRETRAINED_MODEL}")
    tokenizer = AutoTokenizer.from_pretrained(PRETRAINED_MODEL)

    print("   Khởi tạo Dataset (Lazy Loading - Tối ưu RAM)...")
    train_dataset = ShoppingDataset(X_train, y_train, tokenizer, MAX_LENGTH)
    val_dataset   = ShoppingDataset(X_val,   y_val,   tokenizer, MAX_LENGTH)
    test_dataset  = ShoppingDataset(X_test,  y_test,  tokenizer, MAX_LENGTH)
    print("   ✓ Hoàn tất!")

    # ─────────────────────────────────────────────
    # 6. MODEL
    # ─────────────────────────────────────────────
    print(f"\n🤖 Khởi tạo {PRETRAINED_MODEL} ({num_labels} nhãn)...")
    model = AutoModelForSequenceClassification.from_pretrained(
        PRETRAINED_MODEL,
        num_labels=num_labels,
        id2label=id2label,
        label2id=label2id,
    )

    # ─────────────────────────────────────────────
    # 7. CLASS WEIGHTS
    # ─────────────────────────────────────────────
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"   Device: {device}")

    weights_tensor = None
    if use_class_weights:
        class_weights = compute_class_weight(
            "balanced", classes=np.unique(y_train), y=y_train
        )
        MAX_WEIGHT = 10.0
        class_weights = np.clip(class_weights, 0, MAX_WEIGHT)
        weights_tensor = torch.tensor(class_weights, dtype=torch.float).to(device)
        print(f"   Class weights clipped to max {MAX_WEIGHT} "
              f"(min={class_weights.min():.2f}, max={class_weights.max():.2f})")

    # ─────────────────────────────────────────────
    # 8. METRICS
    # ─────────────────────────────────────────────
    def compute_metrics(eval_pred):
        logits, labels_eval = eval_pred
        preds = np.argmax(logits, axis=-1)
        return {
            "accuracy":    accuracy_score(labels_eval, preds),
            "f1_macro":    f1_score(labels_eval, preds, average="macro",    zero_division=0),
            "f1_weighted": f1_score(labels_eval, preds, average="weighted", zero_division=0),
        }

    # ─────────────────────────────────────────────
    # 9. CUSTOM TRAINER
    # ─────────────────────────────────────────────
    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels_local  = inputs.pop("labels")
            outputs = model(**inputs)
            loss_fn = CrossEntropyLoss(weight=weights_tensor, label_smoothing=0.1)
            loss    = loss_fn(outputs.logits, labels_local)
            return (loss, outputs) if return_outputs else loss

    TrainerClass = WeightedTrainer if use_class_weights else Trainer

    # ─────────────────────────────────────────────
    # 10. TRAINING ARGUMENTS
    # ─────────────────────────────────────────────
    training_args = TrainingArguments(
        output_dir=RESULTS_DIR,
        num_train_epochs              = MAX_EPOCHS,
        per_device_train_batch_size   = PER_DEVICE_BATCH,
        per_device_eval_batch_size    = PER_DEVICE_BATCH * 2,
        gradient_accumulation_steps   = GRAD_ACCUM_STEPS,
        learning_rate                 = LEARNING_RATE,
        warmup_ratio                  = WARMUP_RATIO,
        lr_scheduler_type             = "cosine",
        weight_decay                  = 0.01,
        label_smoothing_factor        = 0.1,
        eval_strategy                 = "epoch",
        save_strategy                 = "epoch",
        load_best_model_at_end        = True,
        metric_for_best_model         = "f1_macro",
        greater_is_better             = True,
        save_total_limit              = 2,
        logging_steps                 = 100,   # Sửa từ 500 xuống 100 để 1-2 phút là thấy log nổ ra 1 lần
        disable_tqdm                  = True,  # THÊM DÒNG NÀY VÀO: Tắt triệt để thanh tiến trình gây treo log ngầm
        report_to                     = "none",
        fp16                          = torch.cuda.is_available(),
        dataloader_num_workers        = 0,
        dataloader_pin_memory         = torch.cuda.is_available(),
    )

    # ─────────────────────────────────────────────
    # 11. TRAIN
    # ─────────────────────────────────────────────
    trainer = TrainerClass(
        model           = model,
        args            = training_args,
        train_dataset   = train_dataset,
        eval_dataset    = val_dataset,
        compute_metrics = compute_metrics,
        callbacks       = [
            EarlyStoppingCallback(early_stopping_patience=EARLY_STOP_PATIENCE),
        ],
    )

    print(f"\n{'='*55}")
    print(f"  BẮT ĐẦU TRAINING")
    print(f"{'='*55}")
    trainer.train()

    # ─────────────────────────────────────────────
    # 12. EVALUATE TRÊN TEST SET
    # ─────────────────────────────────────────────
    print("\n📊 Đánh giá trên tập Test...")
    test_results = trainer.evaluate(test_dataset)
    acc    = test_results.get('eval_accuracy', 0)
    f1_mac = test_results.get('eval_f1_macro', 0)
    f1_w   = test_results.get('eval_f1_weighted', 0)

    print(f"\n  Accuracy    : {acc:.4f}")
    print(f"  F1-macro    : {f1_mac:.4f}")
    print(f"  F1-weighted : {f1_w:.4f}")

    print("\n📝 Tạo per-class classification report...")
    preds_output = trainer.predict(test_dataset)
    preds = np.argmax(preds_output.predictions, axis=-1)
    report = classification_report(
        y_test, preds,
        target_names=[id2label[i] for i in range(num_labels)],
        zero_division=0
    )
    report_path = os.path.join(OUTPUT_MODEL, "classification_report.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    # ─────────────────────────────────────────────
    # 13. LƯU MODEL
    # ─────────────────────────────────────────────
    print(f"\n💾 Lưu model → {OUTPUT_MODEL}")
    trainer.save_model(OUTPUT_MODEL)
    tokenizer.save_pretrained(OUTPUT_MODEL)
    joblib.dump(label_encoder, os.path.join(OUTPUT_MODEL, "label_encoder.joblib"))

    metadata = {
        "version":           "v3",
        "pretrained_model":  PRETRAINED_MODEL,
        "num_labels":        num_labels,
        "max_length":        MAX_LENGTH,
        "use_class_weights": use_class_weights,
        "imbalance_ratio":   round(float(imbalance_ratio), 2),
        "train_samples":     len(X_train),
        "val_samples":       len(X_val),
        "test_samples":      len(X_test),
        "test_accuracy":     round(acc, 4),
        "test_f1_macro":     round(f1_mac, 4),
        "test_f1_weighted":  round(f1_w, 4),
    }
    meta_path = os.path.join(OUTPUT_MODEL, "training_metadata.json")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"  HOÀN TẤT!")
    print(f"{'='*55}")


if __name__ == '__main__':
    main()