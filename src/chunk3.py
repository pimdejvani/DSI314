from __future__ import annotations
import re
import os
import json
from io import BytesIO
from typing import List, Dict, Any, Optional

from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

import httplib2
from google_auth_httplib2 import AuthorizedHttp

from google import genai
from google.genai import types

from pypdf import PdfReader, PdfWriter  # pip install pypdf

from http.client import IncompleteRead
from googleapiclient.errors import HttpError
import time, random


# ================= CONFIG =================

SERVICE_ACCOUNT_FILE = "service_account.json"
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = "template"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash"

# ====== Google / Gemini client ======
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)

# ✅ ใส่ timeout ให้ HTTP
authed_http = AuthorizedHttp(creds, http=httplib2.Http(timeout=120))

service_drive = build("drive", "v3", http=authed_http, cache_discovery=False)
service_spread = build("sheets", "v4", http=authed_http, cache_discovery=False).spreadsheets()

client = genai.Client(api_key=GEMINI_API_KEY)


# ================= PDF CACHE =================
_PDF_CACHE: dict[str, bytes] = {}


# ================= HELPERS =================

def _download_pdf_file_bytes_with_retry(
    file_id: str,
    max_attempts: int = 5,
    chunksize: int = 4 * 1024 * 1024,  # ✅ แนะนำ 4MB ลดจำนวนรอบ
    stall_timeout: int = 90,           # ✅ ถ้าไม่คืบหน้าเกิน 90 วิ ให้ถือว่าค้าง
) -> bytes:
    """
    Hybrid downloader:
    1) try fast path: request.execute()
    2) fallback: MediaIoBaseDownload with progress + stall timeout
    """
    last_err = None

    for attempt in range(1, max_attempts + 1):
        try:
            request = service_drive.files().get_media(fileId=file_id)

            # ---------- 1) FAST PATH ----------
            try:
                t0 = time.perf_counter()
                data = request.execute()
                t1 = time.perf_counter()
                print(f"✅ Fast download success {file_id} in {t1 - t0:.2f}s")
                return data
            except Exception as e_fast:
                print(f"⚠️ Fast path failed for {file_id}: {e_fast}")

            # ---------- 2) CHUNKED FALLBACK ----------
            fh = BytesIO()
            downloader = MediaIoBaseDownload(fh, request, chunksize=chunksize)

            done = False
            last_progress = -1
            last_progress_time = time.time()

            while not done:
                status, done = downloader.next_chunk(num_retries=3)

                if status:
                    progress = int(status.progress() * 100)

                    if progress != last_progress:
                        print(f"Downloading {file_id}: {progress}%")
                        last_progress = progress

                    last_progress_time = time.time()

                if time.time() - last_progress_time > stall_timeout:
                    raise TimeoutError(
                        f"Download stalled > {stall_timeout}s (file_id={file_id})"
                    )

            print(f"✅ Chunked download success {file_id}")
            return fh.getvalue()

        except (IncompleteRead, HttpError, OSError, TimeoutError) as e:
            last_err = e
            print(f"⚠️ download attempt {attempt} failed for {file_id}: {e}")

            if attempt == max_attempts:
                raise

            sleep_s = min(2 ** attempt, 30) + random.random()
            time.sleep(sleep_s)

    raise last_err


