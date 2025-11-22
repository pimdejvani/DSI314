import os

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
import streamlit as st

# ================== CONFIG & GOOGLE CLIENTS ==================

st.set_page_config(page_title="Curriculum QA Tool", layout="wide")

SERVICE_ACCOUNT_FILE = "service_account.json"
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = "information"  # ใช้ sheet 'information'

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash"

# ความสูงของ PDF และกรอบฟอร์ม (px)
PDF_HEIGHT = 800

# สร้าง credentials และ client
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service_spread = build("sheets", "v4", credentials=creds).spreadsheets()


# ================== DATA LAYER: READ SHEET ==================

@st.cache_data(show_spinner=True)
def load_curriculum_data() -> pd.DataFrame:
    """
    อ่านข้อมูลจากชีต 'information' แล้วแปลงเป็น DataFrame

    - header อยู่ที่แถว B2 (คอลัมน์ B เป็นต้นไป)
    - ข้อมูลจริงเริ่มแถวถัดไป (B3 ลงไป)
    - normalize แต่ละแถวให้มีจำนวน column เท่ากับ header
    """
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


# ================== PDF VIEWER (GOOGLE DRIVE PREVIEW) ==================

def drive_preview_iframe(pdf_id: str, height: int) -> str:
    """
    ฝัง PDF โดยใช้ Google Drive preview โดยตรง
    ต้องตั้งสิทธิ์ไฟล์ใน Drive เป็น 'Anyone with the link - Viewer'
    """
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


# ================== STREAMLIT UI ==================

st.title("Curriculum QA")

df = load_curriculum_data()
if df.empty:
    st.error("ไม่พบข้อมูลในชีต 'information' หรือโหลดไม่สำเร็จ")
    st.stop()

