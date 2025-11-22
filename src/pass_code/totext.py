
from docx import Document

def docx_to_txt(docx_path, txt_path):
    doc = Document(docx_path)
    with open(txt_path, "w", encoding="utf-8") as f:
        for para in doc.paragraphs:
            f.write(para.text + "\n")
    print(f"✅ แปลงเสร็จแล้ว: {txt_path}")

# if __name__ == "__main__":
#     docx_to_txt("ตัวอย่างหลักสูตร (เคสยาก)/3.อว.ร.บ. การเมืองและการระหว่างประเทศ ปรับปรุง พ.ศ. 2568.docx", "1.คณะพาณิชย์ บริหารธุรกิจบัณฑิต ภาษาไทย 20 สค.68.txt")
