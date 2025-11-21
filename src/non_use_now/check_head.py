
from pathlib import Path
import zipfile
from lxml import etree
import subprocess
import tempfile
import shutil
import sys

# ====== ปรับ path เอกสารของคุณที่นี่ ======
path_doc = Path(r"C:\Users\Pimdej\DSI314\ตัวอย่างหลักสูตร (เคสยาก)\(แก้) 3.อว.ร.บ. การเมืองและการระหว่างประเทศ ปรับปรุง พ.ศ. 2568.docx")
# ========================================


W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

SECTION_TYPES_THAT_START_NEW_PAGE = {"nextPage", "oddPage", "evenPage"}

def _read_document_xml_from_docx(docx_path: Path) -> etree._ElementTree:
    """
    เปิดไฟล์ .docx (เป็น zip) แล้วอ่าน word/document.xml คืนค่าเป็น XML tree
    """
    with zipfile.ZipFile(docx_path, "r") as zf:
        with zf.open("word/document.xml") as f:
            return etree.parse(f)

def _count_manual_page_breaks(doc_tree: etree._ElementTree) -> int:
    """
    นับ <w:br w:type="page"/>
    """
    root = doc_tree.getroot()
    # XPath หา w:br ที่มี w:type="page"
    br_elems = root.xpath(".//w:br[@w:type='page']",
                          namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"})
    return len(br_elems)

def _count_section_breaks_new_page(doc_tree: etree._ElementTree) -> int:
    """
    นับ section break ที่บังคับขึ้นหน้าใหม่ (nextPage/oddPage/evenPage)
    โดยข้าม sectPr สุดท้ายใน <w:body> (เป็นของทั้งเอกสาร ไม่ใช่จุด break)
    """
    root = doc_tree.getroot()
    body = root.find(f".//{W_NS}body")

    # หา sectPr ทั้งหมดที่อยู่ภายในย่อหน้า (w:p/w:pPr/w:sectPr) หรือใน body
    sectprs = body.findall(f".//{W_NS}sectPr")

    count = 0
    for sp in sectprs:
        # ข้าม sectPr สุดท้ายของ body (ส่วนใหญ่เป็นตัวปิดเอกสาร ไม่ใช่ break)
        if sp.getparent() is body:
            # ถ้า sectPr นี้เป็นลูกตัวสุดท้ายของ body -> ข้าม
            if list(body)[-1] is sp:
                continue

        stype = sp.find(f"./{W_NS}type")
        # ถ้าไม่มี type ให้ถือว่า "continuous" (ไม่นับ)
        val = stype.get(f"{W_NS}val") if stype is not None else "continuous"
        if val in SECTION_TYPES_THAT_START_NEW_PAGE:
            count += 1

    return count

def count_page_breaks_in_docx(docx_path: Path) -> dict:
    """
    คืน dict: {"manual_page_break": n1, "section_page_break": n2, "total": n1+n2}
    """
    tree = _read_document_xml_from_docx(docx_path)
    manual = _count_manual_page_breaks(tree)
    section_newpage = _count_section_breaks_new_page(tree)
    return {
        "manual_page_break": manual,
        "section_page_break": section_newpage,
        "total": manual + section_newpage
    }

def convert_doc_to_docx_with_libreoffice(doc_path: Path) -> Path:
    """
    ใช้ LibreOffice (soffice) แปลง .doc -> .docx ชั่วคราว แล้วคืน path .docx
    ต้องมี LibreOffice ใน PATH (คำสั่ง 'soffice')
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="doc2docx_"))
    try:
        cmd = [
            "soffice",
            "--headless",
            "--convert-to", "docx",
            "--outdir", str(tmpdir),
            str(doc_path)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = tmpdir / (doc_path.stem + ".docx")
        if not out.exists():
            raise RuntimeError("ไม่พบไฟล์ .docx หลังแปลงด้วย LibreOffice")
        return out
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"แปลง .doc เป็น .docx ไม่สำเร็จ: {e.stderr.decode(errors='ignore')}")
    # ไม่ลบ tmpdir ที่นี่ เพื่อให้ผู้ใช้ตรวจสอบได้ หากต้องการลบทิ้งค่อย shutil.rmtree(tmpdir) ภายหลัง

def count_page_breaks(path: Path) -> dict:
    """
    ตัวรวม: รับทั้ง .docx และ .doc
    - ถ้า .docx: นับตรงๆ
    - ถ้า .doc: พยายามแปลงเป็น .docx ด้วย LibreOffice แล้วนับ
    """
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return count_page_breaks_in_docx(path)
    elif suffix == ".doc":
        converted = convert_doc_to_docx_with_libreoffice(path)
        return count_page_breaks_in_docx(converted)
    else:
        raise ValueError("รองรับเฉพาะ .doc และ .docx เท่านั้น")

if __name__ == "__main__":
    # รองรับการรันตรงจากไฟล์นี้
    target = path_doc
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])

    result = count_page_breaks(target)
    print(f"ไฟล์: {target}")
    print(f"- Manual page breaks   : {result['manual_page_break']}")
    print(f"- Section page breaks  : {result['section_page_break']}")
    print(f"= รวมทั้งหมด (จุดขึ้นหน้า): {result['total']}")