# ===== ตรวจว่ามีคอลัมน์ที่ต้องใช้ครบไหม =====
required_cols = [
    "pdf id",
    "faculty",
    "degree_full_th",
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

# ================== SEARCH BAR ด้านบน ==================

faculty_list = sorted(df["faculty"].dropna().unique().tolist())

search_col1, search_col2, search_col3 = st.columns([2, 2, 1])

with search_col1:
    fac_options = ["-- เลือกคณะ --"] + faculty_list
    fac_ui = st.selectbox(
        "คณะ (faculty)",
        options=fac_options,
        index=fac_options.index(st.session_state.filter_faculty)
        if st.session_state.filter_faculty in fac_options
        else 0,
    )

with search_col2:
    if fac_ui != "-- เลือกคณะ --":
        degree_list = sorted(
            df[df["faculty"] == fac_ui]["degree_full_th"]
            .dropna()
            .unique()
            .tolist()
        )
        deg_options = ["-- เลือกหลักสูตร --"] + degree_list

        deg_ui = st.selectbox(
            "ชื่อหลักสูตร (degree_full_th)",
            options=deg_options,
            index=deg_options.index(st.session_state.filter_degree)
            if st.session_state.filter_degree in deg_options
            else 0,
        )
    else:
        deg_ui = None
        st.selectbox(
            "ชื่อหลักสูตร (degree_full_th)",
            options=["กรุณาเลือกคณะก่อน"],
            index=0,
            disabled=True,
        )

with search_col3:
    search_clicked = st.button("🔍 ค้นหา", use_container_width=True)

if search_clicked:
    if fac_ui == "-- เลือกคณะ --":
        st.warning("กรุณาเลือกคณะ (faculty)")
    elif deg_ui is None or deg_ui == "-- เลือกหลักสูตร --":
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

# ========= จากตรงนี้ลงไป: render PDF + ฟอร์ม หลังจากค้นหาแล้ว =========

active_fac = st.session_state.filter_faculty
active_deg = st.session_state.filter_degree

filtered = df[
    (df["faculty"] == active_fac)
    & (df["degree_full_th"] == active_deg)
]

if filtered.empty:
    st.warning("ไม่พบข้อมูลที่ตรงกับ faculty + degree_full_th ที่เลือก")
    st.stop()

row = filtered.iloc[0]
pdf_id = row.get("pdf id", "")

# ===== แสดงสรุปผลการค้นหา =====
st.subheader("ผลการค้นหา")
st.markdown(
    f"""
**คณะ (faculty):** {active_fac}  
**ชื่อหลักสูตร (degree_full_th):** {active_deg}  
**pdf id:** `{pdf_id}`
"""
)

st.markdown("---")

# ================== LAYOUT 30:70 ==================

left_col, right_col = st.columns([3, 7])



# ทำให้ฟอร์ม (qa_form) เป็นกล่องที่เลื่อนในตัวเอง สูงประมาณ 600px
BOX_HEIGHT = 700  # px

st.markdown(
    f"""
    <style>
    /* Streamlit ใช้ div[data-testid="stForm"] ไม่ใช่ form */
    div[data-testid="stForm"] {{
        max-height: {BOX_HEIGHT}px !important;
        overflow-y: auto !important;
        padding: 12px;
        border: 1px solid #ddd;
        border-radius: 6px;
        background-color: #fafafa;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)
# ------------------ ด้านซ้าย: PDF ------------------
with left_col:
    st.subheader("📄 PDF หลักสูตร")

    pdf_id = (pdf_id or "").strip()
    if not pdf_id:
        st.warning("ไม่มีค่า 'pdf id' ในแถวนี้")
    else:
        iframe_html = drive_preview_iframe(pdf_id, height=PDF_HEIGHT)
        st.markdown(iframe_html, unsafe_allow_html=True)


# ------------------ ด้านขวา: กล่องเลื่อน + ช่องแก้ไขข้อความจาก data จริง ------------------
with right_col:
    st.subheader("📝 ข้อมูลหลักสูตร")

    FIELD_COLUMNS = [
        "curr_id",
        "faculty",
        "curr_name_th",
        "curr_name_en",
        "degree_full_th",
        "degree_full_en",
        "degree_abr_th",
        "degree_abr_en",
        "curr_category_id",
        "curr_type_id",
        "lang_id",
        "MOU",
        "first_open_semester",
        "first_open_year",
        "careers",
        "campus_id",
        "expense_type",
        "student_nation_id",
        "qualification_collegian",
        "max_semester",
        "day_class",
        "type_class",
        "total_credits",
        "gen_ed_credits",
        "spec_credits",
        "elec_credits",
        "free_elec_credits",
        "count_research",
        "count_academic_paper",
        "count_lecturer_academic",
        "count_lecturer_full",
        "count_lecturer_extra",
        "count_staff",
        "other_grade",
        "criteria_graduate",
        "curr_qa",
    ]

    # ใช้ form เพื่อให้มีปุ่มบันทึกด้านล่าง และ form ทั้งหมดจะอยู่ใน "กล่องเลื่อน"
    with st.form("qa_form"):
        edited_values = {}

        for col_name in FIELD_COLUMNS:
            if col_name not in df.columns:
                continue

            original_value = row.get(col_name, "")
            if original_value is None:
                original_value = ""
            original_value = str(original_value)

            # label สวย ๆ ให้ดูง่าย
            st.markdown(f"**{col_name}**")

            # ช่องแก้ข้อความ (เติมค่าจาก columns ไว้ก่อน)
            # ถ้าเนื้อหายาวมากจะใช้ text_area แทน text_input ก็ได้
            new_value = st.text_input(
                label="",
                value=original_value,
                key=f"edit_{col_name}",
            )

            edited_values[col_name] = new_value

            st.markdown("---")

        # ปุ่มบันทึกอยู่ "ด้านล่างสุดของกล่องเลื่อน" (ใน form เดียวกัน)
        submit = st.form_submit_button("💾 บันทึกการแก้ไข", use_container_width=True)

    if submit:
        st.success("บันทึก (ตัวอย่าง) – ยังไม่ได้เขียนกลับ Google Sheet จริง")
        st.json(
            {
                "faculty": active_fac,
                "degree_full_th": active_deg,
                "pdf_id": pdf_id,
                "edited_values": edited_values,
            }
        )

    # ปุ่มบันทึกอยู่ด้านล่างกล่อง (ไม่เลื่อนตาม เน้นกดง่าย)
    if st.button("💾 บันทึก", use_container_width=True):
        st.success("บันทึก (ตัวอย่าง) – ยังไม่ได้เขียนกลับ Google Sheet จริง")