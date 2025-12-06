import os
import io

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
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
    mask = (finish_info_int == 1) & (finish_course_int == 1)

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
finish_info_val = int(pd.to_numeric(row.get("finish_info", 0), errors="coerce") or 0)
finish_course_val = int(pd.to_numeric(row.get("finish_course", 0), errors="coerce") or 0)

x2_options = []
if finish_info_val == 0:
    x2_options.append("information")
if finish_course_val == 0:
    x2_options.append("course")

if not x2_options:
    st.success("หลักสูตรนี้ตรวจครบทั้ง information และ course แล้ว ✅")
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

                # ==== เตรียม PLO / Qualification ====
                plo_rows = pd.DataFrame()
                if curriculum_key and not plo_df.empty and "curriculum" in plo_df.columns:
                    mask_plo = (
                        plo_df["curriculum"].astype(str).str.strip()
                        == str(curriculum_key).strip()
                    )
                    plo_rows = plo_df[mask_plo].reset_index(drop=False)

                qual_rows = pd.DataFrame()
                if curriculum_key and not qual_df.empty and "curriculum" in qual_df.columns:
                    mask_qual = (
                        qual_df["curriculum"].astype(str).str.strip()
                        == str(curriculum_key).strip()
                    )
                    qual_rows = qual_df[mask_qual].reset_index(drop=False)

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
                                                "orig_index": int(plo_row["index"]),
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
                                            "orig_index": None,
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
                                                "orig_index": int(q_row["index"]),
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
                                        st.markdown("---")


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
                                            "orig_index": None,
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
                                    st.markdown("---")


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
            st.success("บันทึก (ตัวอย่าง – โหมด information, ยังไม่ได้เขียนกลับ Google Sheet จริง)")
            st.json(
                {
                    "mode": "information",
                    "faculty": active_fac,
                    "degree_full_th": active_deg,
                    "pdf_id": pdf_id,
                    "edited_information": edited_info,
                    "edited_plo": edited_plo,
                    "edited_qual": edited_qual,
                    "finish_info_new_value": 1,
                }
            )



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
                    course_rows = course_df[mask_course].reset_index(drop=False)

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
                                "orig_index": int(c_row["index"]),
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

                            # radio + checkbox อยู่คนละ column
                            rcol, ecol = st.columns([4, 1])

                            with rcol:
                                type_choice = st.radio(
                                    "ประเภทวิชา (course_type_id)",
                                    options=type_options,
                                    index=type_options.index(default_choice),
                                    horizontal=True,
                                    key=f"{record_id}_course_{i}_course_type_id_radio",
                                )

                            # คำนวณค่าใหม่ final_type จาก radio + other_type_label
                            if type_choice == "อื่นๆ":
                                if other_type_label.strip():
                                    # ถ้ามี label -> ใช้ label เป็นค่าใหม่ (รวมทุกแถวที่เป็น "อื่นๆ")
                                    final_type = other_type_label.strip()
                                else:
                                    # ไม่มี label -> ใช้ค่าเดิม (อาจว่าง/null หรือค่าอื่น ๆ)
                                    final_type = original_type
                            else:
                                # เลือกเป็นค่ามาตรฐาน
                                final_type = type_choice

                            # ถ้าค่าใหม่ไม่เท่าค่าเดิม -> default ให้ติ๊ก "แก้ไข"
                            default_update_flag = (final_type != original_type)

                            with ecol:
                                course_type_update = st.checkbox(
                                    "แก้ไข",
                                    key=f"{record_id}_course_{i}_course_type_id_edit",
                                    value=default_update_flag,
                                    help="ติ๊กถ้าต้องการให้เขียนทับค่า course_type_id กลับฐานข้อมูล",
                                )

                            # แสดงค่าเดิมถ้าไม่ใช่ type มาตรฐาน เผื่อให้ user เห็นว่าเดิมเป็นอะไร
                            if original_type and original_type not in STANDARD_TYPES:
                                st.caption(f"ค่าเดิมในชีต: {original_type}")

                            edited_one["course_type_id"] = final_type
                            edited_one["course_type_id_choice"] = type_choice
                            edited_one["course_type_id_original"] = original_type
                            edited_one["course_type_id_update"] = course_type_update  # flag สำหรับเขียนกลับ

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
                            st.markdown("---")

                # ===== รายวิชาใหม่ =====
                if new_course_count > 0:
                    st.markdown("#### ➕ รายวิชาใหม่")

                for j in range(new_course_count):
                    with st.container(border=True):
                        st.markdown(f"**รายวิชาใหม่ #{j+1}**")

                        new_course = {
                            "orig_index": None,
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
            st.success("บันทึก (ตัวอย่าง) – โหมด course, ยังไม่ได้เขียนกลับ Google Sheet จริง")
            st.json(
                {
                    "mode": "course",
                    "faculty": active_fac,
                    "degree_full_th": active_deg,
                    "pdf_id": pdf_id,
                    "edited_course_info": edited_course_info,
                    "edited_course_list": edited_course_list,
                    "finish_course_new_value": 1,
                }
            )

