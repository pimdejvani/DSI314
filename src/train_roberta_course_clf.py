

import os
import json
import pandas as pd
from typing import Dict, Any

import torch
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    DataCollatorWithPadding,
    TrainingArguments,
    Trainer,
)
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report


# =========================
# Config
# =========================
MODEL_NAME = "roberta-base"

# ปรับได้ผ่าน env ถ้าต้องการ
EPOCHS = int(os.getenv("CLS_EPOCHS", "3"))
BATCH_TRAIN = int(os.getenv("CLS_TRAIN_BS", "8"))
BATCH_EVAL = int(os.getenv("CLS_EVAL_BS", "8"))
MAX_LEN = int(os.getenv("CLS_MAX_LENGTH", "256"))  # แนะนำ 256 เพื่อให้เทรนทัน/นิ่ง
LR = float(os.getenv("CLS_LR", "2e-5"))

# =========================
# Metrics
# =========================
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = logits.argmax(axis=-1)
    acc = accuracy_score(labels, preds)
    f1 = f1_score(labels, preds, average="macro")
    return {"accuracy": acc, "macro_f1": f1}


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "course4model.csv")

    # ตามที่คุณเคยใช้แล้วได้
    df = pd.read_csv(
        path,
        sep="|",
        engine="python",
        dtype=str,
        encoding="utf-8-sig",
        usecols=list(range(15)),
        on_bad_lines="warn",
    )
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

    # ต้องมีคอลัมน์เหล่านี้
    required = ["eng_name", "eng_desc", "derived_eng_desc1", "label1"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # ไม่คลีน data ตามที่คุณต้องการ
    # แค่จัดการ NaN ให้ concat ได้
    df["eng_name"] = df["eng_name"].fillna("")
    df["eng_desc"] = df["eng_desc"].fillna("")
    df["derived_eng_desc1"] = df["derived_eng_desc1"].fillna("")
    df["label1"] = df["label1"].fillna("")

    # สร้าง text input
    df["text"] = (
        df["eng_name"].astype(str) + " " +
        df["eng_desc"].astype(str) + " " +
        df["derived_eng_desc1"].astype(str)
    ).astype(str)

    # กรองแถวที่ label ใช้ไม่ได้ (ยังถือว่าเป็นการคัดข้อมูลขั้นต่ำ ไม่ใช่การคลีนข้อความ)
    df = df[df["label1"].astype(str).str.strip().astype(bool)]
    df = df[df["label1"] != "NoDesc"]
    df = df[df["text"].astype(str).str.strip().astype(bool)]

    if len(df) < 50:
        raise ValueError("Not enough rows after minimal filtering (label/text empty).")

    # label encoding
    labels = sorted(df["label1"].unique().tolist())
    label2id = {l: i for i, l in enumerate(labels)}
    id2label = {i: l for l, i in label2id.items()}
    df["label_id"] = df["label1"].map(label2id)

    # split
    train_df, test_df = train_test_split(
        df,
        test_size=0.2,
        random_state=42,
        stratify=df["label_id"] if len(labels) > 1 else None,
    )

    train_ds = Dataset.from_pandas(train_df[["text", "label_id"]], preserve_index=False)
    test_ds = Dataset.from_pandas(test_df[["text", "label_id"]], preserve_index=False)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    def tok_fn(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=MAX_LEN,
        )

    train_ds = train_ds.map(tok_fn, batched=True)
    test_ds = test_ds.map(tok_fn, batched=True)

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=len(labels),
        label2id=label2id,
        id2label=id2label,
    )

    out_dir = os.path.join(base_dir, "course_roberta_clf")
    log_txt = os.path.join(base_dir, "roberta_train_log.txt")

    # บันทึกสรุป config ลงไฟล์ txt ก่อน
    with open(log_txt, "w", encoding="utf-8") as f:
        f.write("RoBERTa course classification training log\n")
        f.write(f"MODEL_NAME={MODEL_NAME}\n")
        f.write(f"EPOCHS={EPOCHS}\n")
        f.write(f"MAX_LEN={MAX_LEN}\n")
        f.write(f"TRAIN_BS={BATCH_TRAIN}\n")
        f.write(f"EVAL_BS={BATCH_EVAL}\n")
        f.write(f"LR={LR}\n")
        f.write(f"Train rows={len(train_df)} | Test rows={len(test_df)}\n")
        f.write(f"Classes={len(labels)}\n\n")

    # ใช้ GPU อัตโนมัติถ้ามี
    fp16_flag = torch.cuda.is_available()

    args = TrainingArguments(
        output_dir=out_dir,
        learning_rate=LR,
        per_device_train_batch_size=BATCH_TRAIN,
        per_device_eval_batch_size=BATCH_EVAL,
        num_train_epochs=EPOCHS,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_strategy="steps",
        logging_steps=20,
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        report_to=[],
        fp16=fp16_flag,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=test_ds,
        tokenizer=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    trainer.train()

    # evaluate detail
    pred = trainer.predict(test_ds)
    y_true = pred.label_ids
    y_pred = pred.predictions.argmax(axis=-1)

    report = classification_report(
        y_true,
        y_pred,
        target_names=[id2label[i] for i in range(len(labels))],
        digits=4
    )
    acc = accuracy_score(y_true, y_pred)
    macro = f1_score(y_true, y_pred, average="macro")

    print("\n=== Evaluation ===")
    print("accuracy:", acc)
    print("macro_f1:", macro)
    print(report)

    # append log
    with open(log_txt, "a", encoding="utf-8") as f:
        f.write("\n=== Evaluation ===\n")
        f.write(f"accuracy={acc}\n")
        f.write(f"macro_f1={macro}\n\n")
        f.write(report)
        f.write("\n")

    # save model + tokenizer + label map
    trainer.save_model(out_dir)
    tokenizer.save_pretrained(out_dir)

    with open(os.path.join(out_dir, "label_map.json"), "w", encoding="utf-8") as f:
        json.dump({"label2id": label2id, "id2label": id2label}, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Saved model to: {out_dir}")
    print(f"[OK] Log file to: {log_txt}")


if __name__ == "__main__":
    main()
