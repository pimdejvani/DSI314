from __future__ import annotations
import re
import os
import json
from io import BytesIO
from typing import List, Dict, Any, Optional

from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

from google import genai
from google.genai import types

from pypdf import PdfReader, PdfWriter  # pip install pypdf


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
service_drive = build("drive", "v3", credentials=creds)
service_spread = build("sheets", "v4", credentials=creds).spreadsheets()

client = genai.Client(api_key=GEMINI_API_KEY)


# ================= HELPERS =================

def download_pdf_pages(
    file_id: str,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
) -> bytes:
    request = service_drive.files().get_media(fileId=file_id)
    fh = BytesIO()

    # เพิ่ม chunksize ให้ใหญ่ขึ้นลดโอกาสหลุด
    downloader = MediaIoBaseDownload(fh, request, chunksize=1024 * 1024)

    done = False
    while not done:
        # ให้ตัวไลบรารี retry เอง
        _, done = downloader.next_chunk(num_retries=5)

    pdf_bytes = fh.getvalue()

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
    อ่านข้อมูลจากชีท 'test':
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

    # ✅ แปลง schema เป็น object ถ้า SDK มีให้ใช้
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

    # ---------- 1) ใช้ resp.parsed ก่อน ----------
    parsed = getattr(resp, "parsed", None)
    if parsed is not None:
        return parsed

    # ---------- 2) fallback: text + json.loads ----------
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




def extract_json_object(text: str) -> Optional[str]:
    if not text:
        return None
    # ตัด code fence เผื่อมี
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # หา {...} ก้อนใหญ่สุดแบบง่าย ๆ
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    return None
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
    อ่าน header row (B2:Z2) ของชีทที่ต้องการ
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


def write_information_row(
    row_index: int,
    info_headers: List[str],
    info_data: Dict[str, Any],
):
    """
    เขียนข้อมูลของ 1 หลักสูตร (1 แถว) ลงชีท 'information'
    - row_index: แถวของชีทที่ต้องการเขียน (3,4,...)
    - info_headers: header ของชีท 'information'
    - info_data: dict รวมฟิลด์ scalar จาก chunk1,2,4
    """
    row_values: List[Any] = []
    for h in info_headers:
        v = info_data.get(h, "")
        if v is None:
            v = ""
        row_values.append(v)

    start_col_idx = 2  # B
    end_col_idx = start_col_idx + len(info_headers) - 1
    end_col_letter = col_index_to_letter(end_col_idx)

    service_spread.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"information!B{row_index}:{end_col_letter}{row_index}",
        valueInputOption="RAW",
        body={"values": [row_values]},
    ).execute()


def append_rows_to_sheet(
    sheet_name: str,
    headers: List[str],
    rows_values: List[List[Any]],
):
    """
    เขียน rows_values ต่อท้ายใน sheet ที่กำหนด โดย
    - สมมติว่า header อยู่ที่แถว 2 (B2, C2, ...)
    - เริ่มเขียนข้อมูลตั้งแต่คอลัมน์ B เสมอ
    - ไม่ใช้ values.append แล้ว เพื่อเลี่ยงปัญหา table detection
    """
    if not rows_values:
        return

    # ===== 1) คำนวณคอลัมน์เริ่ม / คอลัมน์สุดท้าย =====
    start_col_idx = 2  # B
    end_col_idx = start_col_idx + len(headers) - 1
    end_col_letter = col_index_to_letter(end_col_idx)

    # ===== 2) หาแถวสุดท้ายที่มีข้อมูลในคอลัมน์ B =====
    # สมมติ header อยู่ที่ B2 ดังนั้นเราสแกน B2 ลงมา
    scan_start_row = 2
    col_b_range = f"{sheet_name}!B{scan_start_row}:B"

    resp = service_spread.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=col_b_range,
    ).execute()

    existing = resp.get("values", [])

    if existing:
        # แถวสุดท้าย = แถวเริ่ม + (จำนวนแถวข้อมูล - 1)
        last_row = scan_start_row + len(existing) - 1
    else:
        # ถ้าไม่มีอะไรเลยใน B2 ลงมา ให้ถือว่า last_row = แถว header
        last_row = scan_start_row

    # แถวถัดไปที่เราจะเริ่มเขียน (อย่างน้อยต้องไม่ต่ำกว่า 3)
    next_row = max(last_row + 1, 3)

    # จำนวนแถวที่เราจะเขียน
    end_row = next_row + len(rows_values) - 1

    target_range = f"{sheet_name}!B{next_row}:{end_col_letter}{end_row}"

    # ===== 3) ใช้ update เขียนลง range เป๊ะ ๆ =====
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

    # ลบ space ทั่วไป, non-breaking space, และจุด
    s = s.replace(" ", "").replace("\u00A0", "").replace(".", "")

    if not s:
        return ""

    # pattern: ตัวอักษร + ตัวเลข (ไม่สนว่ามีอะไรต่อท้าย)
    if lang == "th":
        # ตัวอักษรไทย + อังกฤษ เผื่อกรณีปนกัน
        pattern = r"^([\u0E00-\u0E7Fa-zA-Z]+)(\d+)"
    else:
        # อังกฤษล้วน
        pattern = r"^([A-Za-z]+)(\d+)"

    m = re.match(pattern, s)
    if not m:
        # ถ้าจับ pattern ไม่ได้ ก็คืนค่าที่ล้างแล้วเฉย ๆ
        return s

    letters, digits = m.group(1), m.group(2)
    return f"{letters} {digits}"


