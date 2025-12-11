import os
import time
import json
import pandas as pd
from typing import List, Dict, Any, Optional

from google import genai
from google.genai import types


# =========================
# Config (ปรับได้ตามใจ)
# =========================
BATCH_SIZE = 50
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

MAX_RETRIES = 5
REQUEST_DELAY_SEC = 0.5
BACKOFF_429_SEC = 8

if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)


# =========================
# Label Definitions
# =========================
LABEL_CODE_MAP: Dict[str, str] = {
    "00": "00 Generic programmes and qualifications",
    "01": "01 Education",
    "02": "02 Arts and humanities",
    "03": "03 Social sciences, journalism and information",
    "04": "04 Business, administration and law",
    "05": "05 Natural sciences, mathematics and statistics",
    "06": "06 Information and Communication Technologies",
    "07": "07 Engineering, manufacturing and construction",
    "08": "08 Agriculture, forestry, fisheries and veterinary",
    "09": "09 Health and welfare",
    "10": "10 Services",
}
LABEL_CODES = list(LABEL_CODE_MAP.keys())

LABEL_MAP: Dict[str, str] = {
    "00 Generic programmes and qualifications": (
        "Broad, non-specialised programmes developing basic, general or personal skills; "
        "covers a wide range of subjects with little or no field emphasis."
    ),
    "01 Education": (
        "Teacher training and education science; preparing educators and studying teaching/learning "
        "methods, curriculum, and educational systems."
    ),
    "02 Arts and humanities": (
        "Arts, design, music, performing arts, religion, history, philosophy, and languages/literature; "
        "focuses on cultural and creative expression and interpretation."
    ),
    "03 Social sciences, journalism and information": (
        "Social and behavioural sciences, economics, politics, sociology, journalism, library and "
        "information sciences; studies society, people, and communication."
    ),
    "04 Business, administration and law": (
        "Business and management, accounting, finance, marketing, administration, and legal studies; "
        "focuses on organizations, commerce, and regulatory frameworks."
    ),
    "05 Natural sciences, mathematics and statistics": (
        "Biology, chemistry, physics, earth sciences, mathematics, and statistics; "
        "studies natural phenomena, quantitative reasoning, and data methods."
    ),
    "06 Information and Communication Technologies": (
        "Computer science, software, networks, databases, AI, and ICT applications; "
        "focuses on computing systems and digital technologies."
    ),
    "07 Engineering, manufacturing and construction": (
        "Engineering disciplines, industrial production, materials, architecture/ construction; "
        "applies science and technology to design, build, and manufacture."
    ),
    "08 Agriculture, forestry, fisheries and veterinary": (
        "Crop and animal production, forestry, fisheries, food-related agriculture, and veterinary medicine; "
        "manages biological resources and animal health."
    ),
    "09 Health and welfare": (
        "Medicine, nursing, dentistry, pharmacy, public health, and social care; "
        "promotes health, treatment, rehabilitation, and wellbeing."
    ),
    "10 Services": (
        "Personal, transport, security, environmental, and other service fields including hospitality and tourism; "
        "focuses on practical services for individuals and society."
    ),
}


# =========================
# Response Schema
# =========================
COURSE_LABEL_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "results": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "course_id": {"type": "STRING"},
                    "label_code": {"type": "STRING", "nullable": True},
                    "confidence": {"type": "NUMBER"},
                    "derived_eng_desc1": {"type": "STRING"},
                },
                "required": ["course_id", "label_code", "confidence", "derived_eng_desc1"],
            },
        }
    },
    "required": ["results"],
}


# =========================
# Helpers
# =========================
def sanitize_text(s: Optional[str]) -> str:
    if s is None:
        return ""
    s = str(s)
    s = s.replace("\\", "")
    s = s.replace("\n", " ").replace("\r", " ")
    s = " ".join(s.split())
    return s.strip()


def build_prompt(courses: List[Dict[str, str]]) -> str:
    user_obj = {
        "task": "batch_label_courses",
        "label_definitions": LABEL_MAP,
        "labels": LABEL_CODES,
        "courses": [
            {
                "course_id": c.get("course_id", ""),
                "eng_name": c.get("eng_name", ""),
                "eng_desc": c.get("eng_desc", ""),
            }
            for c in courses
        ],
        "output_format": {
            "results": [
                {
                    "course_id": "string",
                    "label_code": "string (00-10) or null",
                    "confidence": "number 0-1",
                    "derived_eng_desc1": "string"
                }
            ]
        },
        "strict": [
            "Return exactly one result per course in the same order as input.",
            f"Return results with exactly {len(courses)} items.",
            "Choose label_code only from the provided labels (00-10).",
            "Use label_definitions to guide your decision.",
            "derived_eng_desc1 is a short rationale (<= 20 words).",
            "Output must strictly follow the JSON schema.",
            "No extra keys, no free text.",
            "Return COMPACT one-line JSON only.",
            "Do not include newline characters in any string.",
            "If the text is insufficient, set label_code=null and confidence=0."
        ]
    }
    return json.dumps(user_obj, ensure_ascii=False)


def _schema_obj(schema: Dict[str, Any]) -> Any:
    schema_obj: Any = schema
    SchemaCls = getattr(types, "Schema", None)
    if SchemaCls and hasattr(SchemaCls, "from_dict"):
        schema_obj = SchemaCls.from_dict(schema)
    return schema_obj


def _safe_json_load(text: str) -> Dict[str, Any]:
    t = (text or "").strip()
    t = t.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    # กัน newline หลุด
    t = t.replace("\n", " ").replace("\r", " ")
    return json.loads(t)


