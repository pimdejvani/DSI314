from __future__ import annotations

from io import BytesIO
from typing import List, Optional, Dict, Tuple
import os
import re

from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
import pandas as pd

# ====== CONFIG ======
SERVICE_ACCOUNT_FILE = "service_account.json"
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

ROOT_FOLDER_ID = os.getenv("ROOT_FOLDER_ID")
NON_TARGET_FACULTIES = ["คณะเภสัชศาสตร์", "คณะทันตแพทยศาสตร์"]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = "template"
DOC_FLAG_TXT_PATH = "doc_files_faculty_curriculum.txt"

print("=== START SCRIPT ===")
print(f"ROOT_FOLDER_ID   = {ROOT_FOLDER_ID}")
print(f"SPREADSHEET_ID   = {SPREADSHEET_ID}")
print(f"SHEET_NAME       = {SHEET_NAME}")

if not ROOT_FOLDER_ID:
    raise RuntimeError("❌ ROOT_FOLDER_ID ยังไม่ถูกตั้งค่าใน environment variable")

if not SPREADSHEET_ID:
    print("⚠️  SPREADSHEET_ID ยังไม่ถูกตั้งค่า (ตอนเขียน sheet จะ error ได้)")

# ====== SETUP CLIENT ======
print("สร้าง service account credentials...")
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
print("สร้าง Drive / Sheets client...")
service_drive = build("drive", "v3", credentials=creds)
service_spread = build("sheets", "v4", credentials=creds).spreadsheets()

print("=== SETUP เสร็จสิ้น ===\n")

# ====== DRIVE HELPERS ======

def list_items(query: str, fields: str = "nextPageToken, files(id, name, mimeType)"):
    """List ไฟล์/โฟลเดอร์ตาม query (จัดการ page token ให้)"""
    print("\n[list_items] เรียกใช้...")
    print(f"  query = {query}")
    print(f"  fields = {fields}")

    items = []
    page_token = None
    while True:
        try:
            resp = (
                service_drive.files()
                .list(q=query, fields=fields, pageToken=page_token)
                .execute()
            )
        except HttpError as e:
            print("🚨 Drive API HttpError ใน list_items()")
            print(f"  status  = {getattr(e.resp, 'status', 'N/A')}")
            print(f"  reason  = {e}")
            try:
                print(f"  content = {e.content}")
            except Exception:
                pass
            # โยนต่อให้โปรแกรมล้ม จะได้เห็น error เต็ม ๆ
            raise

        batch = resp.get("files", [])
        print(f"  ได้ไฟล์มา {len(batch)} รายการ (page_token={page_token})")
        items.extend(batch)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    print(f"[list_items] รวมทั้งหมด {len(items)} รายการ\n")
    return items

def append_doc_metadata(faculty: str, curriculum: str):
    """
    เขียนข้อมูลแถวที่ไฟล์ word เป็น .doc ลงไฟล์ .txt
    รูปแบบ:

    #faculty__#curriculum

    (เว้นบรรทัดเปล่า 1 บรรทัด)
    """
    header = f"#{faculty}__#{curriculum}\n\n"
    with open(DOC_FLAG_TXT_PATH, "a", encoding="utf-8") as f:
        f.write(header)

    print(
        f"        [append_doc_metadata] เขียน '#{faculty}__#{curriculum}' "
        f"ลง {DOC_FLAG_TXT_PATH} แล้ว"
    )


def get_faculty_folders():
    """ดึงทุกโฟลเดอร์ (คณะ) ภายใต้ ROOT_FOLDER_ID"""
    print("=== ดึงโฟลเดอร์คณะ (faculty) ===")
    q = (
        f"'{ROOT_FOLDER_ID}' in parents and "
        f"trashed = false and "
        f"mimeType = 'application/vnd.google-apps.folder'"
    )
    folders = list_items(q)  # ใช้ fields default เพื่อกันพลาด
    print(f"  ก่อนกรอง NON_TARGET_FACULTIES มี {len(folders)} โฟลเดอร์")
    folders = [f for f in folders if f["name"] not in NON_TARGET_FACULTIES]
    print(f"  หลังกรอง NON_TARGET_FACULTIES เหลือ {len(folders)} โฟลเดอร์")
    for f in folders:
        print(f"    - {f['name']} ({f['id']})")
    print("=== จบ get_faculty_folders ===\n")
    return folders


