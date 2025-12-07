import os
import io

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

# ================== CONFIG & GOOGLE CLIENTS ==================

st.set_page_config(page_title="Curriculum QA Tool", layout="wide")

st.markdown(
    """
    <style>
    /* ปรับขอบหน้าเว็บ */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 3rem;
        padding-right: 3rem;
        max-width: 100%;
    }

    /* จำกัดความสูง popup ของ selectbox ทุกตัวให้ไม่เกิน ~5 แถว แล้วมี scrollbar */
    /* เมนูของ Streamlit ใช้ data-baseweb="menu" และบางทีมี role="listbox" ด้วย */
    div[data-baseweb="menu"],
    ul[role="listbox"],
    div[role="listbox"] {
        max-height: 100px !important;
        overflow-y: auto !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

SERVICE_ACCOUNT_FILE = "service_account.json"
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = "information"
PLO_SHEET_NAME = "plo"
QUAL_SHEET_NAME = "qualification_responsible"
COURSE_SHEET_NAME = "course"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash"

# ความสูงของ PDF และกรอบฟอร์ม
PDF_HEIGHT = 800

# สร้าง credentials และ client
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service_spread = build("sheets", "v4", credentials=creds).spreadsheets()
service_drive = build("drive", "v3", credentials=creds)

# ================== PDF VIEWER (GOOGLE DRIVE PREVIEW) ==================
def drive_preview_iframe(pdf_id: str, height: int) -> str:
    pdf_id = (pdf_id or "").strip()
    if not pdf_id:
        return "<p style='color:red;'>ไม่มี pdf id</p>"

    url = f"https://drive.google.com/file/d/{pdf_id}/preview"

    return f"""
    <iframe
        src="{url}"
        width="100%"
        height="{height}"
        allow="autoplay"
        style="border: 1px solid #ddd; border-radius: 4px;"
    ></iframe>
    """

def editable_field(
    label: str,
    value: str,
    key_prefix: str,
    is_text_area: bool = False,
    height: int | None = None,
    default_update: bool = False,
):
    """
    แสดง label + checkbox 'แก้ไข' อยู่บรรทัดเดียวกัน
    แล้วค่อยตามด้วย input / textarea อีกบรรทัด

    return: (new_value, want_update)
    """
    with st.container():
        # แถวบน: ชื่อฟิลด์ + checkbox แก้ไข
        hcol, ccol = st.columns([5, 1])

        with hcol:
            st.markdown(f"**{label}**")

        with ccol:
            want_update = st.checkbox(
                "แก้ไข",
                key=f"{key_prefix}_edit",
                value=default_update,
                help="ติ๊กถ้าต้องการให้เขียนทับฟิลด์นี้กลับไปที่ Google Sheet",
            )

        # แถวล่าง: กล่องกรอกค่า
        if is_text_area:
            new_val = st.text_area(
                label=label,                     # 👈 มี label จริง
                value=value,
                key=f"{key_prefix}_val",
                height=height,
                label_visibility="collapsed",    # 👈 ซ่อนออกจาก UI
            )
        else:
            new_val = st.text_input(
                label=label,                     # 👈 มี label จริง
                value=value,
                key=f"{key_prefix}_val",
                label_visibility="collapsed",    # 👈 ซ่อนออกจาก UI
            )

    return new_val, want_update



# ================== DATA LAYER: READ SHEET ==================

def load_curriculum_data() -> pd.DataFrame:
    if not SPREADSHEET_ID:
        st.error("ไม่ได้ตั้งค่า SPREADSHEET_ID ใน environment variable")
        return pd.DataFrame()

    range_name = f"{SHEET_NAME}!B2:ZZ"

    result = service_spread.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name,
    ).execute()

    values = result.get("values", [])
    if not values:
        return pd.DataFrame()

    header = values[0]
    data_rows = values[1:]

    normalized_rows = []
    n_cols = len(header)

    for row in data_rows:
        if len(row) < n_cols:
            row = row + [""] * (n_cols - len(row))
        elif len(row) > n_cols:
            row = row[:n_cols]
        normalized_rows.append(row)

    df = pd.DataFrame(normalized_rows, columns=header)
    return df


def load_plo_data() -> pd.DataFrame:
    if not SPREADSHEET_ID:
        return pd.DataFrame()

    range_name = f"{PLO_SHEET_NAME}!B2:ZZ"
    result = service_spread.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name,
    ).execute()

    values = result.get("values", [])
    if not values:
        return pd.DataFrame()

    header = values[0]
    data_rows = values[1:]

    n_cols = len(header)
    normalized_rows = []
    for row in data_rows:
        if len(row) < n_cols:
            row = row + [""] * (n_cols - len(row))
        elif len(row) > n_cols:
            row = row[:n_cols]
        normalized_rows.append(row)

    df = pd.DataFrame(normalized_rows, columns=header)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_qualification_data() -> pd.DataFrame:
    if not SPREADSHEET_ID:
        return pd.DataFrame()

    range_name = f"{QUAL_SHEET_NAME}!B2:ZZ"
    result = service_spread.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name,
    ).execute()

    values = result.get("values", [])
    if not values:
        return pd.DataFrame()

    header = values[0]
    data_rows = values[1:]

    n_cols = len(header)
    normalized_rows = []
    for row in data_rows:
        if len(row) < n_cols:
            row = row + [""] * (n_cols - len(row))
        elif len(row) > n_cols:
            row = row[:n_cols]
        normalized_rows.append(row)

    df = pd.DataFrame(normalized_rows, columns=header)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_course_data() -> pd.DataFrame:
    if not SPREADSHEET_ID:
        return pd.DataFrame()

    range_name = f"{COURSE_SHEET_NAME}!B2:ZZ"
    result = service_spread.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name,
    ).execute()

    values = result.get("values", [])
    if not values:
        return pd.DataFrame()

    header = values[0]
    data_rows = values[1:]

    n_cols = len(header)
    normalized_rows = []
    for row in data_rows:
        if len(row) < n_cols:
            row = row + [""] * (n_cols - len(row))
        elif len(row) > n_cols:
            row = row[:n_cols]
        normalized_rows.append(row)

    df = pd.DataFrame(normalized_rows, columns=header)
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ================== DATA LAYER: DOWNLOAD PDF FROM DRIVE ==================

@st.cache_data(show_spinner=True)
def download_pdf_bytes(file_id: str) -> bytes:
    request = service_drive.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return fh.getvalue()



# cache sheetId ไว้ใน session_state เพื่อลดการเรียก API ซ้ำ
def get_sheet_id(sheet_name: str) -> int:
    if "sheet_id_cache" not in st.session_state:
        st.session_state["sheet_id_cache"] = {}

    cache = st.session_state["sheet_id_cache"]
    if sheet_name in cache:
        return cache[sheet_name]

    # service_spread = build(...).spreadsheets() แล้ว
    meta = service_spread.get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == sheet_name:
            sheet_id = props["sheetId"]
            cache[sheet_name] = sheet_id
            return sheet_id

    raise RuntimeError(f"ไม่พบ sheet ชื่อ {sheet_name}")


def insert_rows(sheet_name: str, start_row_1_based: int, n_rows: int):
    """
    แทรกแถวว่าง n_rows แถวที่ตำแหน่ง start_row_1_based (1-based, ทั้งแถว A:ZZ)
    """
    if n_rows <= 0:
        return

    sheet_id = get_sheet_id(sheet_name)

    requests = [
        {
            "insertDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": start_row_1_based - 1,                 # 0-based
                    "endIndex": start_row_1_based - 1 + n_rows,
                },
                "inheritFromBefore": True,
            }
        }
    ]

    service_spread.batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": requests},
    ).execute()

def save_plo_changes(curriculum_key: str, edited_plo: list[dict]):
    """
    เขียนข้อมูล PLO กลับไปที่ชีต 'plo'

    - แก้ไขเฉพาะฟิลด์ที่มี *_update = True
    - แถวใหม่ (is_new=True) จะถูกแทรกต่อท้ายกลุ่มของ curriculum นี้
    - ถ้า delete=True → ลบทั้งแถวออกจากชีต (deleteDimension)
    """
    if not curriculum_key:
        st.warning("ไม่มี curriculum_key สำหรับ save PLO")
        return

    # โหลด sheet สด
    df = load_plo_data()
    if df.empty or "curriculum" not in df.columns:
        st.error("โหลดชีต 'plo' ไม่ได้ หรือไม่มีคอลัมน์ curriculum")
        return

    cur_series = df["curriculum"].astype(str).str.strip()
    cur_key = str(curriculum_key).strip()
    mask = cur_series == cur_key

    idx_list = [i for i, ok in enumerate(mask) if ok]

    if idx_list:
        first_idx = idx_list[0]
        last_idx = idx_list[-1]
    else:
        first_idx = None
        last_idx = None

    header = list(df.columns)

    # ---------- 1) UPDATE + เก็บ index ที่ต้องลบ ----------
    value_updates = []
    delete_indices: list[int] = []

    for item in edited_plo:
        if item.get("is_new"):
            # แถวใหม่ ยังไม่มีในชีต → ไปจัดการตอน INSERT
            continue

        row_pos = item.get("row_pos")
        if row_pos is None or first_idx is None:
            continue

        df_index = first_idx + int(row_pos)
        if df_index < 0 or df_index >= len(df):
            continue

        if str(df.iloc[df_index]["curriculum"]).strip() != cur_key:
            # curriculum ไม่ตรง → ข้าม (กันเคส concurrency)
            continue

        if item.get("delete"):
            # mark ไว้ว่าจะแถวนี้ทั้งแถวออก
            delete_indices.append(df_index)
            continue

        # กรณีแก้ไขธรรมดา
        row = df.iloc[df_index].copy()

        if item.get("type_plo_update"):
            row["type_plo"] = item.get("type_plo", "")

        if item.get("num_plo_update"):
            row["num_plo"] = item.get("num_plo", "")

        if item.get("detail_plo_update"):
            row["detail_plo"] = item.get("detail_plo", "")

        sheet_row = df_index + 3  # df index 0 → row 3

        row_values = [str(row.get(col, "")) for col in header]

        value_updates.append(
            {
                "range": f"{PLO_SHEET_NAME}!B{sheet_row}",
                "values": [row_values],
            }
        )

    # commit updates แถวเดิม (ยกเว้นแถวที่จะลบ)
    if value_updates:
        body = {
            "valueInputOption": "USER_ENTERED",
            "data": value_updates,
        }
        service_spread.values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body=body,
        ).execute()

    # ลบแถวที่ถูก mark delete
    if delete_indices:
        delete_rows(PLO_SHEET_NAME, delete_indices)

    # ---------- 2) INSERT แถวใหม่ ----------
    new_rows = [
        item for item in edited_plo
        if item.get("is_new") and not item.get("delete")
    ]

    if not new_rows:
        return

    # โหลด df ใหม่หลังจากลบแถวเสร็จแล้ว
    df2 = load_plo_data()
    if df2.empty or "curriculum" not in df2.columns:
        # ไม่มีอะไรเหลือแล้วในชีต แต่อยากเพิ่มแถวใหม่ → แทรกใต้ header ได้เลย
        cur_series2 = pd.Series([], dtype=str)
        idx_list2 = []
    else:
        cur_series2 = df2["curriculum"].astype(str).str.strip()
        mask2 = cur_series2 == cur_key
        idx_list2 = [i for i, ok in enumerate(mask2) if ok]

    if idx_list2:
        last_idx2 = idx_list2[-1]
    else:
        # ไม่มี curriculum นี้แล้ว → แทรกท้ายข้อมูลทั้งหมด
        last_idx2 = len(df2) - 1

    start_row_1_based = last_idx2 + 4  # df index 0 → row3 → ถัดไป row4 = 0+4

    insert_rows(PLO_SHEET_NAME, start_row_1_based, len(new_rows))

    # เติมค่าลงแถวใหม่
    header2 = list(df2.columns) if not df2.empty else header

    data_for_new = []
    current_row = start_row_1_based

    for item in new_rows:
        row_dict = {col: "" for col in header2}
        row_dict["curriculum"] = cur_key
        row_dict["type_plo"] = item.get("type_plo", "")
        row_dict["num_plo"] = item.get("num_plo", "")
        row_dict["detail_plo"] = item.get("detail_plo", "")

        row_values = [str(row_dict.get(col, "")) for col in header2]

        data_for_new.append(
            {
                "range": f"{PLO_SHEET_NAME}!B{current_row}",
                "values": [row_values],
            }
        )
        current_row += 1

    body_new = {
        "valueInputOption": "USER_ENTERED",
        "data": data_for_new,
    }

    service_spread.values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body=body_new,
    ).execute()

def save_qualification_changes(curriculum_key: str, edited_qual: list[dict]):
    """
    เขียนข้อมูลกลับไปที่ชีต 'qualification_responsible' (QUAL_SHEET_NAME)

    - แก้ไขเฉพาะฟิลด์ที่มี *_update = True
    - แถวใหม่ (is_new=True) จะถูกแทรกต่อท้ายกลุ่มของ curriculum นี้
    - ถ้า delete=True → ลบแถวออกจากชีตจริง
    """
    if not curriculum_key:
        st.warning("ไม่มี curriculum_key สำหรับ save qualification")
        return

    df = load_qualification_data()
    if df.empty or "curriculum" not in df.columns:
        st.error("โหลดชีต 'qualification_responsible' ไม่ได้ หรือไม่มีคอลัมน์ curriculum")
        return

    cur_key = str(curriculum_key).strip()
    cur_series = df["curriculum"].astype(str).str.strip()
    mask = cur_series == cur_key

    idx_list = [i for i, ok in enumerate(mask) if ok]

    if idx_list:
        first_idx = idx_list[0]
        last_idx = idx_list[-1]
    else:
        first_idx = None
        last_idx = None

    header = list(df.columns)

    value_updates = []
    delete_indices: list[int] = []

    # ---------- 1) UPDATE + เก็บ index สำหรับลบ ----------
    for item in edited_qual:
        if item.get("is_new"):
            continue

        row_pos = item.get("row_pos")
        if row_pos is None or first_idx is None:
            continue

        df_index = first_idx + int(row_pos)
        if df_index < 0 or df_index >= len(df):
            continue

        if str(df.iloc[df_index]["curriculum"]).strip() != cur_key:
            continue

        if item.get("delete"):
            delete_indices.append(df_index)
            continue

        row = df.iloc[df_index].copy()

        if item.get("qualification_responsible_update"):
            row["qualification_responsible"] = item.get("qualification_responsible", "")

        if item.get("name_responsible_update"):
            row["name_responsible"] = item.get("name_responsible", "")

        if item.get("degree_reponsible_update"):
            row["degree_reponsible"] = item.get("degree_reponsible", "")

        if item.get("program_responsible_update"):
            row["program_responsible"] = item.get("program_responsible", "")

        if item.get("institute_responsible_update"):
            row["institute_responsible"] = item.get("institute_responsible", "")

        if item.get("year_graduate_responsible_update"):
            row["year_graduate_responsible"] = item.get("year_graduate_responsible", "")

        sheet_row = df_index + 3  # df index 0 → row3

        row_values = [str(row.get(col, "")) for col in header]

        value_updates.append(
            {
                "range": f"{QUAL_SHEET_NAME}!B{sheet_row}",
                "values": [row_values],
            }
        )

    if value_updates:
        body = {
            "valueInputOption": "USER_ENTERED",
            "data": value_updates,
        }
        service_spread.values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body=body,
        ).execute()

    if delete_indices:
        delete_rows(QUAL_SHEET_NAME, delete_indices)

    # ---------- 2) INSERT แถวใหม่ ----------
    new_rows = [
        item for item in edited_qual
        if item.get("is_new") and not item.get("delete")
    ]

    if not new_rows:
        return

    df2 = load_qualification_data()
    if df2.empty or "curriculum" not in df2.columns:
        cur_series2 = pd.Series([], dtype=str)
        idx_list2 = []
    else:
        cur_series2 = df2["curriculum"].astype(str).str.strip()
        mask2 = cur_series2 == cur_key
        idx_list2 = [i for i, ok in enumerate(mask2) if ok]

    if idx_list2:
        last_idx2 = idx_list2[-1]
    else:
        last_idx2 = len(df2) - 1

    start_row_1_based = last_idx2 + 4
    insert_rows(QUAL_SHEET_NAME, start_row_1_based, len(new_rows))

    header2 = list(df2.columns) if not df2.empty else header

    data_for_new = []
    current_row = start_row_1_based

    for item in new_rows:
        row_dict = {col: "" for col in header2}
        row_dict["curriculum"] = cur_key
        row_dict["qualification_responsible"] = item.get("qualification_responsible", "")
        row_dict["name_responsible"] = item.get("name_responsible", "")
        row_dict["degree_reponsible"] = item.get("degree_reponsible", "")
        row_dict["program_responsible"] = item.get("program_responsible", "")
        row_dict["institute_responsible"] = item.get("institute_responsible", "")
        row_dict["year_graduate_responsible"] = item.get("year_graduate_responsible", "")

        row_values = [str(row_dict.get(col, "")) for col in header2]

        data_for_new.append(
            {
                "range": f"{QUAL_SHEET_NAME}!B{current_row}",
                "values": [row_values],
            }
        )
        current_row += 1

    body_new = {
        "valueInputOption": "USER_ENTERED",
        "data": data_for_new,
    }

    service_spread.values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body=body_new,
    ).execute()

def save_course_changes(curriculum_key: str, edited_course_list: list[dict]):
    """
    เขียนข้อมูลรายวิชากลับไปที่ชีต 'course' (COURSE_SHEET_NAME)

    - แก้ไขเฉพาะฟิลด์ที่มี *_update = True
    - แถวใหม่ (is_new=True) จะถูกแทรกต่อท้ายกลุ่มของ curriculum นี้
    - ถ้า delete=True → ลบแถวออกจากชีตจริง
    """
    if not curriculum_key:
        st.warning("ไม่มี curriculum_key สำหรับ save course")
        return

    df = load_course_data()
    if df.empty or "curriculum" not in df.columns:
        st.error("โหลดชีต 'course' ไม่ได้ หรือไม่มีคอลัมน์ curriculum")
        return

    cur_key = str(curriculum_key).strip()
    cur_series = df["curriculum"].astype(str).str.strip()
    mask = cur_series == cur_key

    idx_list = [i for i, ok in enumerate(mask) if ok]

    if idx_list:
        first_idx = idx_list[0]
        last_idx = idx_list[-1]
    else:
        first_idx = None
        last_idx = None

    header = list(df.columns)

    value_updates = []
    delete_indices: list[int] = []

    # ---------- 1) UPDATE แถวเดิม + เก็บ index สำหรับลบ ----------
    for item in edited_course_list:
        if item.get("is_new"):
            continue

        row_pos = item.get("row_pos")
        if row_pos is None or first_idx is None:
            continue

        df_index = first_idx + int(row_pos)
        if df_index < 0 or df_index >= len(df):
            continue

        if str(df.iloc[df_index]["curriculum"]).strip() != cur_key:
            continue

        if item.get("delete"):
            delete_indices.append(df_index)
            continue

        row = df.iloc[df_index].copy()

        if item.get("course_type_id_update"):
            row["course_type_id"] = item.get("course_type_id", "")

        fields = [
            "th_abv",
            "th_name",
            "eng_abv",
            "eng_name",
            "credit",
            "lect_hours",
            "practice_hours",
            "self_hours",
            "th_desc",
            "eng_desc",
            "prerequisite",
        ]

        for field in fields:
            flag_name = f"{field}_update"
            if item.get(flag_name):
                row[field] = item.get(field, "")

        sheet_row = df_index + 3  # df index 0 → row3

        row_values = [str(row.get(col, "")) for col in header]

        value_updates.append(
            {
                "range": f"{COURSE_SHEET_NAME}!B{sheet_row}",
                "values": [row_values],
            }
        )

    if value_updates:
        body = {
            "valueInputOption": "USER_ENTERED",
            "data": value_updates,
        }
        service_spread.values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body=body,
        ).execute()

    if delete_indices:
        delete_rows(COURSE_SHEET_NAME, delete_indices)

    # ---------- 2) INSERT แถวใหม่ ----------
    new_rows = [
        item for item in edited_course_list
        if item.get("is_new") and not item.get("delete")
    ]

    if not new_rows:
        return

    df2 = load_course_data()
    if df2.empty or "curriculum" not in df2.columns:
        cur_series2 = pd.Series([], dtype=str)
        idx_list2 = []
    else:
        cur_series2 = df2["curriculum"].astype(str).str.strip()
        mask2 = cur_series2 == cur_key
        idx_list2 = [i for i, ok in enumerate(mask2) if ok]

    if idx_list2:
        last_idx2 = idx_list2[-1]
    else:
        last_idx2 = len(df2) - 1

    start_row_1_based = last_idx2 + 4
    insert_rows(COURSE_SHEET_NAME, start_row_1_based, len(new_rows))

    header2 = list(df2.columns) if not df2.empty else header

    data_for_new = []
    current_row = start_row_1_based

    for item in new_rows:
        row_dict = {col: "" for col in header2}
        row_dict["curriculum"] = cur_key
        row_dict["course_type_id"] = item.get("course_type_id", "")

        fields = [
            "th_abv",
            "th_name",
            "eng_abv",
            "eng_name",
            "credit",
            "lect_hours",
            "practice_hours",
            "self_hours",
            "th_desc",
            "eng_desc",
            "prerequisite",
        ]

        for field in fields:
            row_dict[field] = item.get(field, "")

        row_values = [str(row_dict.get(col, "")) for col in header2]

        data_for_new.append(
            {
                "range": f"{COURSE_SHEET_NAME}!B{current_row}",
                "values": [row_values],
            }
        )
        current_row += 1

    body_new = {
        "valueInputOption": "USER_ENTERED",
        "data": data_for_new,
    }

    service_spread.values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body=body_new,
    ).execute()

def save_information_changes(
    curriculum_key: str,
    edited_info: dict | None = None,
    edited_course_info: dict | None = None,
    mark_finish_info: bool = False,
    mark_finish_course: bool = False,
):
    """
    อัปเดตแถวในชีต 'information' (SHEET_NAME) สำหรับ curriculum หนึ่งตัว

    - ใช้คีย์หลักคือคอลัมน์ 'curriculum'
    - ใช้ค่าใน edited_info / edited_course_info เฉพาะที่มี "update": True
    - ถ้า mark_finish_info=True → เซ็ต finish_info = 1
    - ถ้า mark_finish_course=True → เซ็ต finish_course = 1
    """
    if not curriculum_key:
        st.warning("ไม่มี curriculum_key สำหรับ save information")
        return

    df = load_curriculum_data()
    if df.empty:
        st.error("โหลดชีต 'information' ไม่ได้")
        return

    cur_key = str(curriculum_key).strip()

    # ใช้คอลัมน์ 'curriculum' เป็นตัวระบุตำแหน่งแถว
    if "curriculum" not in df.columns:
        st.error("ไม่พบคอลัมน์ 'curriculum' ในชีต information")
        return

    cur_series = df["curriculum"].astype(str).str.strip()
    mask = cur_series == cur_key
    idx_list = [i for i, ok in enumerate(mask) if ok]

    if not idx_list:
        st.error(f"ไม่พบแถวในชีต information สำหรับ curriculum = {curriculum_key}")
        return

    # ถ้ามีหลายแถว ใช้แถวแรกเป็นหลัก (ปกติควรมีแถวเดียว)
    df_index = idx_list[0]

    row = df.iloc[df_index].copy()

    # helper ฟังก์ชัน apply จาก dict {"col": {"value": .., "update": True/False}}
    def apply_updates(row_series, info_dict: dict | None):
        if not info_dict:
            return row_series
        for col, meta in info_dict.items():
            if not isinstance(meta, dict):
                continue
            if not meta.get("update"):
                continue
            # เฉพาะคอลัมน์ที่มีจริงใน df
            if col in row_series.index:
                row_series[col] = meta.get("value", "")
        return row_series

    # 1) อัปเดตฟิลด์จาก information mode
    row = apply_updates(row, edited_info)

    # 2) อัปเดตฟิลด์จาก course summary (max_semester / credits ฯลฯ)
    row = apply_updates(row, edited_course_info)

    # 3) เซ็ต finish flag ถ้าต้องการ
    if mark_finish_info and "finish_info" in row.index:
        row["finish_info"] = 1

    if mark_finish_course and "finish_course" in row.index:
        row["finish_course"] = 1

    header = list(df.columns)
    row_values = [str(row.get(col, "")) for col in header]

    # df index 0 → แถว B3 (เพราะ header อยู่ B2)
    sheet_row = df_index + 3

    body = {
        "valueInputOption": "USER_ENTERED",
        "data": [
            {
                "range": f"{SHEET_NAME}!B{sheet_row}",
                "values": [row_values],
            }
        ],
    }


    service_spread.values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body=body,
    ).execute()

def delete_rows(sheet_name: str, df_indices_to_delete: list[int]):
    """
    ลบทั้งแถว (ROWS) ใน sheet_name ตาม index ของ df (0-based ของ DataFrame)

    - df_index 0 → แถวข้อมูลจริงคือ row 3 (เพราะ B2 เป็น header)
    - Google Sheets ใช้ row index แบบ 0-based (row1 = 0)
      ดังนั้น row0_based = (df_index + 3) - 1 = df_index + 2
    """
    if not df_indices_to_delete:
        return

    sheet_id = get_sheet_id(sheet_name)

    # ต้องลบจากแถวล่างขึ้นบน เพื่อไม่ให้ index ขยับกระทบแถวที่ยังไม่ลบ
    requests = []
    for df_index in sorted(df_indices_to_delete, reverse=True):
        row_start_0_based = df_index + 2   # df_index 0 → row3 → 0-based = 2

        requests.append(
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row_start_0_based,
                        "endIndex": row_start_0_based + 1,
                    }
                }
            }
        )

    service_spread.batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": requests},
    ).execute()


# ================== STREAMLIT UI ==================

st.title("Curriculum QA")

df = load_curriculum_data()
plo_df = load_plo_data()
qual_df = load_qualification_data()
course_df = load_course_data()
if df.empty:
    st.error("ไม่พบข้อมูลในชีต 'information' หรือโหลดไม่สำเร็จ")
    st.stop()

# ===== ตรวจว่ามีคอลัมน์ที่ต้องใช้ครบไหม =====
required_cols = [
    "pdf id",
    "faculty",
    "degree_full_th",
    "finish_info",
    "finish_course",
]
missing = [c for c in required_cols if c not in df.columns]
if missing:
    st.error(f"ในชีต 'information' ขาดคอลัมน์: {missing}")
    st.stop()

# ===== เตรียม state สำหรับการค้นหา =====
if "has_searched" not in st.session_state:
    st.session_state.has_searched = False

if "filter_faculty" not in st.session_state:
    st.session_state.filter_faculty = None

if "filter_degree" not in st.session_state:
    st.session_state.filter_degree = None

# ================== X1: ตัวกรองสถานะการตรวจ ==================

STATUS_OPTIONS = ["ยังไม่ตรวจ", "เสร็จ"]
x1_status = st.radio(
    "สถานะการตรวจ (X1)",
    STATUS_OPTIONS,
    index=0,
    horizontal=True,
    key="x1_status",
)


finish_info_int = pd.to_numeric(df["finish_info"], errors="coerce").fillna(0).astype(int)
finish_course_int = pd.to_numeric(df["finish_course"], errors="coerce").fillna(0).astype(int)

if x1_status == "ยังไม่ตรวจ":
    mask = (finish_info_int == 0) | (finish_course_int == 0)
else:  # "เสร็จ"
    mask = (finish_info_int == 1) | (finish_course_int == 1)

df_search = df[mask].copy()

if df_search.empty:
    st.warning("ไม่มีหลักสูตรตามตัวกรองสถานะที่เลือก")
    st.stop()

# ================== SEARCH BAR ด้านบน ==================

faculty_series = df_search["faculty"].dropna().astype(str).str.strip()
faculty_list = sorted(
    [f for f in faculty_series.unique().tolist() if f != ""]
)

search_col1, search_col2, search_col3 = st.columns([2, 2, 1])

# ---------- เลือกคณะ ----------
with search_col1:
    st.markdown("**คณะ (faculty)**")

    FAC_BOX_HEIGHT = 150
    fac_box = st.container(height=FAC_BOX_HEIGHT, border=True)

    with fac_box:
        fac_options = ["-- ยังไม่เลือกคณะ --"] + faculty_list

        if (
            st.session_state.filter_faculty is not None
            and st.session_state.filter_faculty in faculty_list
        ):
            default_fac_index = faculty_list.index(st.session_state.filter_faculty) + 1
        else:
            default_fac_index = 0

        fac_choice = st.radio(
            label="คณะ",
            options=fac_options,
            index=default_fac_index,
            key="faculty_radio",
            label_visibility="collapsed",
        )

    fac_ui = None if fac_choice == "-- ยังไม่เลือกคณะ --" else fac_choice

# ---------- เลือกหลักสูตร ----------
with search_col2:
    st.markdown("**ชื่อหลักสูตร (degree_full_th)**")

    if fac_ui is not None:
        degree_series = (
            df_search.loc[df_search["faculty"] == fac_ui, "degree_full_th"]
            .dropna()
            .astype(str)
            .str.strip()
        )
        degree_list = sorted(
            [d for d in degree_series.unique().tolist() if d != ""]
        )

        if degree_list:
            DEG_BOX_HEIGHT = 150
            deg_box = st.container(height=DEG_BOX_HEIGHT, border=True)

            with deg_box:
                deg_options = ["-- ยังไม่เลือกหลักสูตร --"] + degree_list

                if (
                    st.session_state.filter_degree is not None
                    and st.session_state.filter_degree in degree_list
                    and st.session_state.filter_faculty == fac_ui
                ):
                    default_deg_index = degree_list.index(st.session_state.filter_degree) + 1
                else:
                    default_deg_index = 0

                deg_choice = st.radio(
                    label="degree_full_th",
                    options=deg_options,
                    index=default_deg_index,
                    key="degree_radio",
                    label_visibility="collapsed",
                )

            deg_ui = None if deg_choice == "-- ยังไม่เลือกหลักสูตร --" else deg_choice
        else:
            deg_ui = None
            st.info("คณะนี้ยังไม่มี degree_full_th ในชีต")
    else:
        deg_ui = None
        st.info("กรุณาเลือกคณะก่อน")

# ---------- ปุ่มค้นหา ----------
with search_col3:
    search_clicked = st.button("🔍 ค้นหา", use_container_width=True)

if search_clicked:
    if fac_ui is None:
        st.warning("กรุณาเลือกคณะ (faculty)")
    elif deg_ui is None:
        st.warning("กรุณาเลือกชื่อหลักสูตร (degree_full_th)")
    else:
        st.session_state.filter_faculty = fac_ui
        st.session_state.filter_degree = deg_ui
        st.session_state.has_searched = True

st.markdown("---")

# ========== ถ้ายังไม่กดค้นหา แสดงแค่ส่วน search แล้วจบ ==========

if not st.session_state.has_searched:
    st.info("กรุณาเลือก faculty และ degree_full_th แล้วกดปุ่ม 'ค้นหา'")
    st.stop()

# ========= จากตรงนี้ลงไป: render PDF + ฟอร์ม =========

active_fac = st.session_state.filter_faculty
active_deg = st.session_state.filter_degree

filtered = df_search[
    (df_search["faculty"] == active_fac)
    & (df_search["degree_full_th"] == active_deg)
]

if filtered.empty:
    st.warning("ไม่พบข้อมูลที่ตรงกับ faculty + degree_full_th ที่เลือก (ภายใต้ตัวกรอง X1)")
    st.stop()

row = filtered.iloc[0]
pdf_id = row.get("pdf id", "")
record_id = row.get("curr_id", f"{active_fac}_{active_deg}")
curriculum_key = row.get("curriculum", "")

st.markdown(f"**ผลการค้นหา pdf id:** `{pdf_id}`")
st.markdown("---")

# ===== X2: เลือกโหมดแก้ไขตามสถานะ finish =====
raw_finish_info = pd.to_numeric(row.get("finish_info", 0), errors="coerce")
finish_info_val = int(0 if pd.isna(raw_finish_info) else raw_finish_info)

raw_finish_course = pd.to_numeric(row.get("finish_course", 0), errors="coerce")
finish_course_val = int(0 if pd.isna(raw_finish_course) else raw_finish_course)

x2_options = []

if x1_status == "ยังไม่ตรวจ":
    # โหมดนี้ให้เลือกเฉพาะส่วนที่ยังไม่เสร็จ
    if finish_info_val == 0:
        x2_options.append("information")
    if finish_course_val == 0:
        x2_options.append("course")
else:  # x1_status == "เสร็จ"
    # โหมดนี้ให้เลือกเฉพาะส่วนที่ "เสร็จแล้ว" (ตามที่บอกว่า finish_info / finish_course = 1)
    if finish_info_val == 1:
        x2_options.append("information")
    if finish_course_val == 1:
        x2_options.append("course")

# กันเคสข้อมูลเพี้ยน แต่ปกติใน X1 = "เสร็จ" จะได้ทั้งสองอันอยู่แล้ว
if not x2_options:
    st.error("สถานะ finish ของหลักสูตรนี้ไม่ตรงกับตัวกรอง X1 ที่เลือก")
    st.stop()

x2_mode = st.radio(
    "เลือกส่วนที่ต้องการตรวจ/แก้ไข (X2)",
    x2_options,
    index=0,
    horizontal=True,
    key="x2_mode",
)

st.markdown("---")

# ================== LAYOUT 40:60 ==================

left_col, right_col = st.columns([4, 6])

# ------------------ ด้านซ้าย: PDF ------------------
with left_col:
    st.subheader("📄 PDF หลักสูตร")

    if pdf_id:
        try:
            pdf_bytes = download_pdf_bytes(pdf_id)
            pdf_viewer(
                input=pdf_bytes,
                width="100%",
                height=PDF_HEIGHT,
                render_text=True,
                key="pdf_viewer_main",
            )
        except Exception as e:
            st.error(f"โหลด PDF ไม่สำเร็จ: {e}")
    else:
        st.warning("ไม่มี pdf id")

TEXTAREA_HEIGHT = 100
BOX_HEIGHT = 800

with right_col:
    if x2_mode == "information":
        st.subheader("📝 ข้อมูลหลักสูตร (แก้ไขได้ในกล่องเลื่อน)")

        EXCLUDED_COLUMNS = {
            "curriculum",
            "docx id",
            "pdf id",
            "finish_info",
            "finish_course",
            "max_semester",
            "day_class",
            "type_class",
            "total_credits",
            "gen_ed_credits",
            "spec_credits",
            "elec_credits",
            "free_elec_credits",
        }

        FIELD_COLUMNS = [c for c in df.columns if c not in EXCLUDED_COLUMNS]

        LONG_TEXT_COLUMNS = {
            "mou",
            "careers",
            "qualification_collegian",
            "other_grade",
            "criteria_graduate",
        }

        # ---------- เตรียมตัวนับ PLO / Qualification ใหม่ ----------
        plo_count_key = f"new_plo_count_{record_id}"
        if plo_count_key not in st.session_state:
            st.session_state[plo_count_key] = 0
        new_plo_count = int(st.session_state[plo_count_key])

        qual_count_key = f"new_qual_count_{record_id}"
        if qual_count_key not in st.session_state:
            st.session_state[qual_count_key] = 0
        new_qual_count = int(st.session_state[qual_count_key])

        # 👉 callback สำหรับปุ่มเพิ่ม/ล้าง
        def inc_plo():
            st.session_state[plo_count_key] = int(st.session_state.get(plo_count_key, 0)) + 1

        def clear_plo():
            st.session_state[plo_count_key] = 0

        def inc_qual():
            st.session_state[qual_count_key] = int(st.session_state.get(qual_count_key, 0)) + 1

        def clear_qual():
            st.session_state[qual_count_key] = 0


        # ---------- ฟอร์มหลัก ----------
        form_key = f"qa_form_{record_id}_info"

        with st.form(form_key):
            scroll_box = st.container(height=BOX_HEIGHT, border=True)

            with scroll_box:
                edited_info = {}
                edited_plo = []
                edited_qual = []

                curriculum_key = row.get("curriculum", "")

                # ===== เตรียมข้อมูล PLO =====
                plo_rows = pd.DataFrame()
                if curriculum_key and not plo_df.empty and "curriculum" in plo_df.columns:
                    mask_plo = (
                        plo_df["curriculum"].astype(str).str.strip()
                        == str(curriculum_key).strip()
                    )
                    # index ใหม่ 0..N-1 สำหรับ curriculum นี้
                    plo_rows = plo_df[mask_plo].copy().reset_index(drop=True)


                qual_rows = pd.DataFrame()
                if curriculum_key and not qual_df.empty and "curriculum" in qual_df.columns:
                    mask_qual = (
                        qual_df["curriculum"].astype(str).str.strip()
                        == str(curriculum_key).strip()
                    )
                    # ให้ index เป็น 0..N-1 ภายใน curriculum นี้
                    qual_rows = qual_df[mask_qual].copy().reset_index(drop=True)


                plo_inserted = False
                qual_inserted = False

                # ==== ฟอร์มหลักจาก information ====
                for col_name in FIELD_COLUMNS:
                    if col_name not in df.columns:
                        continue

                    original_value = str(row.get(col_name, "") or "")

                    key_prefix = f"{record_id}_info_{col_name}"

                    if col_name in LONG_TEXT_COLUMNS:
                        new_value, want_update = editable_field(
                            label=col_name,
                            value=original_value,
                            key_prefix=key_prefix,
                            is_text_area=True,
                            height=TEXTAREA_HEIGHT,
                            default_update=False,  # 👈 ของเดิมใน DB -> ยังไม่แก้
                        )
                    else:
                        new_value, want_update = editable_field(
                            label=col_name,
                            value=original_value,
                            key_prefix=key_prefix,
                            is_text_area=False,
                            default_update=False,
                        )

                    # เก็บทั้ง value + flag ว่าจะแก้ไหม
                    edited_info[col_name] = {
                        "value": new_value,
                        "update": want_update,
                    }

                    st.markdown("---")

                    # ==== แทรก PLO หลัง qualification_collegian ====
                    if (not plo_inserted) and (col_name == "qualification_collegian"):
                        st.subheader("📌 Program Learning Outcomes (PLO)")

                        if not curriculum_key:
                            st.info("ยังไม่มีค่า curriculum ในชีต information")

                        elif plo_df.empty:
                            st.info("ยังไม่มีข้อมูลในชีต 'plo' หรือโหลดไม่สำเร็จ")

                        elif "curriculum" not in plo_df.columns:
                            st.info("ไม่พบคอลัมน์ 'curriculum' ในชีต 'plo'")
                            st.write("คอลัมน์ที่มีใน plo_df คือ:", list(plo_df.columns))

                        else:
                            # ===== PLO เดิม =====
                            if plo_rows.empty:
                                st.info("ยังไม่มีข้อมูล PLO สำหรับ curriculum นี้ในชีต 'plo'")
                            else:
                                st.markdown("#### ✅ PLO เดิม")
                                for i, plo_row in plo_rows.iterrows():
                                    with st.container(border=True):
                                        st.markdown(f"**PLO เดิม #{i+1}**")

                                        type_val, type_update = editable_field(
                                            label="type_plo",
                                            value=str(plo_row.get("type_plo", "")),
                                            key_prefix=f"{record_id}_plo_{i}_type",
                                            default_update=False,   # ของเดิม -> ยังไม่แก้
                                        )

                                        num_val, num_update = editable_field(
                                            label="num_plo",
                                            value=str(plo_row.get("num_plo", "")),
                                            key_prefix=f"{record_id}_plo_{i}_num",
                                            default_update=False,
                                        )

                                        detail_val, detail_update = editable_field(
                                            label="detail_plo",
                                            value=str(plo_row.get("detail_plo", "")),
                                            key_prefix=f"{record_id}_plo_{i}_detail",
                                            is_text_area=True,
                                            height=TEXTAREA_HEIGHT,
                                            default_update=False,
                                        )

                                        delete_flag = st.checkbox(
                                            "ลบ PLO นี้",
                                            key=f"{record_id}_plo_{i}_delete",
                                            value=False,
                                        )

                                        edited_plo.append(
                                            {
                                                # ตำแหน่งภายใน curriculum นี้ (0..N-1)
                                                "row_pos": i,
                                                "curriculum": curriculum_key,

                                                "type_plo": type_val,
                                                "num_plo": num_val,
                                                "detail_plo": detail_val,

                                                "type_plo_update": type_update,
                                                "num_plo_update": num_update,
                                                "detail_plo_update": detail_update,

                                                "is_new": False,
                                                "delete": delete_flag,
                                            }
                                        )

                                        st.markdown("---")

                            # ===== PLO ใหม่ =====
                            if new_plo_count > 0:
                                st.markdown("#### ➕ PLO ใหม่")

                            for j in range(new_plo_count):
                                with st.container(border=True):
                                    st.markdown(f"**PLO ใหม่ #{j+1}**")

                                    type_val, type_update = editable_field(
                                        label="type_plo (ใหม่)",
                                        value="",
                                        key_prefix=f"{record_id}_plo_new_{j}_type",
                                        default_update=True,  # 👈 กล่องใหม่ -> แก้ เป็น default
                                    )

                                    num_val, num_update = editable_field(
                                        label="num_plo (ใหม่)",
                                        value="",
                                        key_prefix=f"{record_id}_plo_new_{j}_num",
                                        default_update=True,
                                    )

                                    detail_val, detail_update = editable_field(
                                        label="detail_plo (ใหม่)",
                                        value="",
                                        key_prefix=f"{record_id}_plo_new_{j}_detail",
                                        is_text_area=True,
                                        height=TEXTAREA_HEIGHT,
                                        default_update=True,
                                    )

                                    edited_plo.append(
                                        {
                                            "row_pos": None,   # หรือจะลบ key นี้ทิ้งก็ได้
                                            "curriculum": curriculum_key,

                                            "type_plo": type_val,
                                            "num_plo": num_val,
                                            "detail_plo": detail_val,

                                            "type_plo_update": type_update,
                                            "num_plo_update": num_update,
                                            "detail_plo_update": detail_update,

                                            "is_new": True,
                                            "delete": False,
                                        }
                                    )

                                    st.markdown("---")

                        plo_inserted = True

                    # ==== แทรก Qualification หลัง count_staff ====
                    if (not qual_inserted) and (col_name == "count_staff"):
                        st.subheader("👩‍🏫 Qualification / ผู้รับผิดชอบหลักสูตร")

                        if not curriculum_key:
                            st.info("ยังไม่มีค่า curriculum ในชีต information")

                        elif qual_df.empty:
                            st.info("ยังไม่มีข้อมูลในชีต 'qualification_responsible' หรือโหลดไม่สำเร็จ")

                        elif "curriculum" not in qual_df.columns:
                            st.info("ไม่พบคอลัมน์ 'curriculum' ในชีต 'qualification_responsible'")
                            st.write("คอลัมน์ที่มีใน qual_df คือ:", list(qual_df.columns))

                        else:
                            # ===== ผู้รับผิดชอบเดิม =====
                            if qual_rows.empty:
                                st.info("ยังไม่มีข้อมูล qualification_responsible สำหรับ curriculum นี้")
                            else:
                                st.markdown("#### ✅ ผู้รับผิดชอบเดิม")

                                for i, q_row in qual_rows.iterrows():
                                    with st.container(border=True):
                                        st.markdown(f"**ผู้รับผิดชอบเดิม #{i+1}**")

                                        qual_val, qual_update = editable_field(
                                            "qualification_responsible",
                                            value=str(q_row.get("qualification_responsible", "")),
                                            key_prefix=f"{record_id}_qual_{i}_qualification",
                                            default_update=False,
                                        )

                                        name_val, name_update = editable_field(
                                            "name_responsible",
                                            value=str(q_row.get("name_responsible", "")),
                                            key_prefix=f"{record_id}_qual_{i}_name",
                                            default_update=False,
                                        )

                                        degree_val, degree_update = editable_field(
                                            "degree_reponsible",   # 👈 ให้ตรงชื่อคอลัมน์ในชีต
                                            value=str(q_row.get("degree_reponsible", "")),
                                            key_prefix=f"{record_id}_qual_{i}_degree",
                                            default_update=False,
                                        )

                                        program_val, program_update = editable_field(
                                            "program_responsible",
                                            value=str(q_row.get("program_responsible", "")),
                                            key_prefix=f"{record_id}_qual_{i}_program",
                                            default_update=False,
                                        )

                                        inst_val, inst_update = editable_field(
                                            "institute_responsible",   # 👈 ใช้ชื่อคอลัมน์จริง
                                            value=str(q_row.get("institute_responsible", "")),
                                            key_prefix=f"{record_id}_qual_{i}_institute",
                                            default_update=False,
                                        )

                                        year_val, year_update = editable_field(
                                            "year_graduate_responsible",  # 👈 ใช้ชื่อคอลัมน์จริง
                                            value=str(q_row.get("year_graduate_responsible", "")),
                                            key_prefix=f"{record_id}_qual_{i}_year",
                                            default_update=False,
                                        )

                                        delete_flag = st.checkbox(
                                            "ลบผู้รับผิดชอบนี้",
                                            key=f"{record_id}_qual_{i}_delete",
                                            value=False,
                                        )

                                        edited_qual.append(
                                            {
                                                "row_pos": i,   # 👈 ตำแหน่งใน curriculum นี้
                                                "curriculum": curriculum_key,

                                                "qualification_responsible": qual_val,
                                                "name_responsible": name_val,
                                                "degree_reponsible": degree_val,
                                                "program_responsible": program_val,
                                                "institute_responsible": inst_val,
                                                "year_graduate_responsible": year_val,

                                                "qualification_responsible_update": qual_update,
                                                "name_responsible_update": name_update,
                                                "degree_reponsible_update": degree_update,
                                                "program_responsible_update": program_update,
                                                "institute_responsible_update": inst_update,
                                                "year_graduate_responsible_update": year_update,

                                                "is_new": False,
                                                "delete": delete_flag,
                                            }
                                        )


                            # ===== ผู้รับผิดชอบใหม่ =====
                            if new_qual_count > 0:
                                st.markdown("#### ➕ ผู้รับผิดชอบใหม่")

                            for j in range(new_qual_count):
                                with st.container(border=True):
                                    st.markdown(f"**ผู้รับผิดชอบใหม่ #{j+1}**")

                                    qual_val, qual_update = editable_field(
                                        "qualification_responsible (ใหม่)",
                                        value="",
                                        key_prefix=f"{record_id}_qual_new_{j}_qualification",
                                        default_update=True,   # กล่องใหม่ -> ติ๊ก "แก้ไข" ไว้ให้
                                    )

                                    name_val, name_update = editable_field(
                                        "name_responsible (ใหม่)",
                                        value="",
                                        key_prefix=f"{record_id}_qual_new_{j}_name",
                                        default_update=True,
                                    )

                                    degree_val, degree_update = editable_field(
                                        "degree_reponsible (ใหม่)",
                                        value="",
                                        key_prefix=f"{record_id}_qual_new_{j}_degree",
                                        default_update=True,
                                    )

                                    program_val, program_update = editable_field(
                                        "program_responsible (ใหม่)",
                                        value="",
                                        key_prefix=f"{record_id}_qual_new_{j}_program",
                                        default_update=True,
                                    )

                                    inst_val, inst_update = editable_field(
                                        "institute_responsible (ใหม่)",
                                        value="",
                                        key_prefix=f"{record_id}_qual_new_{j}_institute",
                                        default_update=True,
                                    )

                                    year_val, year_update = editable_field(
                                        "year_graduate_responsible (ใหม่)",
                                        value="",
                                        key_prefix=f"{record_id}_qual_new_{j}_year",
                                        default_update=True,
                                    )

                                    edited_qual.append(
                                        {
                                            "row_pos": None,   # หรือจะลบ key นี้ออกก็ได้
                                            "curriculum": curriculum_key,

                                            "qualification_responsible": qual_val,
                                            "name_responsible": name_val,
                                            "degree_reponsible": degree_val,
                                            "program_responsible": program_val,
                                            "institute_responsible": inst_val,
                                            "year_graduate_responsible": year_val,

                                            "qualification_responsible_update": qual_update,
                                            "name_responsible_update": name_update,
                                            "degree_reponsible_update": degree_update,
                                            "program_responsible_update": program_update,
                                            "institute_responsible_update": inst_update,
                                            "year_graduate_responsible_update": year_update,

                                            "is_new": True,
                                            "delete": False,
                                        }
                                    )



                        qual_inserted = True


            ctrl_col1, ctrl_col2 = st.columns(2)
            with ctrl_col1:
                add_plo_btn = st.form_submit_button(
                    "➕ เพิ่ม PLO ใหม่",
                    use_container_width=True,
                    on_click=inc_plo,   # 👈 สำคัญ
                )
            with ctrl_col2:
                clear_plo_btn = st.form_submit_button(
                    "🗑️ ล้าง PLO ใหม่",
                    use_container_width=True,
                    on_click=clear_plo,  # 👈 สำคัญ
                )

            qctrl1, qctrl2 = st.columns(2)
            with qctrl1:
                add_qual_btn = st.form_submit_button(
                    "➕ เพิ่มผู้รับผิดชอบใหม่",
                    use_container_width=True,
                    on_click=inc_qual,  # 👈 สำคัญ
                )
            with qctrl2:
                clear_qual_btn = st.form_submit_button(
                    "🗑️ ล้างผู้รับผิดชอบใหม่",
                    use_container_width=True,
                    on_click=clear_qual,  # 👈 สำคัญ
                )

            submit_info = st.form_submit_button(
                "💾 บันทึกการแก้ไขทั้งหมด",
                use_container_width=True,
            )


        if submit_info:
            try:
                save_information_changes(
                    curriculum_key=curriculum_key,
                    edited_info=edited_info,
                    edited_course_info=None,
                    mark_finish_info=True,
                    mark_finish_course=False,
                )

                if edited_plo:
                    save_plo_changes(curriculum_key, edited_plo)

                if edited_qual:
                    save_qualification_changes(curriculum_key, edited_qual)

                # ตั้งค่าให้รอบถัดไปโชว์แถบสีแดง
                st.session_state.save_done_banner = True
                st.session_state.save_done_message = "บันทึกข้อมูล information / PLO / ผู้รับผิดชอบเรียบร้อยแล้ว ✅"

                # ถ้าอยากใช้ reset_after_save ก็ยังเก็บไว้ได้
                st.session_state.reset_after_save = True

                st.rerun()

            except Exception as e:
                st.error(f"บันทึกไม่สำเร็จ (information): {e}")




    elif x2_mode == "course":
        st.subheader("📚 ข้อมูลรายวิชา (Course)")

        # ---------- ตัวนับ "รายวิชาใหม่" ----------
        course_count_key = f"new_course_count_{record_id}"
        if course_count_key not in st.session_state:
            st.session_state[course_count_key] = 0

        new_course_count = int(st.session_state[course_count_key])

        # 👉 callback สำหรับปุ่มเพิ่ม/ล้างรายวิชาใหม่
        def inc_course():
            st.session_state[course_count_key] = int(st.session_state.get(course_count_key, 0)) + 1

        def clear_course():
            st.session_state[course_count_key] = 0

        # ---------- ฟอร์มหลักของโหมด course ----------
        form_key = f"qa_form_{record_id}_course"

        with st.form(form_key):
            scroll_box = st.container(height=BOX_HEIGHT, border=True)

            with scroll_box:
                # ==== 1) ฟิลด์ summary จาก information ====
                st.markdown("### 📌 สรุปโครงสร้างหน่วยกิต / ชั่วโมง")

                course_info_cols = [
                    "max_semester",
                    "day_class",
                    "type_class",
                    "total_credits",
                    "gen_ed_credits",
                    "spec_credits",
                    "elec_credits",
                    "free_elec_credits",
                ]

                edited_course_info = {}
                for col_name in course_info_cols:
                    if col_name not in df.columns:
                        continue

                    original_value = str(row.get(col_name, "") or "")

                    key_prefix = f"{record_id}_course_info_{col_name}"

                    new_val, want_update = editable_field(
                        label=col_name,
                        value=original_value,
                        key_prefix=key_prefix,
                        is_text_area=False,
                        default_update=False,   # ของเดิมในชีต -> ยังไม่แก้เป็นค่าเริ่มต้น
                    )

                    edited_course_info[col_name] = {
                        "value": new_val,
                        "update": want_update,
                    }

                st.markdown("---")

                # ==== เตรียม DataFrame รายวิชาในหลักสูตรนี้ ====
                course_rows = pd.DataFrame()
                if curriculum_key and not course_df.empty and "curriculum" in course_df.columns:
                    mask_course = (
                        course_df["curriculum"].astype(str).str.strip()
                        == str(curriculum_key).strip()
                    )
                    # index 0..N-1 เฉพาะวิชาใน curriculum นี้
                    course_rows = course_df[mask_course].copy().reset_index(drop=True)


                # ==== ฟอร์มพิเศษสำหรับกำหนดชื่อประเภทของ "อื่นๆ" ====
                STANDARD_TYPES = ["วิชาศึกษาทั่วไป", "วิชาเฉพาะ", "วิชาเลือกเสรี"]

                # หา unique course_type_id ที่ไม่ใช่ STANDARD_TYPES และไม่ว่าง
                default_other_type = ""
                if not course_rows.empty and "course_type_id" in course_rows.columns:
                    type_series = course_rows["course_type_id"].astype(str).str.strip()
                    other_candidates = sorted(
                        {
                            t
                            for t in type_series
                            if t and t not in STANDARD_TYPES
                        }
                    )
                    if other_candidates:
                        # เลือกสักตัวมาเป็น default
                        default_other_type = other_candidates[0]

                other_key = f"course_other_type_{record_id}"
                if other_key not in st.session_state:
                    st.session_state[other_key] = default_other_type

                other_type_label = st.text_input(
                    "ชื่อประเภทวิชาที่ต้องการใช้แทนค่าที่เลือกเป็น 'อื่นๆ'",
                    key=other_key,
                    help=(
                        "ถ้าวิชาไหนคุณเลือกเป็น 'อื่นๆ' และกรอกค่านี้ "
                        "ระบบจะใช้ข้อความนี้เป็นค่า course_type_id ใหม่เวลาเซฟ "
                        "(ถ้าปล่อยว่างจะใช้ค่าเดิมในชีตหรือค่าว่าง)"
                    ),
                )

                st.markdown("---")

                # ==== 2) รายวิชาจากชีต course ====
                st.markdown("### 📚 รายวิชาทั้งหมดในหลักสูตรนี้")

                edited_course_list = []

                # ===== รายวิชาเดิม =====
                if course_rows.empty:
                    st.info("ยังไม่มีข้อมูลรายวิชาสำหรับ curriculum นี้ในชีต 'course'")
                else:
                    st.markdown("#### ✅ รายวิชาเดิม")

                    for i, c_row in course_rows.iterrows():
                        with st.container(border=True):
                            st.markdown(f"**รายวิชาเดิม #{i+1}**")

                            edited_one = {
                                "row_pos": i,  # 👈
                                "curriculum": curriculum_key,
                            }

                            # ----- จัดการ course_type_id แบบปุ่มกด 4 ตัว + ปุ่มแก้ไข -----
                            original_type = str(c_row.get("course_type_id", "") or "").strip()

                            type_options = [
                                "วิชาศึกษาทั่วไป",
                                "วิชาเฉพาะ",
                                "อื่นๆ",
                                "วิชาเลือกเสรี",
                            ]

                            # ถ้าไม่ใช่ type มาตรฐาน (หรือว่าง) -> radio default เป็น "อื่นๆ"
                            if original_type in STANDARD_TYPES:
                                default_choice = original_type
                            else:
                                default_choice = "อื่นๆ"

                            rcol, ecol = st.columns([4, 1])

                            with rcol:
                                type_choice = st.radio(
                                    "ประเภทวิชา (course_type_id)",
                                    options=type_options,
                                    index=type_options.index(default_choice),
                                    horizontal=True,
                                    key=f"{record_id}_course_{i}_course_type_id_radio",
                                )

                            # === คำนวณค่าใหม่ final_type จาก radio + other_type_label ===
                            if type_choice == "อื่นๆ":
                                if other_type_label.strip():
                                    # ถ้ามี label -> ใช้ label นี้เป็นค่าใหม่ "เสมอ"
                                    final_type = other_type_label.strip()
                                else:
                                    # ไม่มี label -> ใช้ค่าเดิม
                                    final_type = original_type
                            else:
                                final_type = type_choice

                            # ถ้า final_type ต่างจากค่าเดิม แปลว่าจะ "เปลี่ยนค่า" จริง ๆ
                            must_update = (final_type != original_type)

                            with ecol:
                                # ผูก key กับ other_type_label ด้วย เพื่อให้ Streamlit reset state
                                course_type_update = st.checkbox(
                                    "แก้ไข",
                                    key=f"{record_id}_course_{i}_course_type_id_edit_{other_type_label}",
                                    value=must_update,
                                    help="ระบบจะเขียนทับค่า course_type_id ถ้าค่าจริงเปลี่ยนจากเดิม",
                                )

                            # 👉 ตาม requirement: ถ้าค่าจริงเปลี่ยน ให้บังคับ update ไม่สนใจ checkbox
                            if must_update:
                                course_type_update = True

                            # แสดงค่าเดิมถ้าไม่ใช่ type มาตรฐาน เผื่อให้ user เห็นว่าเดิมเป็นอะไร
                            if original_type and original_type not in STANDARD_TYPES:
                                st.caption(f"ค่าเดิมในชีต: {original_type}")

                            edited_one["course_type_id"] = final_type
                            edited_one["course_type_id_choice"] = type_choice
                            edited_one["course_type_id_original"] = original_type
                            edited_one["course_type_id_update"] = course_type_update


                            # ----- ฟิลด์อื่น ๆ ของรายวิชา -----
                            fields = [
                                "th_abv",
                                "th_name",
                                "eng_abv",
                                "eng_name",
                                "credit",
                                "lect_hours",
                                "practice_hours",
                                "self_hours",
                                "th_desc",
                                "eng_desc",
                                "prerequisite",
                            ]

                            for field in fields:
                                val = str(c_row.get(field, "") or "")
                                key_prefix = f"{record_id}_course_{i}_{field}"

                                is_ta = field in ("th_desc", "eng_desc", "prerequisite")

                                new_val, update_flag = editable_field(
                                    label=field,
                                    value=val,
                                    key_prefix=key_prefix,
                                    is_text_area=is_ta,
                                    height=TEXTAREA_HEIGHT if is_ta else None,
                                    default_update=False,   # ของเดิม
                                )

                                edited_one[field] = new_val
                                edited_one[f"{field}_update"] = update_flag

                            # 👇 checkbox สำหรับลบรายวิชาเดิม
                            delete_flag = st.checkbox(
                                "ลบรายวิชานี้",
                                key=f"{record_id}_course_{i}_delete",
                                value=False,
                            )

                            edited_one["is_new"] = False
                            edited_one["delete"] = delete_flag

                            edited_course_list.append(edited_one)


                # ===== รายวิชาใหม่ =====
                if new_course_count > 0:
                    st.markdown("#### ➕ รายวิชาใหม่")

                for j in range(new_course_count):
                    with st.container(border=True):
                        st.markdown(f"**รายวิชาใหม่ #{j+1}**")

                        new_course = {
                            "row_pos": None,   # หรือไม่ใส่ก็ได้
                            "curriculum": curriculum_key,
                        }

                        # --- เลือกประเภทวิชาเหมือนเดิม + ปุ่มแก้ไข ---
                        type_options = [
                            "วิชาศึกษาทั่วไป",
                            "วิชาเฉพาะ",
                            "อื่นๆ",
                            "วิชาเลือกเสรี",
                        ]

                        rcol, ecol = st.columns([4, 1])

                        with rcol:
                            type_choice = st.radio(
                                "ประเภทวิชา (course_type_id) (ใหม่)",
                                options=type_options,
                                index=1,  # default เช่น "วิชาเฉพาะ"
                                horizontal=True,
                                key=f"{record_id}_course_new_{j}_course_type_id_radio",
                            )

                        with ecol:
                            course_type_update = st.checkbox(
                                "แก้ไข",
                                key=f"{record_id}_course_new_{j}_course_type_id_edit",
                                value=True,   # รายวิชาใหม่ -> แก้ เป็น default
                                help="ติ๊กถ้าต้องการบันทึก course_type_id ของวิชาใหม่นี้",
                            )

                        if type_choice == "อื่นๆ":
                            if other_type_label.strip():
                                final_type = other_type_label.strip()
                            else:
                                final_type = ""
                        else:
                            final_type = type_choice

                        new_course["course_type_id"] = final_type
                        new_course["course_type_id_choice"] = type_choice
                        new_course["course_type_id_original"] = ""
                        new_course["course_type_id_update"] = course_type_update

                        # --- ฟิลด์อื่นของรายวิชาใหม่ ---
                        fields = [
                            "th_abv",
                            "th_name",
                            "eng_abv",
                            "eng_name",
                            "credit",
                            "lect_hours",
                            "practice_hours",
                            "self_hours",
                            "th_desc",
                            "eng_desc",
                            "prerequisite",
                        ]

                        for field in fields:
                            key_prefix = f"{record_id}_course_new_{j}_{field}"
                            is_ta = field in ("th_desc", "eng_desc", "prerequisite")

                            val, update_flag = editable_field(
                                label=field + " (ใหม่)",
                                value="",
                                key_prefix=key_prefix,
                                is_text_area=is_ta,
                                height=TEXTAREA_HEIGHT if is_ta else None,
                                default_update=True,  # กล่องใหม่ ติ๊ก "แก้ไข" ให้เลย
                            )

                            new_course[field] = val
                            new_course[f"{field}_update"] = update_flag

                        new_course["is_new"] = True
                        new_course["delete"] = False

                        edited_course_list.append(new_course)
                        st.markdown("---")

            cctrl1, cctrl2 = st.columns(2)
            with cctrl1:
                add_course_btn = st.form_submit_button(
                    "➕ เพิ่มรายวิชาใหม่",
                    use_container_width=True,
                    on_click=inc_course,   # 👈
                )
            with cctrl2:
                clear_course_btn = st.form_submit_button(
                    "🗑️ ล้างรายวิชาใหม่",
                    use_container_width=True,
                    on_click=clear_course,  # 👈
                )

            submit_course = st.form_submit_button(
                "💾 บันทึกการแก้ไขทั้งหมด",
                use_container_width=True,
            )

        if submit_course:
            try:
                save_information_changes(
                    curriculum_key=curriculum_key,
                    edited_info=None,
                    edited_course_info=edited_course_info,
                    mark_finish_info=False,
                    mark_finish_course=True,
                )

                if edited_course_list:
                    save_course_changes(curriculum_key, edited_course_list)

                # ตั้งค่าให้รอบถัดไปโชว์แถบสีแดง
                st.session_state.save_done_banner = True
                st.session_state.save_done_message = "บันทึกข้อมูล course เรียบร้อยแล้ว ✅"

                # ถ้าอยากใช้ reset_after_save ก็ยังเก็บไว้ได้
                st.session_state.reset_after_save = True

                st.rerun()

            except Exception as e:
                st.error(f"บันทึกไม่สำเร็จ (course): {e}")

    # ===== แถบล่างสีแดงโชว์เมื่อเซฟเสร็จ =====
    if st.session_state.get("save_done_banner", False):
        msg = st.session_state.get("save_done_message", "Done")

        st.markdown(
            f"""
            <div id="save-done-banner" style="
                position: fixed;
                bottom: 0;
                left: 0;
                width: 100%;
                background-color: #ff4b4b;
                color: white;
                padding: 12px 24px;
                text-align: center;
                font-weight: bold;
                font-size: 18px;
                z-index: 9999;
            ">
                {msg}
            </div>

            <script>
            // ซ่อนแบนเนอร์หลังจาก 5 วินาที (5000 ms)
            setTimeout(function() {{
                var banner = document.getElementById("save-done-banner");
                if (banner) {{
                    banner.style.display = "none";
                }}
            }}, 5000);
            </script>
            """,
            unsafe_allow_html=True,
        )

        # เคลียร์ flag เพื่อไม่ให้ขึ้นซ้ำในการ rerun ครั้งถัดไป
        st.session_state.save_done_banner = False

