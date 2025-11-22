from __future__ import annotations

from io import BytesIO
from typing import List, Optional, Dict, Tuple
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
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

# ====== SETUP CLIENT ======
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service_drive = build("drive", "v3", credentials=creds)
service_spread = build("sheets", "v4", credentials=creds).spreadsheets()


# ====== DRIVE HELPERS ======

def list_items(query: str, fields: str = "nextPageToken, files(id, name, mimeType)"):
    """List ไฟล์/โฟลเดอร์ตาม query (จัดการ page token ให้)"""
    items = []
    page_token = None
    while True:
        resp = (
            service_drive.files()
            .list(q=query, fields=fields, pageToken=page_token)
            .execute()
        )
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def get_faculty_folders():
    """ดึงทุกโฟลเดอร์ (คณะ) ภายใต้ ROOT_FOLDER_ID"""
    q = (
        f"'{ROOT_FOLDER_ID}' in parents and "
        f"trashed = false and "
        f"mimeType = 'application/vnd.google-apps.folder'"
    )
    folders = list_items(q, fields="files(id, name)")
    folders = [f for f in folders if f["name"] not in NON_TARGET_FACULTIES]
    return folders


def get_degree_folders(faculty_id: str):
    """ภายใต้โฟลเดอร์คณะ หาโฟลเดอร์ชื่อมีคำว่า 'ตรี'"""
    q = (
        f"'{faculty_id}' in parents and "
        f"trashed = false and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"name contains 'ตรี'"
    )
    return list_items(q, fields="files(id, name)")


def get_curriculum_folders(degree_id: str):
    """ภายใต้โฟลเดอร์ degree (ที่มีคำว่าตรี) เอาโฟลเดอร์ลูกทั้งหมด (ชื่อสาขา)"""
    q = (
        f"'{degree_id}' in parents and "
        f"trashed = false and "
        f"mimeType = 'application/vnd.google-apps.folder'"
    )
    return list_items(q, fields="files(id, name)")


def get_files_in_folder(folder_id: str):
    """ดึงไฟล์ทั้งหมดในโฟลเดอร์ (ทั้ง pdf และ word)"""
    q = f"'{folder_id}' in parents and trashed = false"
    return list_items(q)


def pick_pdf_and_doc(files):
    """
    เลือก pdf 1 ไฟล์ และ doc/docx 1 ไฟล์จาก list ไฟล์
    (แม้เราจะใช้ pdf เพื่อหา chunk อย่างเดียว แต่ยังเก็บ docx_id ไว้ในตารางเหมือนเดิม)
    """
    pdf_id = None
    doc_id = None

    for f in files:
        mime = f.get("mimeType")
        fid = f.get("id")
        # pdf
        if mime == "application/pdf":
            if pdf_id is None:
                pdf_id = fid
        # doc หรือ docx
        elif mime in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ):
            if doc_id is None:
                doc_id = fid

    return pdf_id, doc_id


def download_file_bytes(file_id: str) -> bytes:
    """โหลดไฟล์จาก Google Drive เป็น bytes"""
    request = service_drive.files().get_media(fileId=file_id)
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue()


# ====== PDF & CHUNK HELPERS ======

def pdf_bytes_to_pages(pdf_bytes: bytes) -> List[str]:
    """แปลง PDF (bytes) เป็น list ข้อความทีละหน้า"""
    from pypdf import PdfReader  # ต้องติดตั้ง pypdf ก่อนใช้งาน

    reader = PdfReader(BytesIO(pdf_bytes))
    pages: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return pages


def normalize_thai(text: str) -> str:
    """Normalize เคสบางอย่างของภาษาไทย เช่น คํา -> คำ"""
    if text is None:
        return ""
    return text.replace("คํา", "คำ")


# def find_page_startswith(
#     pages: List[str],
#     keyword: str,
#     *,
#     min_page: int = 1,
#     after_page: int = -1,
# ) -> Optional[int]:
#     """
#     หา index หน้า (0-based) ที่ 'ขึ้นต้นหน้า' ด้วย keyword
#     - min_page: หน้า (1-based) ขั้นต่ำที่ยอมให้เป็นคำตอบ (เช่น 5 = หน้า 1–4 ไม่เอา)
#     - after_page: ข้ามหน้าที่ index <= ค่านี้ (0-based) เช่น after_page=4 -> ข้ามหน้า 0–4
#     คืนค่า index 0-based หรือ None ถ้าไม่เจอ
#     """
#     keyword_norm = normalize_thai(keyword)

#     for idx, raw in enumerate(pages):
#         page_no = idx + 1
#         if page_no < min_page:
#             continue
#         if idx <= after_page:
#             continue

#         text = normalize_thai(raw or "").lstrip()
#         if text.startswith(keyword_norm):
#             return idx

#     return None

import re

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
    # เก็บเฉพาะ [ก-ฮ สระ/วรรณยุกต์ในบล็อกไทย] + [0-9]
    # ไม่เก็บ space / เครื่องหมายวรรคตอน / ตัวอื่น
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

    for idx, raw in enumerate(pages):
        page_no = idx + 1
        if page_no < min_page:
            continue
        if idx <= after_page:
            continue

        page_norm = sanitize_thai_digits(raw or "")

        if key_norm and key_norm in page_norm:
            return idx

    return None



