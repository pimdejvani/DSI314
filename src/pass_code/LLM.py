
from google import genai
# # 2.0 = AIzaSyDNnUB-sqMsMclTb4JFJJ6Di54xqx9q5Hs
# # 2.5 = AIzaSyA5BA7ydJYn4T7zejQhdvoAJ_en-mkHNV0
# client = genai.Client(api_key="AIzaSyA5BA7ydJYn4T7zejQhdvoAJ_en-mkHNV0")

# response = client.models.generate_content(
#     model="gemini-2.0-flash", contents="ขอตัวเลขอราบิก 10 ตัวแรกเริ่มจาก 0"
# )
# print(response.text)

from pathlib import Path
from google import genai
from google.genai import types
import os

from src.utils.resolve import resolve_filename  # ใช้แค่ชื่อไฟล์ล้วนได้

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# หาไฟล์ด้วยชื่อไฟล์ (ไม่ต้องพาธเต็ม) – ไฟล์ต้องอยู่ใต้โฟลเดอร์ที่ mount แล้ว
fname = "(cleaned) (แก้) 3.อว.ร.บ. การเมืองและการระหว่างประเทศ ปรับปรุง พ.ศ. 2568.pdf"
pdf_path: Path = resolve_filename(fname)

# อ่านเป็น bytes แล้วแนบเข้า contents โดยตรง
pdf_bytes = pdf_path.read_bytes()

resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
        "หัวข้อ 2.3 แผนการรับนักศึกษาและผู้สําเร็จการศึกษาในระยะ 5 ปี ในปี 2571 มีนักศึกษารวมเท่าไหร่",
    ],
)

print(resp.text)
