import os
import pandas as pd

base_dir = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(base_dir, "course4model.csv")

df = pd.read_csv(
    path,
    sep="|",
    engine="python",
    dtype=str,
    encoding="utf-8-sig",
    on_bad_lines="warn",
)

# ป้องกัน NaN และบังคับเป็น string
df["eng_abv"] = df["eng_abv"].fillna("").astype(str)

# แยกด้วย , แล้วแตกเป็นหลายแถว
df["eng_abv"] = df["eng_abv"].str.split(",")

df = df.explode("eng_abv", ignore_index=True)

# ตัดช่องว่างหัว-ท้าย
df["eng_abv"] = df["eng_abv"].str.strip()

# ถ้ามีค่าเปล่า (เช่น ",,") ให้ตัดทิ้ง
df = df[df["eng_abv"] != ""]

# บันทึกไฟล์ใหม่
out_path = os.path.join(base_dir, "course4model_exploded.csv")
df.to_csv(out_path, index=False, encoding="utf-8-sig")

print("Saved to:", out_path)
print("Rows:", len(df))
