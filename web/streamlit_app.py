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
        max-height: 100px !important;   /* ลองเล่น 160–220 ได้ */
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
SHEET_NAME = "information"  # ใช้ sheet 'information'
PLO_SHEET_NAME = "plo"
QUAL_SHEET_NAME = "qualification_responsible"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash"


# ความสูงของ PDF และกรอบฟอร์ม (px) – ตอนใช้ st.pdf() จะไม่เป๊ะ 800px แต่ตัว viewer จะปรับเอง
PDF_HEIGHT = 800

# สร้าง credentials และ client
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service_spread = build("sheets", "v4", credentials=creds).spreadsheets()
service_drive = build("drive", "v3", credentials=creds)  # ✅ เพิ่ม Drive client

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

@st.cache_data(show_spinner=True)
def load_plo_data() -> pd.DataFrame:
    """
    อ่านข้อมูล PLO จากชีต 'plo'
    - header อยู่ที่แถว B2 (คอลัมน์ B เป็นต้นไป)
    - ข้อมูลจริงเริ่มแถวถัดไป (B3 ลงไป)
    """
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
    # ลบช่องว่างหัว-ท้ายจากชื่อคอลัมน์ เผื่อมี space แถม
    df.columns = [str(c).strip() for c in df.columns]
    return df

@st.cache_data(show_spinner=True)
def load_qualification_data() -> pd.DataFrame:
    """
    อ่านข้อมูลจากชีต 'qualification_responsible'
    - header อยู่ที่แถว B2
    """
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



# ================== DATA LAYER: DOWNLOAD PDF FROM DRIVE ==================

@st.cache_data(show_spinner=True)
def download_pdf_bytes(file_id: str) -> bytes:
    """
    ดาวน์โหลดไฟล์ PDF จาก Google Drive (ด้วย service account)
    แล้วคืนค่าเป็น bytes สำหรับใช้กับ st.pdf()

    หมายเหตุ: ต้องแชร์ไฟล์ใน Drive ให้ service account ตัวนี้มีสิทธิ์อย่างน้อย Viewer
    """
    request = service_drive.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        # จะไม่ print progress เพื่อไม่รก log
    return fh.getvalue()

# ================== STREAMLIT UI ==================

st.title("Curriculum QA")

df = load_curriculum_data()
plo_df = load_plo_data()
qual_df = load_qualification_data()
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

faculty_series = df["faculty"].dropna().astype(str).str.strip()
faculty_list = sorted(
    [f for f in faculty_series.unique().tolist() if f != ""]
)

search_col1, search_col2, search_col3 = st.columns([2, 2, 1])

# ---------- เลือกคณะ ----------
with search_col1:
    st.markdown("**คณะ (faculty)**")

    FAC_BOX_HEIGHT = 150  # กล่องสูงประมาณ 5 แถว
    fac_box = st.container(height=FAC_BOX_HEIGHT, border=True)

    with fac_box:
        fac_options = ["-- ยังไม่เลือกคณะ --"] + faculty_list

        # ถ้าเคยเลือกคณะไว้แล้ว ให้ติ๊กอันนั้น, ถ้ายังไม่เคย → ติ๊ก placeholder
        if (
            st.session_state.filter_faculty is not None
            and st.session_state.filter_faculty in faculty_list
        ):
            default_fac_index = faculty_list.index(st.session_state.filter_faculty) + 1
        else:
            default_fac_index = 0  # placeholder

        fac_choice = st.radio(
            label="คณะ",                 # label ภายใน (จะถูกซ่อน)
            options=fac_options,
            index=default_fac_index,
            key="faculty_radio",
            label_visibility="collapsed",  # 👈 ซ่อน label กันแถบว่างด้านบน
        )

    # แปลงค่าที่เลือกให้เป็น None ถ้ายังอยู่ที่ placeholder
    fac_ui = None if fac_choice == "-- ยังไม่เลือกคณะ --" else fac_choice