def add_dot_after_th_letter(abv: str) -> str:
    if not abv:
        return abv

    s = abv.strip()

    # กลุ่มตัวอักษร (ไทย/อังกฤษ) ตามด้วยเลข
    # รองรับทั้ง "ก 1", "ก1", "ก.1", "บช 101" ฯลฯ
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
    - คืน dict ตัวเดิม (แก้ในที่เดิม)
    """
    if not isinstance(item, dict):
        return item

    if "th_abv" in item and item["th_abv"]:
        item["th_abv"] = normalize_course_abv(item["th_abv"], "th")
        # ✅ เติมจุดหลังอักษร เมื่อเจอแพทเทิร์น อักษร+เลข
        item["th_abv"] = add_dot_after_th_letter(item["th_abv"])

    if "eng_abv" in item and item["eng_abv"]:
        item["eng_abv"] = normalize_course_abv(item["eng_abv"], "en")

    return item

def normalize_course_code(val: Any) -> str:
    """
    แปลงรหัสวิชาให้พร้อมใช้เป็น key สำหรับ match:
    - แปลงเป็น string
    - เก็บไว้เฉพาะ: [0-9], [A-Z], [a-z], และอักขระในช่วงภาษาไทย [\u0E00-\u0E7F]
    - ตัวอื่น ๆ (ช่องว่าง, dash, วงเล็บ, zero-width ฯลฯ) ถูกลบทิ้ง
    """
    if val is None:
        return ""
    s = str(val)

    keep: list[str] = []
    for ch in s:
        if ("0" <= ch <= "9") or ("A" <= ch <= "Z") or ("a" <= ch <= "z") or ("\u0E00" <= ch <= "\u0E7F"):
            keep.append(ch)
    return "".join(keep)


# ----------------- รวม course chunk2 + chunk3 ในแถวนั้น ๆ -----------------

def combine_course_items_for_row(
    struct_courses: List[Dict[str, Any]],
    desc_courses: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    รวม course จาก chunk2 (struct_courses) + chunk3 (desc_courses)
    โดยจับคู่แบบ:
    - eng_abv ของ chunk2 กับ eng_abv ของ chunk3 (หลัง normalize)
    - th_abv ของ chunk2 กับ th_abv ของ chunk3 (หลัง normalize)

    ถ้า match อย่างใดอย่างหนึ่ง -> merge เป็นรายวิชาเดียวกัน
    ถ้าไม่มีทั้ง eng_abv และ th_abv -> ไม่ join กับใคร, เก็บเป็น no_code_items
    """

    # index แยกตามภาษา
    index_eng: Dict[str, Dict[str, Any]] = {}
    index_th: Dict[str, Dict[str, Any]] = {}
    no_code_items: List[Dict[str, Any]] = []

    def get_eng_code(item: Dict[str, Any]) -> str:
        return normalize_course_code(item.get("eng_abv"))

    def get_th_code(item: Dict[str, Any]) -> str:
        return normalize_course_code(item.get("th_abv"))

    def merge_into_index(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        พยายามหาว่ารายการนี้เคยมีอยู่ใน index แล้วหรือยัง (ทั้ง eng และ th)
        - ถ้ามี -> update dict เดิม
        - ถ้าไม่มี -> สร้าง dict ใหม่ แล้วเก็บลง index_eng/index_th ตาม code ที่มี
        คืนค่า merged dict ที่ใช้จริง (เพื่อใช้ต่อถ้าจำเป็น)
        """
        eng_code = get_eng_code(item)
        th_code = get_th_code(item)

        # ไม่มี code เลย -> ไม่ join กับใคร
        if not eng_code and not th_code:
            return None

        merged: Optional[Dict[str, Any]] = None

        # 1) ลองหาจาก eng_abv ก่อน
        if eng_code and eng_code in index_eng:
            merged = index_eng[eng_code]

        # 2) ถ้าไม่เจอ ลองจาก th_abv
        if merged is None and th_code and th_code in index_th:
            merged = index_th[th_code]

        # 3) ถ้ายังไม่เจอเลย -> สร้างใหม่
        if merged is None:
            merged = {}

        # อัปเดตข้อมูลจาก item ลงไป
        merged.update(item)

        # ผูก merged เข้ากับ index ทั้งสอง (ถ้ามี code)
        if eng_code:
            index_eng[eng_code] = merged
        if th_code:
            index_th[th_code] = merged

        return merged

    # ---------- 1) ใส่ของ chunk2 (โครงสร้างหลักสูตร) ก่อน ----------
    for c in struct_courses:
        if not isinstance(c, dict):
            continue
        merged = merge_into_index(c)
        if merged is None:
            # ไม่มี code -> ไม่ join กับใคร
            no_code_items.append(c.copy())

    # ---------- 2) ใส่ของ chunk3 (คำอธิบายรายวิชา) ทับเข้าไป ----------
    for c in desc_courses:
        if not isinstance(c, dict):
            continue
        merged = merge_into_index(c)
        if merged is None:
            # ไม่มี code -> ไม่ join กับใคร
            no_code_items.append(c.copy())

    # ---------- 3) รวบรวมผลลัพธ์ ----------
    # index_eng / index_th อาจชี้ไปยัง dict เดียวกันหลาย key
    # เลยต้อง dedupe ด้วย id()
    unique_map: Dict[int, Dict[str, Any]] = {}
    for v in list(index_eng.values()) + list(index_th.values()):
        unique_map[id(v)] = v

    combined = list(unique_map.values()) + no_code_items
    return combined

def update_already_extract_flag(row_idx: int, value: int = 1) -> None:
    """
    อัปเดตค่า already_extract ในชีทต้นทาง
    row_idx = เลขแถวจริงใน Google Sheet (3,4,5,...)
    template ใหม่เริ่มที่ B2:
    B:faculty, C:degree, D:curriculum, E:docx id, F:pdf id,
    G:chunk1_start, H:chunk1_end, I:chunk2_start, J:chunk2_end,
    K:chunk3_start, L:chunk3_end, M:chunk4_start, N:chunk4_end,
    O:already_extract, P:finish_info, Q:finish_course, R:DONE
    """
    cell_range = f"{SHEET_NAME}!O{row_idx}"  # O = already_extract

    service_spread.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=cell_range,
        valueInputOption="RAW",
        body={"values": [[str(value)]]},
    ).execute()


# ================= PROMPT & SCHEMA =================

content_chunk1 = """จากในไฟล์ที่ทำการ extract เรียงจากบนลงล่าง ห้ามตอบคำอธิบายอื่น ให้ตอบเป็น JSON อย่างเดียว ตาม schema ที่กำหนด
หมวดที่ 1 จะมี  curr_id รหัสหลักสูตร curr_name_th ชื่อหลักสูตรภาษาไทย curr_name_en ชื่อหลักสูตรภาษาอังกฤษ	degree_full_th ชื่อปริญญาและสาขาวิชาภาษาไทยชื่อเต็ม degree_full_en ชื่อปริญญาและสาขาวิชาภาษาอังกฤษชื่อเต็ม degree_abr_th ชื่อปริญญาและสาขาวิชาภาษาไทยชื่อย่อ degree_abr_en ชื่อปริญญาและสาขาวิชาภาษาอังกฤษชื่อย่อ 
curr_category_id รูปแบบ จาก รูปแบบของหลักสูตร หมวดที่เจอคำคล้ายๆว่า 'หลักสูตรระดับปริญญาตรี 4 ปี หรือต่อเนื่อง' (เอามาเฉพาะค่าที่ถูกเลือก) curr_type_id ประเภทของหลักสูตร จาก รูปแบบของหลักสูตร (เอามาเฉพาะค่าที่ถูกเลือก) lang_id ภาษาที่ใช้ จาก รูปแบบของหลักสูตร หมวดที่เจอคำคล้ายๆว่า 'จัดการศึกษาเป็นภาษาไทย' (เอามาเฉพาะค่าที่ถูกเลือก) mou ความร่วมมือกับสถาบันอื่น จาก รูปแบบของหลักสูตร เป็นหมวดที่เจอคำคล้ายๆว่า 'เป็นหลักสูตรของสถาบันโดยเฉพาะ'(เอามาเฉพาะค่าที่ถูกเลือก) first_open_semester สถานภาพของหลักสูตรและการพิจารณาอนุมัติ/เห็นชอบหลักสูตร จาก รูปแบบของหลักสูตร ให้เอาเลขภาคการศึกษาที่เปิดสอนมาใส่ first_open_year สถานภาพของหลักสูตรและการพิจารณาอนุมัติ/เห็นชอบหลักสูตร จาก รูปแบบของหลักสูตร ให้เอาเลขปีการศึกษาที่เปิดสอนมาใส่ 
careers อาชีพที่สามารถประกอบได้หลังสำเร็จการศึกษา จาก รูปแบบของหลักสูตร (ไม่เอาลำดับข้อ หากมีหลายตัวอยากให้ใช้ ,) campus_id สถานที่จัดการเรียนการสอน จาก รูปแบบของหลักสูตร (เอามาเฉพาะค่าที่ถูกเลือก หากมีหลายตัวอยากให้ใช้ ,) expense_type ประเภทโครงการ จากประเภทโครงการ จากรูปแบบ 
หมวดที่ 2 student_nation_id การรับเข้าศึกษา (เอามาเฉพาะค่าที่ถูกเลือก) qualification_collegian คุณสมบัติของผู้เข้าศึกษา (เอามาแค่เฉพาะเนื้อหาในเกณฑ์ที่เป็นข้อๆ ไม่เอาอักษรพิเศษ ไม่เอาลำดับข้อ หากมีหลายข้อให้ใช้ , )

หมวดที่ 3 type_plo ใน ผลลัพธ์การเรียนรู้ระดับหลักสูตร (เป็นเกณฑ์ภาษาอังกฤษที่มีลำดับ เช่น plo1 plo2 k2 s2 e1 c1 เอามาแค่ตัวอักษร) num_plo ใน ผลลัพธ์การเรียนรู้ระดับหลักสูตร (เป็นเกณฑ์ภาษาอังกฤษที่มีลำดับ เช่น plo1 plo2 k2 s2 e1 c1 เอามาแค่ตัวเลข) detail_plo ใน ผลลัพธ์การเรียนรู้ระดับหลักสูตร (เป็นเกณฑ์ภาษาอังกฤษที่มีลำดับ เช่น PLO 1 PLO 2 K2 S2 E1 C1 เอามาแค่คำอธิบายของเกณฑ์นั้น)
"""

schema_chunk1 = {
    "type": "OBJECT",
    "properties": {
        "curr_id": {"type": "STRING", "nullable": True},
        "curr_name_th": {"type": "STRING", "nullable": True},
        "curr_name_en": {"type": "STRING", "nullable": True},
        "degree_full_th": {"type": "STRING", "nullable": True},
        "degree_full_en": {"type": "STRING", "nullable": True},
        "degree_abr_th": {"type": "STRING", "nullable": True},
        "degree_abr_en": {"type": "STRING", "nullable": True},
        "curr_category_id": {"type": "STRING", "nullable": True},
        "curr_type_id": {"type": "STRING", "nullable": True},
        "lang_id": {"type": "STRING", "nullable": True},
        "mou": {"type": "STRING", "nullable": True},
        "first_open_semester": {"type": "INTEGER", "nullable": True},
        "first_open_year": {"type": "INTEGER", "nullable": True},
        "careers": {"type": "STRING", "nullable": True},
        "campus_id": {"type": "STRING", "nullable": True},
        "expense_type": {"type": "STRING", "nullable": True},
        "student_nation_id": {"type": "STRING", "nullable": True},
        "qualification_collegian": {"type": "STRING", "nullable": True},
        "plo": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "type_plo": {"type": "STRING", "nullable": True},
                    "num_plo": {"type": "INTEGER", "nullable": True},
                    "detail_plo": {"type": "STRING", "nullable": True},
                },
                "required": [],
            },
        },
    },
    "required": [],
}

content_chunk2 = """จากในไฟล์ที่ทำการ extract ค่อนข้างเรียงจากบนลงล่าง อย่าลืมสองหน้าแรก ห้ามตอบคำอธิบายอื่น ให้ตอบเป็น JSON อย่างเดียว ตาม schema ที่กำหนด
max_semester ระยะเวลาการศึกษาสูงสุด จาก ระบบการจัดการศึกษาและระยะเวลาการศึกษา (เอามาเฉพาะค่าที่ถูกเลือกและเอามาแค่เลข) day_class วัน-เวลาในการดำเนินการเรียนการสอน จาก การดำเนินการหลักสูตร (เอามาเฉพาะค่าที่ถูกเลือก หากมีหลายค่าให้ใช้ ,) type_class ระบบการศึกษา จาก การดำเนินการหลักสูตร (เอามาเฉพาะค่าที่ถูกเลือก หากมีหลายค่าให้ใช้ ,)
#'หากหลักสูตรมีหลายรูปแบบให้เลือก เลือกรูปแบบแรก' total_credits จำนวนหน่วยกิตรวม จาก หลักสูตร ใน โครงสร้างหลักสูตร รายวิชา และหน่วยกิต (เอามาแค่ค่าผลรวม) gen_ed_credits จำนวนหน่วยกิตรวม 'วิชาศึกษาทั่วไป' จาก หลักสูตร ใน โครงสร้างหลักสูตร (เอามาแค่ค่าผลรวม) spec_credits จำนวนหน่วยกิตรวม 'วิชาเฉพาะ' จาก หลักสูตร ใน โครงสร้างหลักสูตร (เอามาแค่ค่าผลรวม)  elec_credits จำนวนหน่วยกิตรวม วิชาเลือก/วิชาโท/วิชาภาคปฏิบัติ (ปล.อาจมีความต่างเล็กน้อย บางครั้งก็ไม่มี หรืออาจมีแค่คำเดียวจากในนี้) จาก หลักสูตร ใน โครงสร้างหลักสูตร (เอามาแค่ค่าผลรวม)  free_elec_credits จำนวนหน่วยกิตรวม 'วิชาเลือกเสรี' จาก หลักสูตร ใน โครงสร้างหลักสูตร (เอามาแค่ค่าผลรวม) โดยทั้ง 4 ตัว เมื่อดูที่หัวข้อนั้นอยู่ระกับเดียวกัน เช่น หัวข้อ 1 ,2 ,3 ,4
course_type_id ประเภทของวิชาหลัก (จะเป็นคำว่า 'วิชาศึกษาทั่วไป', 'วิชาเฉพาะ' ,'วิชาเลือกเสรี' หรือ 'วิชาเลือก หรือ วิชาโท หรือ วิชาโท/วิชาภาคปฏิบัติ/ศึกษาค้นคว้าด้วยตนเอง' โดยอาจต้องเลื่อนขึ้นไปดูข้างบนอยู่บ้าง)  ,th_abv รหัสวิชาย่อ ภาษาไทย ,eng_abv รหัสวิชาย่อ ภาษาอังกฤษ
"""

schema_chunk2 = {
    "type": "OBJECT",
    "properties": {
        "day_class": {"type": "STRING", "nullable": True},
        "type_class": {"type": "STRING", "nullable": True},
        "max_semester": {"type": "INTEGER", "nullable": True},
        "total_credits": {"type": "NUMBER", "nullable": True},
        "gen_ed_credits": {"type": "NUMBER", "nullable": True},
        "spec_credits": {"type": "NUMBER", "nullable": True},
        "elec_credits": {"type": "NUMBER", "nullable": True},
        "free_elec_credits": {"type": "NUMBER", "nullable": True},
        "course": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "course_type_id": {"type": "STRING", "nullable": True},
                    "th_abv": {"type": "STRING", "nullable": True},
                    # "th_name": {"type": "STRING", "nullable": True},
                    "eng_abv": {"type": "STRING", "nullable": True},
                    # "eng_name": {"type": "STRING", "nullable": True},

                },
                "required": [],
            },
        },
    },
    "required": [],
}

content_chunk3 = """ ห้ามตอบคำอธิบายอื่น ให้ตอบเป็น JSON อย่างเดียว ตาม schema ที่กำหนด
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
                # ถ้าเจอ error เรื่อง additionalProperties ค่อยลบบรรทัดนี้ทิ้ง
                # "additionalProperties": False,
            },
        },
    },
    "required": ["course"],
    # ถ้าเจอ error เรื่อง additionalProperties ค่อยลบบรรทัดนี้ทิ้ง
    # "additionalProperties": False,
}

