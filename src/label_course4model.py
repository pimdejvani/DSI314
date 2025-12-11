import os
import time
import json
import glob
import threading
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple, Optional

from google import genai
from google.genai import types


# =========================
# Paths / Env
# =========================
DEFAULT_BASE = "/app/src/course4model"
COURSE4MODEL_PATH = os.getenv("COURSE4MODEL_PATH", DEFAULT_BASE)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# งาน label ปริมาณมากแนะนำ flash
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

BATCH_SIZE = int(os.getenv("PHI_BATCH_SIZE", "10"))
MAX_WORKERS = int(os.getenv("PHI_WORKERS", "3"))
REQUEST_DELAY_SEC = float(os.getenv("PHI_REQUEST_DELAY", "0.5"))
BACKOFF_429_SEC = float(os.getenv("PHI_BACKOFF_429", "8"))
MAX_RETRIES = int(os.getenv("PHI_MAX_RETRIES", "5"))
TIMEOUT = int(os.getenv("PHI_TIMEOUT", "60"))

# log/checkpoint
PROGRESS_EVERY_BATCHES = int(os.getenv("PHI_PROGRESS_EVERY", "20"))
CHECKPOINT_EVERY_BATCHES = int(os.getenv("PHI_CHECKPOINT_EVERY", "25"))

FAIL_FAST = os.getenv("PHI_FAIL_FAST", "0") == "1"


# =========================
# Label Map
# =========================
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

LABELS = list(LABEL_MAP.keys())


# =========================
# Response Schema (ล็อก JSON)
# =========================
# หมายเหตุ: SDK ปัจจุบันรองรับ schema แบบ dict ได้ในหลายเคส
# เราทำโครงสร้างให้ง่ายและเคร่งพอที่จะลด JSON พัง
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "results": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "eng_abv": {"type": "STRING"},
                    "label": {"type": "STRING", "nullable": True},
                    "confidence": {"type": "NUMBER"},
                    "derived_eng_desc1": {"type": "STRING"},
                },
                "required": ["eng_abv", "label", "confidence", "derived_eng_desc1"],
            },
        }
    },
    "required": ["results"],
}


# =========================
# Gemini Client
# =========================
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)


# =========================
# Helpers
# =========================
def _resolve_path(base: str) -> str:
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
    # ลองอ่านแบบ | ก่อน
    try:
        df = pd.read_csv(path, sep="|", dtype=str, encoding="utf-8-sig")
    except Exception:
        # ให้ pandas เดา delimiter
        df = pd.read_csv(path, sep=None, engine="python", dtype=str, encoding="utf-8-sig")

    # normalize header เผื่อ BOM/space
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    return df


def sanitize_text(s: Optional[str]) -> str:
    """
    ตามสเปกคุณ:
    - ตัด \n และ \
    - รวมถึงอักขระพิเศษแบบเบา ๆ (เราจะเน้นลบ backslash/newline)
    """
    if s is None:
        return ""
    s = str(s)
    s = s.replace("\\", "")
    s = s.replace("\n", "").replace("\r", "")
    s = " ".join(s.split())
    return s.strip()


def build_prompt(courses: List[Dict[str, str]]) -> Tuple[str, str]:
    system = (
        "You are a data master labeling assistant. "
        "Output ONLY valid JSON. No markdown. No extra text. Read every text."
    )

    user_obj = {
        "task": "batch_label_courses",
        "label_definitions": LABEL_MAP,
        "labels": LABELS,
        "courses": [
            {
                "eng_abv": c.get("eng_abv", ""),
                "eng_name": c.get("eng_name", ""),
                "eng_desc": c.get("eng_desc", ""),
            }
            for c in courses
        ],
        "output_format": {
            "results": [
                {
                    "eng_abv": "string",
                    "label": "string or null",
                    "confidence": "number 0-1",
                    "derived_eng_desc1": "string"
                }
            ]
        },
        "strict": [
            "Return exactly one result per course in the same order as input.",
            "Choose label only from the provided labels.",
            "Use label_definitions to guide your decision.",
            "derived_eng_desc1 is a short rationale of why you chose the label (<= 20 words).",
            "If the text is insufficient, set label=null and confidence=0."
        ]
    }

    user_text = json.dumps(user_obj, ensure_ascii=False)
    return system, user_text