def compute_chunk_page_ranges(pages: List[str]) -> Dict[str, Tuple[Optional[int], Optional[int]]]:
    n = len(pages)
    if n == 0:
        return {
            "chunk1": (None, None),
            "chunk2": (None, None),
            "chunk3": (None, None),
            "chunk4": (None, None),
        }

    # ===== markers: ใช้ฟังก์ชันใหม่ =====

    # หมวดที่ 4 (หน้า >= 5)
    idx_m4 = find_page_contains_keyword_thai(
        pages,
        "หมวดที่ 4",
        min_page=5,
        after_page=-1,
    )

    # 'อธิบายรายวิชา' สำหรับ chunk2 (หลังหมวดที่ 4, หน้า >= 5)
    idx_desc_for_c2 = None
    if idx_m4 is not None:
        idx_desc_for_c2 = find_page_contains_keyword_thai(
            pages,
            "แผนการศึกษา",
            min_page=5,
            after_page=idx_m4,
        )

    # 'อธิบายรายวิชา' สำหรับ chunk3 (ไม่ผูกกับ m4, แต่หน้า >= 5)
    idx_desc = find_page_contains_keyword_thai(
        pages,
        "อธิบายรายวิชา",
        min_page=5,
        after_page=-1,
    )

    # 'หมวดที่ 5' สำหรับ chunk3
    idx_m5 = None
    if idx_desc is not None:
        idx_m5 = find_page_contains_keyword_thai(
            pages,
            "หมวดที่ 5",
            min_page=5,
            after_page=idx_desc,
        )

    # 'หมวดที่ 6' สำหรับ chunk4
    idx_m6 = find_page_contains_keyword_thai(
        pages,
        "หมวดที่ 6",
        min_page=5,
        after_page=-1,
    )

    # 'ภาคผนวก' สำหรับ chunk4
    idx_appendix = None
    if idx_m6 is not None:
        idx_appendix = find_page_contains_keyword_thai(
            pages,
            "ภาคผนวก",
            min_page=1,
            after_page=idx_m6,
        )

    # ===== ใช้ marker พวกนี้คำนวณ chunk1–4 เหมือนเดิม =====

    # chunk1: หน้า 1 → หน้า 'หมวดที่ 4' (ถ้ามี) ไม่งั้นไปถึงหน้าสุดท้าย
    if idx_m4 is not None:
        chunk1_start = 1
        chunk1_end = idx_m4 + 1
    else:
        chunk1_start = 1
        chunk1_end = n

    # chunk2: จากหน้า 'หมวดที่ 4' → หน้า 'อธิบายรายวิชา' (เวอร์ชัน c2)
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

    # chunk3: หน้า 'อธิบายรายวิชา' → หน้า 'หมวดที่ 5'
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

    # chunk4: หน้า 'หมวดที่ 6' → หน้า 'ภาคผนวก' หรือหน้าสุดท้าย
    if idx_m6 is not None:
        chunk4_start = idx_m6 + 1
        if idx_appendix is not None and idx_appendix >= idx_m6:
            chunk4_end = idx_appendix + 1
        else:
            chunk4_end = n
    else:
        chunk4_start = None
        chunk4_end = None

    return {
        "chunk1": (chunk1_start, chunk1_end),
        "chunk2": (chunk2_start, chunk2_end),
        "chunk3": (chunk3_start, chunk3_end),
        "chunk4": (chunk4_start, chunk4_end),
    }



# ====== SHEETS WRITER ======

def write_df_to_sheet(df: pd.DataFrame):
    """เขียนข้อมูลลง Google Sheet (เริ่ม B2, append เป็นแถว ๆ)"""

    if df.empty:
        return

    sheet = service_spread

    def _v(val):
        return "" if pd.isna(val) else val

    values = []
    for _, row in df.iterrows():
        values.append(
            [
                _v(row.get("faculty", "")),        # B
                _v(row.get("degree", "")),         # C
                _v(row.get("curriculum", "")),     # D
                _v(row.get("docx_id", "")),        # E
                _v(row.get("pdf_id", "")),         # F
                0, 0, 0, 0, 0, 0, 0, 0, 0,         # G–O หมวด 1–9
                0,                                 # P DONE
                _v(row.get("chunk1_start", "")),   # Q
                _v(row.get("chunk1_end", "")),     # R
                _v(row.get("chunk2_start", "")),   # S
                _v(row.get("chunk2_end", "")),     # T
                _v(row.get("chunk3_start", "")),   # U
                _v(row.get("chunk3_end", "")),     # V
                _v(row.get("chunk4_start", "")),   # W
                _v(row.get("chunk4_end", "")),     # X
            ]
        )

    body = {"values": values}

    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!B2",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


# ====== MAIN FLOW ======

def main():
    rows: List[Dict[str, object]] = []

    faculty_folders = get_faculty_folders()

    for fac in faculty_folders:
        faculty_id = fac["id"]
        faculty_name = fac["name"]

        degree_folders = get_degree_folders(faculty_id)

        for degree_folder in degree_folders:
            degree_id = degree_folder["id"]
            degree_label = "ตรี"

            curriculum_folders = get_curriculum_folders(degree_id)

            for cur in curriculum_folders:
                cur_id = cur["id"]
                cur_name = cur["name"]

                files = get_files_in_folder(cur_id)
                pdf_id, docx_id = pick_pdf_and_doc(files)

                # เตรียมค่าเริ่มต้นของ chunk pages
                chunk1_start = chunk1_end = None
                chunk2_start = chunk2_end = None
                chunk3_start = chunk3_end = None
                chunk4_start = chunk4_end = None

                # ถ้ามี pdf_id ให้ลองโหลดและคำนวณ page ranges
                if pdf_id is not None:
                    pdf_bytes = download_file_bytes(pdf_id)
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

                rows.append(
                    {
                        "faculty": faculty_name,
                        "degree": degree_label,
                        "curriculum": cur_name,
                        "pdf_id": pdf_id,
                        "docx_id": docx_id,
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

    df = pd.DataFrame(rows)
    df.to_csv("curriculum_files.csv", index=False, encoding="utf-8-sig")
    write_df_to_sheet(df)


if __name__ == "__main__":
    main()