def call_gemini_with_schema(prompt: str) -> Dict[str, Any]:
    schema_obj = _schema_obj(COURSE_LABEL_SCHEMA)

    system_instruction = """
You are a data master labeling assistant.

Rules:
- Choose label_code ONLY from the provided list (00-10).
- Use label_definitions to guide your decision.
- Return exactly one result per course in the same order as input.
- If the text is insufficient, set label_code to null and confidence=0.
- Output must strictly follow the JSON schema.
- No extra keys, no free text.
- Return COMPACT one-line JSON only.
- Do not include newline characters in any string.
""".strip()

    config = types.GenerateContentConfig(
        temperature=0.0,
        top_p=0.3,
        top_k=40,
        candidate_count=1,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        response_mime_type="application/json",
        response_schema=schema_obj,
        system_instruction=system_instruction,

    )

    last_err: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(REQUEST_DELAY_SEC)

        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=config,
            )
            text = getattr(resp, "text", None) or ""
            return _safe_json_load(text)

        except Exception as e:
            last_err = e
            msg = str(e)
            # ง่าย ๆ ตามแพตเทิร์นคุณ
            if "429" in msg or "Rate limit" in msg:
                time.sleep(BACKOFF_429_SEC)
            else:
                time.sleep(1.0)

    raise last_err or RuntimeError("Gemini call failed")


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    กันพลาด: ถ้าไฟล์ยังไม่มีคอลัมน์รอบ 1 (เช่นลืมรัน prepare)
    ก็สร้างให้แบบ safe defaults
    """
    needed = [
        "valid1", "label1", "confident1", "derived_eng_desc1",
        "valid2", "label2", "confident2", "derived_eng_desc2",
        "final_label", "final_confident", "derived_eng_desc_final",
    ]
    for c in needed:
        if c not in df.columns:
            df[c] = None

    # ค่าเริ่มต้นรอบ 1
    df["valid1"] = df["valid1"].fillna(0)
    df["confident1"] = df["confident1"].fillna(0)
    return df


# =========================
# Main Loop for valid1
# =========================

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "course4model.csv")

    # ✅ อ่านเต็มไฟล์ (จำเป็นเพราะมีคอลัมน์ valid/label หลัง prepare)
    df = pd.read_csv(
        path,
        sep="|",
        engine="python",
        dtype=str,
        encoding="utf-8-sig",
        on_bad_lines="warn",
    )
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

    # ✅ กันพลาด: สร้างคอลัมน์ที่ต้องใช้ หากยังไม่มี
    df = _ensure_columns(df)

    # ✅ หาแถวที่ยังไม่ผ่าน valid1
    remaining_idx = df.index[df["valid1"].astype(str) == "0"].tolist()

    print(f"[INFO] File: {path}")
    print(f"[INFO] Total rows: {len(df)}")
    print(f"[INFO] valid1=0 remaining: {len(remaining_idx)}")

    if not remaining_idx:
        print("[OK] No rows to label for valid1.")
        return

    batch_no = 0
    success_batches = 0
    failed_batches = 0

    while True:
        remaining_idx = df.index[df["valid1"].astype(str) == "0"].tolist()
        if not remaining_idx:
            break

        batch_no += 1
        idxs = remaining_idx[:BATCH_SIZE]

        # ✅ เตรียม input batch
        courses: List[Dict[str, str]] = []
        for i in idxs:
            row = df.loc[i]
            courses.append({
                "course_id": sanitize_text(row.get("course_id", "")),
                "eng_name": sanitize_text(row.get("eng_name", "")),
                "eng_desc": sanitize_text(row.get("eng_desc", "")),
            })

        prompt = build_prompt(courses)

        try:
            # ✅ เรียก LLM
            result = call_gemini_with_schema(prompt)
            results = result.get("results", [])
            print(result)

            # ✅ map course_id -> row index ของ batch ปัจจุบัน
            batch_id_to_index: Dict[str, int] = {}
            if "course_id" in df.columns:
                for i in idxs:
                    cid = sanitize_text(df.at[i, "course_id"])
                    if cid:
                        batch_id_to_index[cid] = i

            saved = 0
            skipped = 0

            # ✅ Partial save:
            # ไม่ต้องรอให้ครบทั้ง batch
            for r in results:
                cid = sanitize_text(r.get("course_id", ""))
                i = batch_id_to_index.get(cid)

                if i is None:
                    skipped += 1
                    continue

                code = r.get("label_code")
                if code not in LABEL_CODE_MAP:
                    skipped += 1
                    continue

                label_full = LABEL_CODE_MAP.get(code)

                # ✅ อัปเดตเฉพาะแถวที่ match
                df.at[i, "label1"] = label_full
                df.at[i, "confident1"] = str(r.get("confidence", 0) or 0)
                df.at[i, "derived_eng_desc1"] = sanitize_text(r.get("derived_eng_desc1", ""))

                # ✅ ผ่านรอบ valid1 เฉพาะแถวนี้
                df.at[i, "valid1"] = 1

                saved += 1

            print(f"[OK] Batch {batch_no} saved {saved}/{len(idxs)} rows (skipped {skipped})")

            # ✅ เซฟไฟล์ครั้งเดียวหลังจบ batch
            df.to_csv(path, sep="|", index=False, encoding="utf-8-sig")

            success_batches += 1

        except Exception as e:
            failed_batches += 1
            print(f"[WARN] Batch {batch_no} failed: {e}")
            # ไม่แตะ valid1 เพื่อให้รันซ้ำได้

    # สรุป
    rem_final = (df["valid1"].astype(str) == "0").sum()
    print(f"[DONE] success_batches={success_batches}, failed_batches={failed_batches}")
    print(f"[SUMMARY] valid1=0 remaining: {rem_final}")
    print(f"[OK] Saved -> {path}")


if __name__ == "__main__":
    main()