def _safe_load_json(text: str) -> Dict[str, Any]:
    """
    กันกรณีโมเดลหลุด format เล็กน้อย:
    - มี ```json ... ```
    - มี text แถมก่อน/หลัง
    """
    if text is None:
        raise ValueError("Empty response text")

    t = text.strip()
    t = t.replace("```json", "").replace("```JSON", "").replace("```", "").strip()

    # ดึงช่วง {...}
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]

    return json.loads(t)


def call_gemini(system_instruction: str, user_text: str) -> Dict[str, Any]:
    last_err: Optional[Exception] = None

    # config แบบ “ล็อก schema”
    config_strict = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0,
        max_output_tokens=900,
        response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA,
    )

    # config สำรอง ถ้า SDK ไม่รับ schema ในบาง environment
    config_loose = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0,
        max_output_tokens=900,
        response_mime_type="application/json",
    )

    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(REQUEST_DELAY_SEC)

        # รอบแรกพยายามแบบ strict
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_text,
                config=config_strict,
            )
            text = getattr(resp, "text", None) or ""
            return _safe_load_json(text)

        except Exception as e_strict:
            # ถ้า error เกี่ยวกับ schema ให้ fallback แบบ loose ภายใน attempt เดียวกัน
            try:
                resp = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=user_text,
                    config=config_loose,
                )
                text = getattr(resp, "text", None) or ""
                return _safe_load_json(text)

            except Exception as e:
                last_err = e
                msg = str(e)

                if "429" in msg or "Rate limit" in msg:
                    time.sleep(BACKOFF_429_SEC)
                else:
                    time.sleep(1.0)

    raise last_err or RuntimeError("Gemini call failed")


def batchify(rows: List[int], batch_size: int) -> List[List[int]]:
    return [rows[i:i + batch_size] for i in range(0, len(rows), batch_size)]