def get_degree_folders(faculty_id: str):
    """ภายใต้โฟลเดอร์คณะ หาโฟลเดอร์ชื่อมีคำว่า 'ตรี'"""
    print(f"  [get_degree_folders] faculty_id={faculty_id}")
    q = (
        f"'{faculty_id}' in parents and "
        f"trashed = false and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"name contains 'ตรี'"
    )
    folders = list_items(q, fields="nextPageToken, files(id, name, mimeType)")
    print(f"  [get_degree_folders] ได้ {len(folders)} โฟลเดอร์ (ที่ชื่อมี 'ตรี')\n")
    return folders


def get_curriculum_folders(degree_id: str):
    """ภายใต้โฟลเดอร์ degree (ที่มีคำว่าตรี) เอาโฟลเดอร์ลูกทั้งหมด (ชื่อสาขา)"""
    print(f"    [get_curriculum_folders] degree_id={degree_id}")
    q = (
        f"'{degree_id}' in parents and "
        f"trashed = false and "
        f"mimeType = 'application/vnd.google-apps.folder'"
    )
    folders = list_items(q, fields="nextPageToken, files(id, name, mimeType)")
    print(f"    [get_curriculum_folders] ได้ {len(folders)} โฟลเดอร์สาขา\n")
    return folders

def pick_pdf_and_doc(files):
    """
    เลือก pdf 1 ไฟล์ และ doc/docx 1 ไฟล์จาก list ไฟล์
    คืนค่า (pdf_id, doc_id, doc_is_doc)

    - pdf_id: id ของไฟล์ pdf หรือ None
    - doc_id: id ของไฟล์ word (.doc หรือ .docx) หรือ None
    - doc_is_doc: True  ถ้าไฟล์ word ที่เลือกเป็น .doc (application/msword)
                  False ถ้าเป็น .docx หรือไม่มีไฟล์ word
    """
    pdf_id = None
    doc_id = None
    doc_is_doc = False  # default = ไม่ใช่ .doc

    for f in files:
        mime = f.get("mimeType")
        fid = f.get("id")
        name = f.get("name")
        print(f"        ตรวจไฟล์: name={name}, mime={mime}, id={fid}")

        # pdf
        if mime == "application/pdf":
            if pdf_id is None:
                pdf_id = fid
                print(f"        👉 เลือกเป็น PDF: {name} ({fid})")

        # .doc (application/msword)
        elif mime == "application/msword":
            # ให้ .doc มี priority สูงกว่า .docx (ถ้ามันโผล่มาทั้งคู่)
            if doc_id is None:
                doc_id = fid
                doc_is_doc = True
                print(f"        👉 เลือกเป็น DOC (.doc): {name} ({fid})")

        # .docx
        elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            # เลือกเฉพาะกรณีที่ยังไม่มี doc_id
            if doc_id is None:
                doc_id = fid
                doc_is_doc = False
                print(f"        👉 เลือกเป็น DOCX (.docx): {name} ({fid})")

    print(
        f"      [pick_pdf_and_doc] สรุป pdf_id={pdf_id}, "
        f"doc_id={doc_id}, doc_is_doc={doc_is_doc}\n"
    )
    return pdf_id, doc_id, doc_is_doc



def get_files_in_folder(folder_id: str):
    """ดึงไฟล์ทั้งหมดในโฟลเดอร์ (ทั้ง pdf และ word)"""
    print(f"      [get_files_in_folder] folder_id={folder_id}")
    q = f"'{folder_id}' in parents and trashed = false"
    files = list_items(q)  # ใช้ default fields รวม mimeType ด้วย
    print(f"      [get_files_in_folder] พบไฟล์ {len(files)} ไฟล์ในโฟลเดอร์นี้\n")
    return files



import socket  # เพิ่มด้านบนไฟล์

def download_file_bytes(file_id: str, max_retries: int = 3) -> bytes | None:
    """โหลดไฟล์จาก Google Drive เป็น bytes (retry ถ้า timeout)
    ถ้าลองครบ max_retries แล้วยัง timeout → คืนค่า None
    """
    print(f"        [download_file_bytes] ดาวน์โหลดไฟล์จาก Drive: {file_id}")
    request = service_drive.files().get_media(fileId=file_id)
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    attempt = 0

    while not done:
        try:
            # num_retries ภายใน googleapiclient เอง (เช่น retry 2 รอบสำหรับ 5xx)
            status, done = downloader.next_chunk(num_retries=2)
            # ถ้าอยากดู progress:
            # if status:
            #     print(f"          progress: {status.progress() * 100:.1f}%")
        except (TimeoutError, socket.timeout) as e:
            attempt += 1
            print(f"          ⚠️ Timeout ตอนโหลดไฟล์ {file_id} (attempt {attempt}/{max_retries}): {e}")
            if attempt >= max_retries:
                print(f"          ❌ ยกเลิกการดาวน์โหลดไฟล์ {file_id} หลัง timeout หลายครั้ง")
                return None  # บอกให้ caller รู้ว่าโหลดไม่สำเร็จ
            # ถ้ายังไม่ครบ max_retries → loop ต่อเพื่อ retry
        except Exception as e:
            print(f"          🚨 error อย่างอื่นตอนดาวน์โหลดไฟล์ {file_id}: {e}")
            return None

    print("        [download_file_bytes] ดาวน์โหลดเสร็จแล้ว\n")
    return fh.getvalue()



