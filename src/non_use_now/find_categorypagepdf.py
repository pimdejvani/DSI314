from pypdf import PdfReader
from rapidfuzz import fuzz
import httpx
import io 

file_id = "1rFfJmfPEcle1SdTTzhoPBUNKpnKdzLYL"
url = f"https://drive.google.com/uc?export=download&id={file_id}"

# ดาวน์โหลด pdf เป็น bytes
resp = httpx.get(url, follow_redirects=True)
print('---------------',resp)
resp.raise_for_status()
pdf_bytes = resp.content

# ให้ PdfReader อ่านจาก bytes แทนไฟล์
reader = PdfReader(io.BytesIO(pdf_bytes))

targets = [
    "ภาคผนวก"
]

# เกณฑ์ similarity (0–100), ยิ่งสูงยิ่งเหมือน
THRESHOLD = 100

results = {t: [] for t in targets}

for page_idx, page in enumerate(reader.pages, start=1):
    text = page.extract_text() or ""
    # ตัดเป็นบรรทัด เพื่อให้ fuzzy ตรงหัวหมวดมากขึ้น
    for line in text.splitlines():
        for target in targets:
            score = fuzz.partial_ratio(target, line)
            if score >= THRESHOLD:
                results[target].append((page_idx, score))
                # ถ้าเจอแล้วจะไม่เช็คบรรทัดอื่นซ้ำมากเกินไปก็ได้
                # break

# แสดงผล
for target in targets:
    if results[target]:
        pages = sorted(set(p for p, _ in results[target]))
        print(f"{target} พบที่หน้า: {pages}")
    else:
        print(f"{target} ไม่พบในไฟล์ หรืออาจเป็นภาพสแกน / OCR ไม่ครบ")