def _extract_results(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = obj.get("results")
    if isinstance(results, list):
        return results
    if isinstance(obj, list):
        return obj
    return []


def process_one_batch(df: pd.DataFrame, idxs: List[int]) -> Tuple[List[int], List[Dict[str, Any]]]:
    courses = []
    for i in idxs:
        row = df.loc[i]
        courses.append({
            "eng_abv": sanitize_text(row.get("eng_abv", "")),
            "eng_name": sanitize_text(row.get("eng_name", "")),
            "eng_desc": sanitize_text(row.get("eng_desc", "")),
        })

    system, user_text = build_prompt(courses)
    result_obj = call_gemini(system, user_text)

    results = _extract_results(result_obj)
    if not results:
        raise ValueError(f"Unexpected response shape: {result_obj}")

    cleaned: List[Dict[str, Any]] = []
    for r in results:
        label = r.get("label", None)
        # กันหลุด label นอกลิสต์
        if label not in LABELS:
            # ถ้าไม่ตรง ให้ถือว่าไม่มั่นใจ
            label = None

        cleaned.append({
            "eng_abv": sanitize_text(r.get("eng_abv", "")),
            "label": label,
            "confidence": float(r.get("confidence", 0) or 0),
            "derived_eng_desc1": sanitize_text(r.get("derived_eng_desc1", "")),
        })

    return idxs, cleaned


# =========================
# Main
# =========================
def main():
    path = _resolve_path(COURSE4MODEL_PATH)
    df = _read_any(path)

    required = [
        "course_id", "eng_abv", "eng_name", "eng_desc",
        "valid1", "label1", "confident1", "derived_eng_desc1"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing columns {missing}. "
            "Please run prepare_course4model.py first."
        )

    total_rows = len(df)
    valid1_0_idx = df.index[df["valid1"].astype(str) == "0"].tolist()
    valid1_1_count = (df["valid1"].astype(str) == "1").sum()

    print(f"[INFO] Dataset: {path}")
    print(f"[INFO] Total rows: {total_rows}")
    print(f"[INFO] valid1=1 already: {valid1_1_count}")
    print(f"[INFO] valid1=0 to process now: {len(valid1_0_idx)}")

    if not valid1_0_idx:
        print("[OK] No rows to label (valid1 == 0).")
        return

    batches = batchify(valid1_0_idx, BATCH_SIZE)
    total_batches = len(batches)
    print(f"[INFO] Batch size: {BATCH_SIZE} -> {total_batches} batches")
    print(f"[INFO] Workers: {MAX_WORKERS}, delay={REQUEST_DELAY_SEC}s, backoff429={BACKOFF_429_SEC}s")

    # progress counters
    lock = threading.Lock()
    done_batches = 0
    failed_batches = 0
    labeled_rows_this_run = 0

    def maybe_log_progress():
        nonlocal done_batches, failed_batches, labeled_rows_this_run
        if done_batches % PROGRESS_EVERY_BATCHES == 0 or done_batches == total_batches:
            print(
                f"[PROGRESS] batches done {done_batches}/{total_batches} | "
                f"failed {failed_batches} | "
                f"rows labeled this run ~{labeled_rows_this_run}"
            )

    def checkpoint_save():
        df.to_csv(path, sep="|", index=False, encoding="utf-8-sig")
        print(f"[CHECKPOINT] Saved -> {path}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(process_one_batch, df, b) for b in batches]

        for fut in as_completed(futures):
            try:
                idxs, results = fut.result()
            except Exception as e:
                with lock:
                    failed_batches += 1
                    done_batches += 1
                    print(f"[WARN] Batch failed: {e}")
                    maybe_log_progress()
                    if CHECKPOINT_EVERY_BATCHES and done_batches % CHECKPOINT_EVERY_BATCHES == 0:
                        checkpoint_save()
                if FAIL_FAST:
                    raise
                continue

            if len(results) != len(idxs):
                with lock:
                    failed_batches += 1
                    done_batches += 1
                    print("[WARN] Batch size mismatch, skipping valid1 update for this batch")
                    maybe_log_progress()
                    if CHECKPOINT_EVERY_BATCHES and done_batches % CHECKPOINT_EVERY_BATCHES == 0:
                        checkpoint_save()
                if FAIL_FAST:
                    raise ValueError("Batch size mismatch")
                continue

            # update df รอบ 1
            for i, r in zip(idxs, results):
                df.at[i, "label1"] = r["label"]
                df.at[i, "confident1"] = r["confidence"]
                df.at[i, "derived_eng_desc1"] = r["derived_eng_desc1"]

            # ถ้าใส่ได้ครบทุกอันให้ valid1 = 1
            for i in idxs:
                df.at[i, "valid1"] = 1

            with lock:
                done_batches += 1
                labeled_rows_this_run += len(idxs)
                maybe_log_progress()
                if CHECKPOINT_EVERY_BATCHES and done_batches % CHECKPOINT_EVERY_BATCHES == 0:
                    checkpoint_save()

    # save final
    df.to_csv(path, sep="|", index=False, encoding="utf-8-sig")

    # summary after run
    valid1_0_after = (df["valid1"].astype(str) == "0").sum()
    valid1_1_after = (df["valid1"].astype(str) == "1").sum()

    print(f"[OK] Labeled and overwritten: {path}")
    print(
        f"[SUMMARY] total rows={total_rows} | "
        f"valid1=1 now={valid1_1_after} | "
        f"valid1=0 remaining={valid1_0_after} | "
        f"failed batches={failed_batches}"
    )
    print("[TIP] Re-run this script to automatically continue remaining valid1=0 rows.")


if __name__ == "__main__":
    main()