def download_pdf_pages(
    file_id: str,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
) -> bytes:
    """
    โหลดไฟล์ PDF จาก Google Drive แล้วคืน bytes ของ PDF เฉพาะหน้าที่ต้องการ
    - start_page / end_page เป็นเลขหน้าแบบ 1-based และ end_page เป็นแบบรวมหน้า

    ✅ behavior:
    - โหลดทั้งไฟล์ 1 ครั้ง/ไฟล์ด้วย cache
    - จะตัดหน้าใหม่ตาม start/end
    """

    if file_id not in _PDF_CACHE:
        _PDF_CACHE[file_id] = _download_pdf_file_bytes_with_retry(file_id)

    pdf_bytes = _PDF_CACHE[file_id]

    if start_page is None and end_page is None:
        return pdf_bytes

    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()

    total_pages = len(reader.pages)

    if start_page is None:
        start_page = 1
    if end_page is None:
        end_page = total_pages

    start_page = max(1, start_page)
    end_page = min(total_pages, end_page)

    if start_page > end_page:
        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    for page_num in range(start_page - 1, end_page):
        writer.add_page(reader.pages[page_num])

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def to_int_or_none(v):
    v = str(v).strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def read_rows_from_sheet() -> list[dict[str, str]]:
    """
    อ่านข้อมูลจากชีท 'template':
    - B2:Z2 = header (ชื่อคอลัมน์)
    - B3:Z  = data
    คืนค่า: list ของ dict {column_name: value}
    """
    header_resp = service_spread.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!B2:Z2",
    ).execute()
    headers = header_resp.get("values", [[]])[0]

    data_resp = service_spread.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!B3:Z",
    ).execute()
    data_rows = data_resp.get("values", [])

    rows_dicts: list[dict[str, str]] = []
    for row in data_rows:
        row_dict: dict[str, str] = {}
        for i, h in enumerate(headers):
            if i < len(row):
                row_dict[h] = row[i]
            else:
                row_dict[h] = ""
        rows_dicts.append(row_dict)

    return rows_dicts


def extract_json_object(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    return None


def call_gemini_with_file_and_schema(
    file_bytes: bytes,
    prompt: str,
    schema: dict[str, Any],
) -> dict[str, Any]:

    file_part = types.Part.from_bytes(
        data=file_bytes,
        mime_type="application/pdf",
    )
    prompt_part = types.Part.from_text(text=prompt)

    schema_obj = schema
    SchemaCls = getattr(types, "Schema", None)
    if SchemaCls and hasattr(SchemaCls, "from_dict"):
        schema_obj = SchemaCls.from_dict(schema)

    config = types.GenerateContentConfig(
        temperature=0.0,
        top_p=0.3,
        top_k=40,
        candidate_count=1,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        response_mime_type="application/json",
        response_schema=schema_obj,
        system_instruction=(
            """
            You are an information extraction engine.

            Rules:
            - Use ONLY information that is explicitly present in the provided document (PDF/TXT).
            - Do NOT use outside knowledge.
            - Do NOT guess or infer missing values.
            - If a field is missing or not clearly specified, set it to null.
            - Copy numbers, dates, codes, and names exactly as they appear.
            - If you are uncertain, do not guess; use null.
            - responde same language as appear.

            Output must strictly follow the JSON schema. No extra keys, no free text.
            """
        ),
    )

    config.thinking_config = types.ThinkingConfig(thinking_budget=0)

    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            types.Content(
                role="user",
                parts=[prompt_part, file_part],
            )
        ],
        config=config,
    )

    parsed = getattr(resp, "parsed", None)
    if parsed is not None:
        return parsed

    text = getattr(resp, "text", None)

    if not text:
        for cand in getattr(resp, "candidates", []) or []:
            content = getattr(cand, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []) or []:
                part_text = getattr(part, "text", None)
                if part_text:
                    text = part_text
                    break
            if text:
                break

    if not text:
        print("⚠️ Gemini response has no text or parsed JSON:")
        print(resp)
        return {}
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        candidate = extract_json_object(text)
        if candidate:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        print("⚠️ JSON decode failed. Raw text from Gemini:")
        print(text)
        return {"_raw": text}


# ----------------- sheet utilities -----------------

def col_index_to_letter(col_idx: int) -> str:
    """
    col_idx เป็น 1-based (1=A, 2=B, ...)
    """
    result = ""
    while col_idx > 0:
        col_idx, rem = divmod(col_idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def get_sheet_headers(sheet_name: str) -> List[str]:
    """
    อ่าน header row (B2:AZ) ของชีทที่ต้องการ
    """
    resp = service_spread.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!B2:AZ",
    ).execute()
    headers = resp.get("values", [[]])[0]
    return headers


