
# doc2pdf.py
from pathlib import Path
import sys

import aspose.words as aw  # <-- นำเข้าไว้บนสุด

# ===== ปรับพาธไฟล์ของคุณ =====
DOCX_PATH = Path(r"C:\Users\Pimdej\DSI314\ตัวอย่างหลักสูตร (เคสยาก)\(แก้) 3.อว.ร.บ. การเมืองและการระหว่างประเทศ ปรับปรุง พ.ศ. 2568.docx")
PDF_PATH  = DOCX_PATH.with_suffix(".pdf")
# =================================

def convert_with_custom_ttf(docx_path: Path, pdf_path: Path, font_dir: Path) -> None:
    doc = aw.Document(str(docx_path))

    # แหล่งฟอนต์: ระบบ + โฟลเดอร์ของเราที่มี .ttf
    fs = aw.fonts.FontSettings()
    system_src = aw.fonts.SystemFontSource()
    folder_src = aw.fonts.FolderFontSource(str(font_dir), True)  # scan subfolders = True
    fs.set_fonts_sources([system_src, folder_src])

    # ตั้งค่า substitution: ถ้าหาฟอนต์ไม่เจอให้ใช้ "TH Sarabun New"
    subs = fs.substitution_settings
    subs.default_font_substitution.default_font_name = "TH Sarabun New"
    subs.font_info_substitution.enabled = True
    subs.table_substitution.enabled = True
    # แมปฟอนต์ยอดนิยมให้แทนด้วย TH Sarabun New (เพิ่มชื่อได้ตามต้องการ)
    for fam in ["Times New Roman", "Arial", "Calibri", "Tahoma", "TH SarabunPSK", "Angsana New", "Cordia New"]:
        subs.table_substitution.set_substitutes(fam, ["TH Sarabun New"])

    doc.font_settings = fs

    # บันทึกเป็น PDF พร้อมฝังฟอนต์
    opt = aw.saving.PdfSaveOptions()
    opt.embed_full_fonts = True     # ฝังฟอนต์เต็ม (ไฟล์ใหญ่ขึ้น แต่คงรูปดีที่สุด)
    opt.use_core_fonts = False      # ไม่บังคับ core fonts
    # ถ้าต้องการ PDF/A
    # opt.compliance = aw.saving.PdfCompliance.PDF_A_2A

    doc.save(str(pdf_path), opt)

def main():
    if not DOCX_PATH.exists():
        print(f"ไม่พบไฟล์ DOCX: {DOCX_PATH}")
        sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    # วาง THSarabunNew.ttf (และถ้ามี Bold/Italic/BI) ไว้ในโฟลเดอร์เดียวกับสคริปต์นี้
    convert_with_custom_ttf(DOCX_PATH, PDF_PATH, script_dir)
    print(f"แปลงสำเร็จ → {PDF_PATH}")

if __name__ == "__main__":
    main()