# ====== PDF & CHUNK HELPERS ======

def pdf_bytes_to_pages(pdf_bytes: bytes) -> List[str]:
    """แปลง PDF (bytes) เป็น list ข้อความทีละหน้า"""
    from pypdf import PdfReader  # ต้องติดตั้ง pypdf ก่อนใช้งาน

    reader = PdfReader(BytesIO(pdf_bytes))
    pages: List[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(text)
    print(f"        [pdf_bytes_to_pages] รวม {len(pages)} หน้า\n")
    return pages


THAI_RANGE = r"\u0E00-\u0E7F"

def normalize_thai(text: str) -> str:
    """normalize เบื้องต้น เช่น คํา -> คำ"""
    if text is None:
        return ""
    return text.replace("คํา", "คำ")


def sanitize_thai_digits(text: str) -> str:
    """
    เอาเฉพาะตัวอักษรไทย + ตัวเลขอารบิก (0-9)
    ลบตัวอื่น (อังกฤษ, สัญลักษณ์, เว้นวรรค ฯลฯ) ทิ้งออกไป
    """
    if text is None:
        return ""
    text = normalize_thai(text)
    filtered = re.sub(fr"[^{THAI_RANGE}0-9]", "", text)
    return filtered


def find_page_contains_keyword_thai(
    pages: list[str],
    keyword: str,
    *,
    min_page: int = 1,
    after_page: int = -1,
) -> int | None:
    """
    หา index หน้า (0-based) ที่มี keyword (หลังจาก sanitize ให้เหลือแต่ไทย+เลข)
    - min_page: หน้า (1-based) ขั้นต่ำที่ยอมให้เป็นคำตอบ
    - after_page: ข้ามทุกหน้าที่ index <= ค่านี้ (0-based)
    """
    key_norm = sanitize_thai_digits(keyword)
    print(f"        [find_page_contains_keyword_thai] keyword='{keyword}' -> '{key_norm}'")

    for idx, raw in enumerate(pages):
        page_no = idx + 1
        if page_no < min_page:
            continue
        if idx <= after_page:
            continue

        page_norm = sanitize_thai_digits(raw or "")

        if key_norm and key_norm in page_norm:
            print(f"          → เจอ '{key_norm}' ที่หน้า {page_no} (index {idx})")
            return idx

    print("          → ไม่เจอ keyword นี้\n")
    return None


def compute_chunk_page_ranges(pages: List[str]) -> Dict[str, Tuple[Optional[int], Optional[int]]]:
    print("      [compute_chunk_page_ranges] เริ่มคำนวณ chunk page ranges")
    n = len(pages)
    print(f"        จำนวนหน้าทั้งหมด = {n}")
    if n == 0:
        return {
            "chunk1": (None, None),
            "chunk2": (None, None),
            "chunk3": (None, None),
            "chunk4": (None, None),
        }

    # ===== markers =====
    idx_m4 = find_page_contains_keyword_thai(
        pages,
        "หมวดที่ 4",
        min_page=5,
        after_page=-1,
    )

    idx_desc_for_c2 = None
    if idx_m4 is not None:
        idx_desc_for_c2 = find_page_contains_keyword_thai(
            pages,
            "แผนการศึกษา",
            min_page=5,
            after_page=idx_m4,
        )

    idx_desc = find_page_contains_keyword_thai(
        pages,
        "อธิบายรายวิชา",
        min_page=5,
        after_page=-1,
    )

    idx_m5 = None
    if idx_desc is not None:
        idx_m5 = find_page_contains_keyword_thai(
            pages,
            "หมวดที่ 5",
            min_page=5,
            after_page=idx_desc,
        )

    idx_m6 = find_page_contains_keyword_thai(
        pages,
        "หมวดที่ 6",
        min_page=5,
        after_page=-1,
    )

    idx_appendix = None
    if idx_m6 is not None:
        idx_appendix = find_page_contains_keyword_thai(
            pages,
            "ภาคผนวก",
            min_page=1,
            after_page=idx_m6,
        )

    print("        markers summary:")
    print(f"          idx_m4        = {idx_m4}")
    print(f"          idx_desc_c2   = {idx_desc_for_c2}")
    print(f"          idx_desc      = {idx_desc}")
    print(f"          idx_m5        = {idx_m5}")
    print(f"          idx_m6        = {idx_m6}")
    print(f"          idx_appendix  = {idx_appendix}")

    # chunk1
    if idx_m4 is not None:
        chunk1_start = 1
        chunk1_end = idx_m4 + 1
    else:
        chunk1_start = 1
        chunk1_end = n

    # chunk2
    if (
        idx_m4 is not None
        and idx_desc_for_c2 is not None
        and idx_desc_for_c2 >= idx_m4
    ):
        chunk2_start = idx_m4 + 1
        chunk2_end = idx_desc_for_c2 + 1
    else:
        chunk2_start = None
        chunk2_end = None

    # chunk3
    if (
        idx_desc is not None
        and idx_m5 is not None
        and idx_m5 >= idx_desc
    ):
        chunk3_start = idx_desc + 1
        chunk3_end = idx_m5 + 1
    else:
        chunk3_start = None
        chunk3_end = None

    # chunk4
    if idx_m6 is not None:
        chunk4_start = idx_m6 + 1
        if idx_appendix is not None and idx_appendix >= idx_m6:
            chunk4_end = idx_appendix + 1
        else:
            chunk4_end = n
    else:
        chunk4_start = None
        chunk4_end = None

    result = {
        "chunk1": (chunk1_start, chunk1_end),
        "chunk2": (chunk2_start, chunk2_end),
        "chunk3": (chunk3_start, chunk3_end),
        "chunk4": (chunk4_start, chunk4_end),
    }
    print(f"      [compute_chunk_page_ranges] ผลลัพธ์ = {result}\n")
    return result


# ====== SHEETS WRITER ======

def write_df_to_sheet(df: pd.DataFrame):
    """เขียนข้อมูลลง Google Sheet (เริ่ม B2, ตามคอลัมน์ที่กำหนด)"""

    print("\n=== เขียน DataFrame ลง Google Sheet ===")
    print(f"  จำนวนแถวใน df = {len(df)}")
    if df.empty:
        print("  df ว่าง ไม่เขียนอะไรลงชีต\n")
        return

    if not SPREADSHEET_ID:
        print("❌ ไม่มี SPREADSHEET_ID – ข้ามการเขียนชีต\n")
        return

    sheet = service_spread

    def _v(val):
        if pd.isna(val) or val is None:
            return ""
        return val

    def _num(val):
        if pd.isna(val) or val is None:
            return 0
        return val

    values = []
    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        print(f"  เตรียมแถว {idx}: faculty={row.get('faculty')}, curriculum={row.get('curriculum')}")
        values.append(
            [
                _v(row.get("faculty", "")),         # B
                _v(row.get("degree", "")),          # C
                _v(row.get("curriculum", "")),      # D
                _v(row.get("docx_id", "")),         # E
                _v(row.get("pdf_id", "")),          # F

                _num(row.get("chunk1_start")),      # G
                _num(row.get("chunk1_end")),        # H
                _num(row.get("chunk2_start")),      # I
                _num(row.get("chunk2_end")),        # J
                _num(row.get("chunk3_start")),      # K
                _num(row.get("chunk3_end")),        # L
                _num(row.get("chunk4_start")),      # M
                _num(row.get("chunk4_end")),        # N

                0,                                  # O  already_extract
                0,                                  # R  DONE
            ]
        )

    body = {"values": values}
    print("  ส่ง values ไป append ลงชีต...")
    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!B2",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()
    print("=== เขียนชีตเสร็จสิ้น ===\n")


# ====== MAIN FLOW ======

def main():
    print("=== เริ่ม main() ===")
    rows: List[Dict[str, object]] = []

    faculty_folders = get_faculty_folders()
    print(f"\n>>> พบคณะทั้งหมด {len(faculty_folders)} โฟลเดอร์ <<<\n")

    faculty_count = 0
    curriculum_count = 0

    for fac in faculty_folders:
        faculty_count += 1
        faculty_id = fac["id"]
        faculty_name = fac["name"]
        print(f"\n===== คณะ {faculty_count}: {faculty_name} ({faculty_id}) =====")

        degree_folders = get_degree_folders(faculty_id)
        print(f"  → degree_folders (ตรี) = {len(degree_folders)} โฟลเดอร์")

        for degree_folder in degree_folders:
            degree_id = degree_folder["id"]
            degree_label = "ตรี"
            degree_name = degree_folder.get("name")
            print(f"\n  --- degree: {degree_name} ({degree_id}) ---")

            curriculum_folders = get_curriculum_folders(degree_id)
            print(f"    → curriculum_folders = {len(curriculum_folders)} โฟลเดอร์สาขา")

            for cur in curriculum_folders:
                curriculum_count += 1
                cur_id = cur["id"]
                cur_name = cur["name"]
                print(f"\n    *** [{curriculum_count}] curriculum: {cur_name} ({cur_id}) ***")

                files = get_files_in_folder(cur_id)
                pdf_id, docx_id, doc_is_doc = pick_pdf_and_doc(files)

                # ===== NEW: ถ้าไฟล์ word ที่เลือกเป็น .doc ให้จด faculty/curriculum ลงไฟล์ .txt =====
                if docx_id is not None and doc_is_doc:
                    print(f"    🔤 curriculum นี้ใช้ไฟล์ .doc: faculty={faculty_name}, curriculum={cur_name}")
                    append_doc_metadata(faculty_name, cur_name)
                else:
                    if docx_id is not None:
                        print("    ℹ️ ไฟล์ word เป็น .docx → ไม่ต้องเขียนลง .txt")
                    else:
                        print("    ℹ️ curriculum นี้ไม่มีไฟล์ word")

                chunk1_start = chunk1_end = None
                chunk2_start = chunk2_end = None
                chunk3_start = chunk3_end = None
                chunk4_start = chunk4_end = None

                if pdf_id is not None:
                    pdf_bytes = download_file_bytes(pdf_id)
                    if pdf_bytes is None:
                        print(f"    ⚠️ โหลด PDF ไม่สำเร็จสำหรับ curriculum: {cur_name} (pdf_id={pdf_id}) -> ข้ามการคำนวณ chunk")
                    else:
                        try:
                            pages = pdf_bytes_to_pages(pdf_bytes)
                            ranges = compute_chunk_page_ranges(pages)

                            c1 = ranges["chunk1"]
                            c2 = ranges["chunk2"]
                            c3 = ranges["chunk3"]
                            c4 = ranges["chunk4"]

                            chunk1_start, chunk1_end = c1
                            chunk2_start, chunk2_end = c2
                            chunk3_start, chunk3_end = c3
                            chunk4_start, chunk4_end = c4
                        except Exception as e:
                            print(f"    🚨 ERROR ขณะประมวลผล PDF ({pdf_id}) ของ curriculum {cur_name}: {e}")
                else:
                    print(f"    ℹ️ curriculum นี้ไม่มี pdf_id")

                print(f"    → สรุป row นี้: pdf_id={pdf_id}, docx_id={docx_id}, "
                      f"c1={chunk1_start}-{chunk1_end}, "
                      f"c2={chunk2_start}-{chunk2_end}, "
                      f"c3={chunk3_start}-{chunk3_end}, "
                      f"c4={chunk4_start}-{chunk4_end}")

                rows.append(
                    {
                        "faculty": faculty_name,
                        "degree": degree_label,
                        "curriculum": cur_name,
                        "docx_id": docx_id,
                        "pdf_id": pdf_id,
                        "chunk1_start": chunk1_start,
                        "chunk1_end": chunk1_end,
                        "chunk2_start": chunk2_start,
                        "chunk2_end": chunk2_end,
                        "chunk3_start": chunk3_start,
                        "chunk3_end": chunk3_end,
                        "chunk4_start": chunk4_start,
                        "chunk4_end": chunk4_end,
                    }
                )

    print("\n=== main() จบการวนลูปแล้ว ===")
    print(f"  รวม faculty    = {faculty_count}")
    print(f"  รวม curriculum = {curriculum_count}")
    print(f"  รวม rows       = {len(rows)}")

    df = pd.DataFrame(rows)
    print("ตัวอย่าง df.head():")
    print(df.head())

    df = df.to_csv("curriculum_files.csv", index=False, encoding="utf-8-sig")
    print("✅ บันทึกไฟล์ curriculum_files.csv แล้ว")

    write_df_to_sheet(df)
    print("✅ เสร็จสิ้นทุกขั้นตอนใน main()\n")


if __name__ == "__main__":
    main()