content_chunk4 = """จากในไฟล์ที่ทำการ extract ค่อนข้างเรียงจากบนลงล่าง ห้ามตอบคำอธิบายอื่น ให้ตอบเป็น JSON อย่างเดียว ตาม schema ที่กำหนด
หมวดที่ 6 count_research งานวิจัยหรือ บทความวิจัย (ชิ้น) จาก ด้านวิชาการ count_academic_paper ผลงานทางวิชาการอื่น ๆ จาก ด้านวิชาการ count_lecturer_academic จำนวนอาจารย์ประจำหลักสูตร (คน) จาก ด้านวิชาการ
count_lecturer_full จำนวนอาจารย์ประจำไม่ว่าชนชาติใดรวม จาก ด้านการบริหารจัดการ (เอามาแค่เลข) count_lecturer_extra  จำนวนอาจารย์พิเศษรวม (เอามาแค่เลข) จาก ด้านการบริหารจัดการ count_staff จำนวนเจ้าหน้าที่ (เอามาแค่เลข) จาก ด้านการบริหารจัดการ
qualification_responsible, name_responsible, degree_reponsible, program_responsible, institute_responsible, year_graduate_responsible เป็นข้อมูลจากตารางของอาจารย์ผู้รับผิดชอบหลักสูตรและอาจารย์ประจำหลักสูตร บางทีอาจมีอาจารย์ท่านอื่นด้วย แต่เอาเฉพาะอาจารย์ผู้รับผิดชอบ โดยqualification_responsible ตำแหน่งทางวิชาการ,name_responsible ชื่อ - สกุล, degree_reponsible คุณวุฒิ, program_responsible สาขาวิชา, institute_responsible สถาบัน, year_graduate_responsible ปีพ.ศ. เอามาแค่เลข
หมวดที่ 7 other_grade เป็นเกณฑ์การประเมิณที่ไม่ใช่เกรด A-F ให้เก็บใน format 'ตัวย่ออังกฤษ(ความหมายภาษาไทย)' เช่น 'S(ใช้ได้)' (ถ้ามีหลายตัวให้ใส่มาทั้งหมดแล้วใช้ ,) criteria_graduate เกณฑ์การสําเร็จการศึกษาตามหลักสูตร ให้เอามาเฉพาะเกณฑ์ที่ทำให้สำเร็จการศึกษาทที่เป็นข้อๆ แต่เอาข้อออก ให้ใส่มารวมกันแล้วใช้ ,
หมวดที่ 8 และ 9 curr_qa ชื่อเกณฑ์ในการประเมิณหลักสูตร อาจอยู่ในทั้ง 8 และ 9 หรืออยู่แค่อย่างละที่ ถ้าอยู่ในหมวด 9 จะอยู่แค่เฉพาะในส่วน ผลการด าเนินงานของหลักสูตร/ผลการประกันคุณภาพการศึกษา ฉันอยากได้แค่ชื่อเกณฑ์และเอาแค่ชื่อย่อ เช่น AACSB, EQUIS, AMBA, AUN-QA, EdPEx, IQA,มาตรฐานของกระทรวงฯ, สกอ., สปอว. (ถ้ามีหลายอันใส่มาแค่ใช้ ,) แต่ที่เป็นพวก มคอ. ไม่เอา
"""