# ---------- เลือกหลักสูตร ----------
with search_col2:
    st.markdown("**ชื่อหลักสูตร (degree_full_th)**")

    if fac_ui is not None:
        degree_series = (
            df.loc[df["faculty"] == fac_ui, "degree_full_th"]
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

                # ถ้าเคยเลือกหลักสูตรไว้แล้ว ให้ติ๊กกลับไปที่เดิม
                if (
                    st.session_state.filter_degree is not None
                    and st.session_state.filter_degree in degree_list
                    and st.session_state.filter_faculty == fac_ui
                ):
                    default_deg_index = degree_list.index(st.session_state.filter_degree) + 1
                else:
                    default_deg_index = 0  # placeholder

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
record_id = row.get("curr_id", f"{active_fac}_{active_deg}")
curriculum_key = row.get("curriculum", "")
# ===== แสดงสรุปผลการค้นหา =====
st.markdown(
    f"""
**ผลการค้นหา pdf id:** `{pdf_id}`
"""
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

            # 👇 ใช้ streamlit-pdf-viewer แทน st.pdf
            pdf_viewer(
                input=pdf_bytes,      # ใช้ bytes จาก Google Drive API
                width="100%",         # หรือจะใส่เป็น 800 ก็ได้
                height=PDF_HEIGHT,    # ใช้ค่าที่คุณตั้งไว้ด้านบน
                render_text=True,     # ⭐ สำคัญมาก: ทำให้คลุม+Ctrl+C ได้
                key="pdf_viewer_main",
            )

        except Exception as e:
            st.error(f"โหลด PDF ไม่สำเร็จ: {e}")
    else:
        st.warning("ไม่มี pdf id")

with right_col:
    st.subheader("📝 ข้อมูลหลักสูตร (แก้ไขได้ในกล่องเลื่อน)")

    # คอลัมน์ที่ไม่ต้องแสดง
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

    # ฟิลด์ที่แสดงจริง
    FIELD_COLUMNS = [c for c in df.columns if c not in EXCLUDED_COLUMNS]

    TEXTAREA_HEIGHT = 100
    BOX_HEIGHT = 700

    # ช่องที่อยากเป็น text_area
    LONG_TEXT_COLUMNS = {
        "mou",
        "careers",
        "qualification_collegian",
        "other_grade",
        "criteria_graduate",
    }

    form_key = f"qa_form_{record_id}"

    # 👇 form ครอบใหญ่สุด
    with st.form(form_key):
        # 👇 กล่องเลื่อนอยู่ใน form
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
                plo_rows = plo_df[mask_plo].reset_index(drop=False)

            # ===== เตรียมข้อมูล Qualification =====
            qual_rows = pd.DataFrame()
            if curriculum_key and not qual_df.empty and "curriculum" in qual_df.columns:
                mask_qual = (
                    qual_df["curriculum"].astype(str).str.strip()
                    == str(curriculum_key).strip()
                )
                qual_rows = qual_df[mask_qual].reset_index(drop=False)

            plo_inserted = False
            qual_inserted = False

            # ========== 1) ฟอร์มหลักจาก information ==========
            for col_name in FIELD_COLUMNS:
                if col_name not in df.columns:
                    continue

                original_value = row.get(col_name, "") or ""
                original_value = str(original_value)

                widget_key = f"edit_{record_id}_{col_name}"

                # ช่องยาวใช้ text_area
                if col_name in LONG_TEXT_COLUMNS:
                    new_value = st.text_area(
                        label=col_name,
                        value=original_value,
                        key=widget_key,
                        height=TEXTAREA_HEIGHT,
                    )
                else:
                    new_value = st.text_input(
                        label=col_name,
                        value=original_value,
                        key=widget_key,
                    )

                edited_info[col_name] = new_value
                st.markdown("---")

                # ===== 2) แทรก PLO หลัง qualification_collegian =====
                if (not plo_inserted) and (col_name == "qualification_collegian"):
                    st.subheader("📌 Program Learning Outcomes (PLO)")

                    if not curriculum_key:
                        st.info("ยังไม่มีค่า curriculum ในชีต information")
                    elif plo_df.empty:
                        st.info("ยังไม่มีข้อมูลในชีต 'plo' หรือโหลดไม่สำเร็จ")
                    elif "curriculum" not in plo_df.columns:
                        st.info("ไม่พบคอลัมน์ 'curriculum' ในชีต 'plo'")
                        st.write("คอลัมน์ที่มีใน plo_df คือ:", list(plo_df.columns))
                    elif plo_rows.empty:
                        st.info("ยังไม่มีข้อมูล PLO สำหรับ curriculum นี้ในชีต 'plo'")
                    else:
                        for i, plo_row in plo_rows.iterrows():
                            with st.container(border=True):
                                st.markdown(f"**PLO #{i+1}**")

                                type_val = st.text_input(
                                    "type_plo",
                                    value=str(plo_row.get("type_plo", "")),
                                    key=f"{record_id}_plo_{i}_type",
                                )
                                num_val = st.text_input(
                                    "num_plo",
                                    value=str(plo_row.get("num_plo", "")),
                                    key=f"{record_id}_plo_{i}_num",
                                )
                                detail_val = st.text_area(
                                    "detail_plo",
                                    value=str(plo_row.get("detail_plo", "")),
                                    key=f"{record_id}_plo_{i}_detail",
                                    height=TEXTAREA_HEIGHT,
                                )

                                edited_plo.append(
                                    {
                                        "orig_index": int(plo_row["index"]),
                                        "curriculum": curriculum_key,
                                        "type_plo": type_val,
                                        "num_plo": num_val,
                                        "detail_plo": detail_val,
                                    }
                                )
                                st.markdown("---")

                    plo_inserted = True  # กันไม่ให้วาดซ้ำ

                # ===== 3) แทรก Qualification หลัง count_staff =====
                if (not qual_inserted) and (col_name == "count_staff"):
                    st.subheader("👩‍🏫 Qualification / ผู้รับผิดชอบหลักสูตร")

                    if not curriculum_key:
                        st.info("ยังไม่มีค่า curriculum ในชีต information")
                    elif qual_df.empty:
                        st.info("ยังไม่มีข้อมูลในชีต 'qualification_responsible' หรือโหลดไม่สำเร็จ")
                    elif "curriculum" not in qual_df.columns:
                        st.info("ไม่พบคอลัมน์ 'curriculum' ในชีต 'qualification_responsible'")
                        st.write("คอลัมน์ที่มีใน qual_df คือ:", list(qual_df.columns))
                    elif qual_rows.empty:
                        st.info("ยังไม่มีข้อมูล qualification_responsible สำหรับ curriculum นี้")
                    else:
                        for i, q_row in qual_rows.iterrows():
                            with st.container(border=True):
                                st.markdown(f"**ผู้รับผิดชอบ #{i+1}**")

                                qual_val = st.text_area(
                                    "qualification_responsible",
                                    value=str(q_row.get("qualification_responsible", "")),
                                    key=f"{record_id}_qual_{i}_qualification",
                                )
                                name_val = st.text_input(
                                    "name_responsible",
                                    value=str(q_row.get("name_responsible", "")),
                                    key=f"{record_id}_qual_{i}_name",
                                )
                                degree_val = st.text_input(
                                    "degree_reponsible",
                                    value=str(q_row.get("degree_reponsible", "")),
                                    key=f"{record_id}_qual_{i}_degree",
                                )
                                program_val = st.text_input(
                                    "program_responsible",
                                    value=str(q_row.get("program_responsible", "")),
                                    key=f"{record_id}_qual_{i}_program",
                                )
                                inst_val = st.text_input(
                                    "institute_responsible",
                                    value=str(q_row.get("institute_responsible", "")),
                                    key=f"{record_id}_qual_{i}_institute",
                                )
                                year_val = st.text_input(
                                    "year_graduate_responsible",
                                    value=str(q_row.get("year_graduate_responsible", "")),
                                    key=f"{record_id}_qual_{i}_year",
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
                                    }
                                )
                                st.markdown("---")

                    qual_inserted = True  # กันไม่ให้วาดซ้ำ

        # 👇 ปุ่ม submit ยังอยู่ “ใน form” แต่ไม่อยู่ในกล่องเลื่อนแล้ว
        submit = st.form_submit_button(
            "💾 บันทึกการแก้ไขทั้งหมด",
            use_container_width=True,
        )

    if submit:
        st.success("บันทึก (ตัวอย่าง) – ยังไม่ได้เขียนกลับ Google Sheet จริง")
        st.json(
            {
                "faculty": active_fac,
                "degree_full_th": active_deg,
                "pdf_id": pdf_id,
                "edited_information": edited_info,
                "edited_plo": edited_plo,
                "edited_qualification": edited_qual,
            }
        )