def make_row_from_item(
    headers: List[str],
    base_row: Optional[Dict[str, Any]],
    item: Optional[Dict[str, Any]],
    extra: Optional[Dict[str, Any]] = None,
) -> List[Any]:
    """
    สร้าง 1 แถวตาม headers:
    priority: extra > item > base_row
    """
    row_values: List[Any] = []
    base_row = base_row or {}
    item = item or {}
    extra = extra or {}

    for h in headers:
        if h in extra:
            v = extra[h]
        elif h in item:
            v = item[h]
        elif h in base_row:
            v = base_row[h]
        else:
            v = ""
        if v is None:
            v = ""
        row_values.append(v)
    return row_values


def append_rows_to_sheet(
    sheet_name: str,
    headers: List[str],
    rows_values: List[List[Any]],
):
    """
    เขียน rows_values ต่อท้ายใน sheet ที่กำหนด โดย
    - สมมติว่า header อยู่ที่แถว 2
    - เริ่มเขียนข้อมูลตั้งแต่คอลัมน์ B เสมอ
    - ใช้ update ลง range เป๊ะ ๆ
    """
    if not rows_values:
        return

    start_col_idx = 2  # B
    end_col_idx = start_col_idx + len(headers) - 1
    end_col_letter = col_index_to_letter(end_col_idx)

    scan_start_row = 2
    col_b_range = f"{sheet_name}!B{scan_start_row}:B"

    resp = service_spread.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=col_b_range,
    ).execute()

    existing = resp.get("values", [])

    if existing:
        last_row = scan_start_row + len(existing) - 1
    else:
        last_row = scan_start_row

    next_row = max(last_row + 1, 3)
    end_row = next_row + len(rows_values) - 1

    target_range = f"{sheet_name}!B{next_row}:{end_col_letter}{end_row}"

    service_spread.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=target_range,
        valueInputOption="RAW",
        body={"values": rows_values},
    ).execute()


def normalize_course_abv(code: Any, lang: str) -> str:
    """
    ทำความสะอาดรหัสวิชาให้เป็นรูปแบบ:
      LETTERS DIGITS
    - ลบ space และจุดออกก่อน
    - ถ้ามีตัวอักษรต่อท้ายหลังตัวเลข จะทิ้งไป
    lang = "th" หรือ "en"
    """
    if code is None:
        return ""
    s = str(code)

    s = s.replace(" ", "").replace("\u00A0", "").replace(".", "")
    if not s:
        return ""

    if lang == "th":
        pattern = r"^([\u0E00-\u0E7Fa-zA-Z]+)(\d+)"
    else:
        pattern = r"^([A-Za-z]+)(\d+)"

    m = re.match(pattern, s)
    if not m:
        return s

    letters, digits = m.group(1), m.group(2)
    return f"{letters} {digits}"


def add_dot_after_th_letter(abv: str) -> str:
    if not abv:
        return abv

    s = abv.strip()
    s = re.sub(
        r'^([A-Za-z\u0E00-\u0E7F]+)\s*\.?\s*(\d+)\b',
        r'\1. \2',
        s
    )
    return s


