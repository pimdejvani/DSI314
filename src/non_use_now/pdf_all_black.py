
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image

# ===== ปรับพาธไฟล์ของคุณ =====
INPUT_PDF = Path(r"C:\Users\Pimdej\DSI314\ตัวอย่างหลักสูตร (เคสยาก)\(แก้) 3.อว.ร.บ. การเมืองและการระหว่างประเทศ ปรับปรุง พ.ศ. 2568.pdf")
OUTPUT_PDF = INPUT_PDF.with_name(f"(cleaned) {INPUT_PDF.stem}.pdf")
# =================================

# ค่าความเข้มของสีดำที่ถือว่า “ดำพอ” (0-255; ยิ่งต่ำยิ่งต้องดำสนิท)
BLACK_THRESHOLD = 215  # ปรับตามต้องการ: ถ้า PDF ตัวอักษรเทา ให้เพิ่มเป็น 80–100


def keep_only_black_pixels(img: Image.Image, threshold=BLACK_THRESHOLD) -> Image.Image:
    """
    รับภาพ (PIL Image) แล้วคืนภาพที่ pixel สีดำจะคงไว้ ส่วนอื่นเป็นขาว
    ใช้ค่าเฉลี่ย (gray = (r+g+b)/3) เพื่อเทียบกับ threshold
    """
    img = img.convert("RGB")
    pixels = img.load()
    w, h = img.size

    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            gray = (r + g + b) // 3
            if gray > threshold:  # ถ้าไม่ดำ
                pixels[x, y] = (255, 255, 255)  # ทำเป็นขาว
            else:
                pixels[x, y] = (0, 0, 0)  # ทำให้ดำแน่นอน
    return img


def clean_pdf(input_path: Path, output_path: Path):
    doc = fitz.open(str(input_path))
    output_doc = fitz.open()

    print(f"กำลังประมวลผล {len(doc)} หน้า...")
    for page_number in range(len(doc)):
        page = doc.load_page(page_number)
        # render เป็นภาพ
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        # ทำความสะอาด
        clean_img = keep_only_black_pixels(img)
        # แปลงกลับเป็น PDF หน้าเดียว
        img_pdf = fitz.open()
        img_bytes = clean_img.tobytes("jpeg", "RGB")
        rect = fitz.Rect(0, 0, clean_img.width, clean_img.height)
        new_page = img_pdf.new_page(width=rect.width, height=rect.height)
        new_page.insert_image(rect, stream=img_bytes)
        # แนบเข้ากับไฟล์รวม
        output_doc.insert_pdf(img_pdf)
        print(f"ทำหน้า {page_number+1}/{len(doc)} เสร็จแล้ว")

    output_doc.save(str(output_path))
    output_doc.close()
    doc.close()
    print(f"บันทึกไฟล์ใหม่แล้ว: {output_path}")


if __name__ == "__main__":
    clean_pdf(INPUT_PDF, OUTPUT_PDF)