schema_chunk4 = {
    "type": "OBJECT",
    "properties": {
        "count_research": {"type": "INTEGER", "nullable": True},
        "count_academic_paper": {"type": "INTEGER", "nullable": True},
        "count_lecturer_academic": {"type": "INTEGER", "nullable": True},
        "count_lecturer_full": {"type": "INTEGER", "nullable": True},
        "count_lecturer_extra": {"type": "INTEGER", "nullable": True},
        "count_staff": {"type": "INTEGER", "nullable": True},
        "qualification_responsible": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "qualification_responsible": {
                        "type": "STRING",
                        "nullable": True,
                    },
                    "name_responsible": {
                        "type": "STRING",
                        "nullable": True,
                    },
                    "degree_reponsible": {
                        "type": "STRING",
                        "nullable": True,
                    },
                    "program_responsible": {
                        "type": "STRING",
                        "nullable": True,
                    },
                    "institute_responsible": {
                        "type": "STRING",
                        "nullable": True,
                    },
                    "year_graduate_responsible": {
                        "type": "INTEGER",
                        "nullable": True,
                    },
                },
                "required": [],
            },
        },
        "other_grade": {"type": "STRING", "nullable": True},
        "criteria_graduate": {"type": "STRING", "nullable": True},
        "curr_qa": {"type": "STRING", "nullable": True},
    },
    "required": [],
}

