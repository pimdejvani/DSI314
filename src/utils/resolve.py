# src/utils/resolve.py
from __future__ import annotations
from pathlib import Path
import os
from typing import List

def _iter_search_dirs() -> List[Path]:
    """
    อ่านรายการโฟลเดอร์ฐานจาก ENV: FILE_SEARCH_PATH
    - รูปแบบ: คั่นด้วย ':' (Linux/Docker) หรือ ';' (Windows)
    - ถ้าไม่ตั้งค่า: ใช้ค่าเริ่มต้น [/data, /app/src]
    """
    raw = os.getenv("FILE_SEARCH_PATH")
    if raw:
        sep = ";" if (os.name == "nt" and ";" in raw) else ":"
        parts = [p.strip() for p in raw.split(sep) if p.strip()]
    else:
        parts = ["/data", "/app/src"]

    dirs = []
    for p in parts:
        path = Path(p).resolve()
        if path.exists():
            dirs.append(path)
    return dirs

def resolve_filename(name: str, *, case_insensitive: bool = True) -> Path:
    """
    ค้นหาไฟล์จาก 'ชื่อไฟล์ล้วน' (ไม่รองรับโหมด prefix/substring/glob อีกต่อไป)
    - เดินค้นหาใต้ทุกโฟลเดอร์ฐาน
    - เทียบชื่อไฟล์แบบตรงตัว (เลือกไม่แคร์ตัวพิมพ์เล็กใหญ่ได้ด้วย case_insensitive)
    - ถ้าพบหลายตำแหน่ง เลือกไฟล์ที่แก้ไขล่าสุด (mtime มากสุด)
    """
    if not name or Path(name).name != name:
        raise ValueError("ใส่เฉพาะ 'ชื่อไฟล์' เช่น 'report.docx' ห้ามมีโฟลเดอร์พาธ")

    search_dirs = _iter_search_dirs()
    if not search_dirs:
        raise FileNotFoundError("ไม่มีโฟลเดอร์สำหรับค้นหา (FILE_SEARCH_PATH ว่าง/ไม่พบ)")

    key = name.casefold() if case_insensitive else name
    candidates: List[Path] = []

    for base in search_dirs:
        # เดินทุกไฟล์ใต้ base แล้วเทียบเฉพาะ 'ชื่อไฟล์'
        for p in base.rglob("*"):
            if p.is_file():
                fn = p.name.casefold() if case_insensitive else p.name
                if fn == key:
                    candidates.append(p)

    if not candidates:
        raise FileNotFoundError(
            f"ไม่พบไฟล์ชื่อ '{name}' ใน: {', '.join(map(str, search_dirs))}"
        )

    if len(candidates) == 1:
        return candidates[0]

    # ถ้าชนหลายไฟล์ → เอาไฟล์ที่แก้ไขล่าสุด
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]