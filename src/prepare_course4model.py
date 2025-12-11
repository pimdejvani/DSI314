import os
import glob
import pandas as pd

DEFAULT_BASE = "/app/src/course4model"
COURSE4MODEL_PATH = os.getenv("COURSE4MODEL_PATH", DEFAULT_BASE)


def _resolve_path(base: str) -> str:
    """
    รองรับทั้ง:
    - path ที่ชี้ไฟล์ตรง ๆ
    - ชื่อฐานที่ไม่มีนามสกุล
    จะลองหา .csv/.tsv/.txt และ fallback เป็น base เอง
    """
    if os.path.isfile(base):
        return base

    for ext in (".csv", ".tsv", ".txt"):
        p = base + ext
        if os.path.isfile(p):
            return p

    wild = glob.glob(base + ".*")
    for p in wild:
        if os.path.isfile(p):
            return p

    return base


def _read_any(path: str) -> pd.DataFrame:
    """
    dataset ของคุณเหมือนใช้ | เป็นตัวคั่น
    เลยลอง | ก่อน แล้วค่อยลอง comma
    """
    try:
        return pd.read_csv(path, sep="|", dtype=str, encoding="utf-8-sig")
    except Exception:
        return pd.read_csv(path, dtype=str, encoding="utf-8-sig")


def main():
    path = _resolve_path(COURSE4MODEL_PATH)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"course4model file not found at: {path}. "
            "Set COURSE4MODEL_PATH if your filename is different."
        )

    df = pd.read_csv(path, sep=",", dtype=str, encoding="utf-8-sig")



    # ให้เหลือแค่ 4 คอลัมน์หลัก
    keep = ["course_id", "eng_abv", "eng_name", "eng_desc"]
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[keep].copy()
    
    # ทำความสะอาดเบื้องต้น
    for c in keep:
        df[c] = df[c].where(df[c].notna(), None)

    # ---------- กรณี eng_desc ซ้ำหลายแถว ----------
    # ถ้ามี eng_desc แล้วซ้ำกัน ให้รวม eng_abv + course_id เป็นสตริงเดียวคั่นด้วย comma
    has_desc = (
        df["eng_desc"].notna()
        & df["eng_desc"].astype(str).str.strip().astype(bool)
    )
    df_desc = df[has_desc].copy()
    df_nod = df[~has_desc].copy()

    if not df_desc.empty:
        df_desc["_desc_key"] = df_desc["eng_desc"].astype(str).str.strip()

        def join_unique(series):
            vals = [v.strip() for v in series.dropna().astype(str).tolist() if v.strip()]
            seen = set()
            out = []
            for v in vals:
                if v not in seen:
                    seen.add(v)
                    out.append(v)
            return ",".join(out) if out else None

        def first_nonempty(series):
            for v in series.dropna().astype(str).tolist():
                v = v.strip()
                if v:
                    return v
            return None

        df_desc = (
            df_desc
            .groupby("_desc_key", as_index=False)
            .agg({
                "course_id": join_unique,
                "eng_abv": join_unique,
                "eng_name": first_nonempty,
                "eng_desc": first_nonempty,
            })
            .drop(columns=["_desc_key"])
        )

    df = pd.concat([df_desc, df_nod], ignore_index=True)


    # ---------- สร้างคอลัมน์ label/valid ----------
    new_cols = [
        "valid1", "label1", "confident1", "derived_eng_desc1",
        "valid2", "label2", "confident2", "derived_eng_desc2",
        "final_label", "final_confident", "derived_eng_desc_final",
    ]
    for c in new_cols:
        df[c] = None

    # ค่าเริ่มต้นตามสเปก
    df["valid1"] = 0
    df["valid2"] = 0
    df["confident1"] = 0
    df["confident2"] = 0
    df["final_confident"] = 0

    # ทำให้เป็น int ชัด ๆ
    for c in ["valid1", "valid2", "confident1", "confident2", "final_confident"]:
        df[c] = df[c].astype(int)

    # ---------- กรณีไม่มี eng_desc ----------
    no_desc_mask = (
        df["eng_desc"].isna()
        | ~df["eng_desc"].astype(str).str.strip().astype(bool)
    )

    valid_cols = ["valid1", "valid2", "confident1", "confident2", "final_confident"]
    label_cols = ["label1", "label2", "final_label"]
    derived_cols = ["derived_eng_desc1", "derived_eng_desc2", "derived_eng_desc_final"]

    df.loc[no_desc_mask, valid_cols] = 1
    df.loc[no_desc_mask, label_cols] = "NoDesc"
    df.loc[no_desc_mask, derived_cols] = "NoDesc"

    # บันทึกทับไฟล์เดิม
    df.to_csv(path, sep="|", index=False, encoding="utf-8-sig")
    print(f"[OK] Prepared and overwritten: {path}")
    print(f"[INFO] Rows: {len(df)}")


if __name__ == "__main__":
    main()