CONTENT_CHUNKS: dict[int, str] = {
    1: content_chunk1,
    2: content_chunk2,
    3: content_chunk3,
    4: content_chunk4,
}

SCHEMA_CHUNKS: dict[int, dict[str, Any]] = {
    1: schema_chunk1,
    2: schema_chunk2,
    3: schema_chunk3,
    4: schema_chunk4,
}


# ================= MAIN LOOP =================

def main():
    # 1) อ่านแถวจากชีท test
    rows = read_rows_from_sheet()
    print("rows", rows)

    # 2) header ของชีทปลายทาง (ทุกชีทคอลัมน์แรกอยู่ที่ B2)
    info_headers = get_sheet_headers("information")
    plo_headers = get_sheet_headers("plo")
    course_headers = get_sheet_headers("course")
    qual_headers = get_sheet_headers("qualification_responsible")

    # 3) loop ทีละแถว (1 แถว = 1 หลักสูตร)
    for row_idx, row in enumerate(rows, start=3):  # row_idx = แถวจริงในชีท (header อยู่ที่แถว 2)
        print("row_idx", row_idx)

        # ---------- (1) เลือกเฉพาะแถวที่ already_extract == 0 ----------
        already = str(row.get("already_extract", "")).strip()
        if already != "0":
            # ถ้าไม่ใช่ 0 แปลว่าเคย extract แล้ว -> ข้าม
            continue

        pdf_id = row.get("pdf id") or row.get("PDF_ID") or ""
        if not pdf_id:
            # ไม่มี pdf id ก็ข้าม
            continue

        PAGE_START_CHUNKS: Dict[int, Optional[int]] = {
            1: to_int_or_none(row.get("chunk1_start")),
            2: to_int_or_none(row.get("chunk2_start")),
            3: to_int_or_none(row.get("chunk3_start")),
            4: to_int_or_none(row.get("chunk4_start")),
        }
        PAGE_END_CHUNKS: Dict[int, Optional[int]] = {
            1: to_int_or_none(row.get("chunk1_end")),
            2: to_int_or_none(row.get("chunk2_end")),
            3: to_int_or_none(row.get("chunk3_end")),
            4: to_int_or_none(row.get("chunk4_end")),
        }

        print(f"\n========== ROW {row_idx} pdf_id={pdf_id} ==========\n")

        # ---------- scalar fields chunk1,2,4 -> information ----------
        info_data: Dict[str, Any] = {}

        # (2) map field จาก template -> sheet information ตามที่ต้องการ
        info_data["curriculum"] = row.get("curriculum", "")
        info_data["docx id"] = row.get("docx id", "")
        info_data["pdf id"] = pdf_id
        info_data["faculty"] = row.get("faculty", "")

        # 🔹 base_row สำหรับ sheet อื่น ๆ ที่ "ไม่เอา docx id / pdf id"
        base_row_no_ids = {
            k: v
            for k, v in row.items()
            if k.strip().lower().replace("_", " ") not in {"docx id", "pdf id"}
        }

        # buffer สำหรับแต่ละชนิดในแถวนี้
        plo_values_for_row: List[List[Any]] = []
        qual_values_for_row: List[List[Any]] = []
        chunk2_courses: List[Dict[str, Any]] = []
        chunk3_courses: List[Dict[str, Any]] = []

        # 4) รัน chunk 1–4
        for chunk_no in range(1, 5):
            prompt = CONTENT_CHUNKS[chunk_no]
            schema = SCHEMA_CHUNKS[chunk_no]
            start = PAGE_START_CHUNKS[chunk_no]
            end = PAGE_END_CHUNKS[chunk_no]

            pdf_bytes = download_pdf_pages(pdf_id, start, end)

            result = call_gemini_with_file_and_schema(
                file_bytes=pdf_bytes,
                prompt=prompt,
                schema=schema,
            )

            print(f"--- chunk {chunk_no} result ---")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print()

            if chunk_no == 1:
                # scalar -> info_data
                for k, v in result.items():
                    if k == "plo":
                        continue
                    info_data[k] = v

                # plo -> sheet 'plo'
                plo_list = result.get("plo") or []
                if isinstance(plo_list, list):
                    for plo_item in plo_list:
                        if not isinstance(plo_item, dict):
                            continue
                        row_values = make_row_from_item(
                            headers=plo_headers,
                            base_row=base_row_no_ids,  # ✅ เปลี่ยนมาใช้ base_row_no_ids
                            item=plo_item,
                            extra={"row_index": row_idx, "row_idx": row_idx},
                        )
                        plo_values_for_row.append(row_values)

            elif chunk_no == 2:
                # scalar (ยกเว้น course) -> info_data
                for k, v in result.items():
                    if k == "course":
                        continue
                    info_data[k] = v

                # course list จาก chunk2
                c_list = result.get("course") or []
                if isinstance(c_list, list):
                    for c in c_list:
                        if isinstance(c, dict):
                            # ✅ normalize th_abv / eng_abv ก่อนเก็บ
                            normalize_course_item_abv(c)
                            chunk2_courses.append(c)

            elif chunk_no == 3:
                # course descriptions จาก chunk3
                c_list = result.get("course") or []
                if isinstance(c_list, list):
                    for c in c_list:
                        if isinstance(c, dict):
                            # ✅ normalize th_abv / eng_abv ก่อนเก็บ
                            normalize_course_item_abv(c)
                            chunk3_courses.append(c)

            elif chunk_no == 4:
                # scalar (ยกเว้น qualification_responsible) -> info_data
                for k, v in result.items():
                    if k == "qualification_responsible":
                        continue
                    info_data[k] = v

                # qualification_responsible -> sheet 'qualification_responsible'
                q_list = result.get("qualification_responsible") or []
                if isinstance(q_list, list):
                    for q in q_list:
                        if not isinstance(q, dict):
                            continue
                        row_values = make_row_from_item(
                            headers=qual_headers,
                            base_row=base_row_no_ids,  # ✅ ใช้ base_row_no_ids
                            item=q,
                            extra={"row_index": row_idx, "row_idx": row_idx},
                        )
                        qual_values_for_row.append(row_values)

        # ===== หลังจากครบ 4 chunk ของแถวนี้ =====
        print(info_data)
        info_data.setdefault("finish_info", 0)
        info_data.setdefault("finish_course", 0)
        
        # information: เขียนแถว row_idx (ครั้งแรกเท่านั้น เพราะรอบต่อไปโดนกรอง already_extract)
        write_information_row(row_idx, info_headers, info_data)

        # plo (append เฉพาะของแถวนี้)
        if plo_values_for_row:
            append_rows_to_sheet("plo", plo_headers, plo_values_for_row)

        # course: รวม chunk2 + chunk3 ของแถวนี้ แล้ว append
        if chunk2_courses or chunk3_courses:
            combined_courses = combine_course_items_for_row(
                struct_courses=chunk2_courses,
                desc_courses=chunk3_courses,
            )

            course_values_for_row: List[List[Any]] = []
            for item in combined_courses:
                row_values = make_row_from_item(
                    headers=course_headers,
                    base_row=base_row_no_ids,  # ✅ ใช้ base_row_no_ids
                    item=item,
                    extra={"row_index": row_idx, "row_idx": row_idx},
                )

                course_values_for_row.append(row_values)

            if course_values_for_row:
                append_rows_to_sheet("course", course_headers, course_values_for_row)

        # qualification_responsible
        if qual_values_for_row:
            append_rows_to_sheet(
                "qualification_responsible",
                qual_headers,
                qual_values_for_row,
            )

        # ---------- (3) mark ว่าแถวนี้ extract เสร็จแล้ว ----------
        update_already_extract_flag(row_idx, 1)



if __name__ == "__main__":
    main()
