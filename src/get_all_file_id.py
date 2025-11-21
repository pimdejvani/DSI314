
from __future__ import annotations
from googleapiclient.discovery import build
from google.oauth2 import service_account
import pandas as pd

# ====== CONFIG ======
SERVICE_ACCOUNT_FILE = "service_account.json"  # แก้เป็น path ของไฟล์ key คุณ
SCOPES = ["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets",]

ROOT_FOLDER_ID = "1S8yB19KxNAKOCUDcvvX-rztBD9OOXnkH"
TARGET_NON_FACULTIES = ["คณะทันตแพทยศาสตร์", "สถาบันภาษา"]

SPREADSHEET_ID = "1w5hiNTEL4tt7-kl4QZInwj_Zgx2PSeB2bKYpKulnHuI"
SHEET_NAME = "template"

# ====== SETUP DRIVE CLIENT ======
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service_drive = build("drive", "v3", credentials=creds)
service_spread = build("sheets", "v4", credentials=creds).spreadsheets()

def list_items(query: str, fields: str = "nextPageToken, files(id, name, mimeType)"):
    """helper: list ไฟล์/โฟลเดอร์ตาม query (จัดการเรื่อง page token ให้)"""
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

    print(f"✅ เจอโฟลเดอร์ทั้งหมด {len(folders)} อันภายใต้ ROOT_FOLDER_ID")
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
    """เลือก pdf 1 ไฟล์ และ doc/docx 1 ไฟล์จาก list ไฟล์"""
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





def write_df_to_sheet(df):


    sheet = service_spread

    values = []
    for _, row in df.iterrows():
        values.append([
            row.get("faculty", ""),     # B
            row.get("degree", ""),      # C
            row.get("curriculum", ""),  # D
            row.get("docx_id", ""),     # E
            row.get("pdf_id", ""),      # F
            0, 0, 0, 0, 0, 0, 0, 0, 0,  # G–O หมวด 1–9
            0,                          # P DONE
        ])

    body = {"values": values}

    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!B2:P2",  # บอกว่าเริ่มเขียนตั้งแต่คอลัมน์ B ถึง P
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def main():
    rows = []

    faculty_folders = get_faculty_folders()

    for fac in faculty_folders:
        faculty_id = fac["id"]
        faculty_name = fac["name"]

        degree_folders = get_degree_folders(faculty_id)

        for degree_folder in degree_folders:
            degree_id = degree_folder["id"]
            # จาก requirement: degree = "ตรี" เสมอ
            degree_label = "ตรี"

            curriculum_folders = get_curriculum_folders(degree_id)

            for cur in curriculum_folders:
                cur_id = cur["id"]
                cur_name = cur["name"]

                files = get_files_in_folder(cur_id)
                pdf_id, docx_id = pick_pdf_and_doc(files)

                # ถ้าอยากเช็คว่ามีไม่ครบจะได้รู้
                if pdf_id is None or docx_id is None:
                    print(
                        f"⚠️ โฟลเดอร์สาขา '{cur_name}' (คณะ {faculty_name}) "
                        f"ไม่เจอ pdf หรือ docx ครบคู่: pdf={pdf_id}, docx={docx_id}"
                    )

                rows.append(
                    {
                        "faculty": faculty_name,
                        "degree": degree_label,
                        "curriculum": cur_name,
                        "pdf_id": pdf_id,
                        "docx_id": docx_id,
                    }
                )

    df = pd.DataFrame(rows)
    print(df)
    df.to_csv("curriculum_files.csv", index=False, encoding="utf-8-sig")
    print("✅ บันทึกเป็น curriculum_files.csv แล้ว")
    write_df_to_sheet(df)
    faculties = sorted(df["faculty"].dropna().unique())
    print(faculties)


if __name__ == "__main__":
    main()