def normalize_course_item_abv(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    รับ dict ของรายวิชา 1 ตัว
    - แก้รูปแบบ th_abv และ eng_abv ตามกติกา
    - คืน dict ตัวเดิม
    """
    if not isinstance(item, dict):
        return item

    if "th_abv" in item and item["th_abv"]:
        item["th_abv"] = normalize_course_abv(item["th_abv"], "th")
        item["th_abv"] = add_dot_after_th_letter(item["th_abv"])

    if "eng_abv" in item and item["eng_abv"]:
        item["eng_abv"] = normalize_course_abv(item["eng_abv"], "en")

    return item


def update_already_extract_flag(row_idx: int, value: int = 1) -> None:
    """
    อัปเดตค่า already_extract ในชีทต้นทาง
    template ใหม่:
    O = already_extract
    """
    cell_range = f"{SHEET_NAME}!O{row_idx}"

    service_spread.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=cell_range,
        valueInputOption="RAW",
        body={"values": [[str(value)]]},
    ).execute()

def safe_parse_json(text: str) -> dict[str, Any]:
    if not text:
        return {}

    # ตัด code fence เผื่อมี
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)

    # 1) ลอง parse ตรง ๆ
    try:
        obj = json.loads(t)

        # ✅ เผื่อกรณี JSON ถูก encode ซ้อนมาเป็น string
        if isinstance(obj, str):
            try:
                obj2 = json.loads(obj)
                if isinstance(obj2, (dict, list)):
                    return obj2
            except json.JSONDecodeError:
                pass

        if isinstance(obj, (dict, list)):
            return obj
        # ถ้าเป็นอย่างอื่นก็ปล่อยไป fallback
    except json.JSONDecodeError:
        pass

    # 1.5) ลอง extract {...} ก่อน (กรณีมี text เกิน)
    candidate = extract_json_object(t)
    if candidate:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, str):
                try:
                    obj2 = json.loads(obj)
                    if isinstance(obj2, (dict, list)):
                        return obj2
                except json.JSONDecodeError:
                    pass
            if isinstance(obj, (dict, list)):
                return obj
        except json.JSONDecodeError:
            pass

    # 2) ✅ ทำตามลำดับที่คุณต้องการ
    # 2.1 replace "\n" -> ""
    t2 = t.replace("\n", "")

    # 2.2 replace "\" -> " "  (แบ็กสแลชทุกตัว)
    #     ใน python ต้องเขียนเป็น "\\"
    t2 = t2.replace("\\", " ")

    # 2.3 ลอง parse ใหม่
    try:
        obj = json.loads(t2)

        # ✅ เผื่อ double-encoded อีกชั้น
        if isinstance(obj, str):
            try:
                obj2 = json.loads(obj)
                if isinstance(obj2, (dict, list)):
                    return obj2
            except json.JSONDecodeError:
                pass

        if isinstance(obj, (dict, list)):
            return obj

    except json.JSONDecodeError:
        pass

    # 3) ถ้ายังไม่ได้ ให้หยุด
    return {"_raw": text}

# ================= PROMPT & SCHEMA (CHUNK 3 ONLY) =================

content_chunk3 = """ ห้ามตอบคำอธิบายอื่น ให้ตอบเป็น JSON อย่างเดียว ตาม schema ที่กำหนด รายวิชาcollect มาจากบนลงล่าง
th_abv ชื่อรหัสวิชาย่อ ภาษาไทย ,th_name ชื่อวิชาเต็ม ภาษาไทย credit, lect_hours, practice_hours, self_hours 4 อันนี้มาจากหน่อวยกิตของแต่ละวิชา มีโครงสร้างเป็น 'credit (lect_hours-practice_hours-self_hours)' เช่น '3 (3-0-6)' ให้เอามาแค่เลข ,eng_abv ชื่อรหัสวิชาย่อ ภาษาอังกฤษ	,eng_name ชื่อวิชาเต็ม ภาษาอังกฤษ 
,th_desc คำอธิบายรายวิชาภาษาไทย (ไม่ต้องเอา วิชาบังคับก่อน มา) ,Prerequisite เอามาหากว่ามีชื่อรหัสวิชาภาษาอังกฤษมา นอกจากนั้นไม่เอา ไม่เอาเกณฑ์อื่น ,eng_desc คำอธิบายรายวิชาภาษาอังกฤษ (ไม่ต้องเอา Prerequisite มา) 
"""

schema_chunk3 = {
    "type": "OBJECT",
    "properties": {
        "course": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "th_abv": {"type": "STRING", "nullable": True},
                    "th_name": {"type": "STRING", "nullable": True},
                    "credit": {"type": "NUMBER", "nullable": True},
                    "lect_hours": {"type": "INTEGER", "nullable": True},
                    "practice_hours": {"type": "INTEGER", "nullable": True},
                    "self_hours": {"type": "INTEGER", "nullable": True},
                    "eng_abv": {"type": "STRING", "nullable": True},
                    "eng_name": {"type": "STRING", "nullable": True},
                    "th_desc": {"type": "STRING", "nullable": True},
                    "prerequisite": {"type": "STRING", "nullable": True},
                    "eng_desc": {"type": "STRING", "nullable": True},
                },
                "required": [],
            },
        },
    },
    "required": ["course"],
}


# ================= MAIN LOOP (CHUNK 3 ONLY) =================

def main():
    # 1) อ่านแถวจากชีท template
    rows = read_rows_from_sheet()
    print("rows", rows)

    # 2) header ของชีทปลายทาง: ใช้เฉพาะ course
    course_headers = get_sheet_headers("course")
    print("already course headers")

    # 3) loop ทีละแถว
    for row_idx, row in enumerate(rows, start=3):
        pdf_id = row.get("pdf id") or row.get("PDF_ID") or ""

        # เลือกเฉพาะแถวที่ already_extract == 0
        already = str(row.get("already_extract", "")).strip()
        if already != "0":
            continue

        if not pdf_id:
            continue

        row_success = False

        try:
            print(f"\n========== ROW {row_idx} pdf_id={pdf_id} (CHUNK 3 ONLY) ==========\n")

            start = to_int_or_none(row.get("chunk3_start"))
            end = to_int_or_none(row.get("chunk3_end"))

            # base_row สำหรับ sheet อื่น ๆ ที่ "ไม่เอา docx id / pdf id"
            base_row_no_ids = {
                k: v
                for k, v in row.items()
                if k.strip().lower().replace("_", " ") not in {"docx id", "pdf id"}
            }

            print("process download pdf for chunk 3 ...")
            pdf_bytes = download_pdf_pages(pdf_id, start, end)

            print("process gemini for chunk 3 ...")
            result = call_gemini_with_file_and_schema(
                file_bytes=pdf_bytes,
                prompt=content_chunk3,
                schema=schema_chunk3,
            )

            print(f"--- chunk 3 result ---")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print()

            # course descriptions จาก chunk3
            c_list = result.get("course") or []
            chunk3_courses: List[Dict[str, Any]] = []
            if isinstance(c_list, list):
                for c in c_list:
                    if isinstance(c, dict):
                        normalize_course_item_abv(c)
                        chunk3_courses.append(c)

            # append ลงชีท course โดยตรง (ไม่ combine กับ chunk2)
            if chunk3_courses:
                course_values_for_row: List[List[Any]] = []
                for item in chunk3_courses:
                    row_values = make_row_from_item(
                        headers=course_headers,
                        base_row=base_row_no_ids,
                        item=item,
                        extra={"row_index": row_idx, "row_idx": row_idx},
                    )
                    course_values_for_row.append(row_values)

                append_rows_to_sheet("course", course_headers, course_values_for_row)

            # mark ว่าแถวนี้ extract เสร็จแล้ว
            update_already_extract_flag(row_idx, 1)
            row_success = True

            print(f"✅ ROW {row_idx} done (chunk 3 only)")

        except Exception as e:
            print(f"❌ Error on row {row_idx} pdf_id={pdf_id}: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # ล้าง cache เฉพาะไฟล์นี้เมื่อจบแถว
            if pdf_id:
                _PDF_CACHE.pop(pdf_id, None)

            if not row_success:
                print(f"⚠️ ROW {row_idx} not completed, cache cleared, will retry next run")


if __name__ == "__main__":
    main()
