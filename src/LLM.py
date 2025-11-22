
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

api_key=os.getenv("GEMINI_API_KEY")

from google import genai
from google.genai import types

client = genai.Client(api_key)

content = ""

# .txt
file = types.Part.from_bytes(
    data=txt_content.encode("utf-8"), # ใช้ตัวแปรไฟล์ที่คุณมีอยู่แล้ว
    mime_type="text/plain",
)
# .pdf
file = types.Part.from_bytes(
    data=file_bytes,              # ใช้ตัวแปรไฟล์ที่คุณมีอยู่แล้ว
    mime_type="application/pdf", 
)



						

content_chunk1 = """จากในไฟล์ที่ทำการ extract ค่อนข้างเรียงจากบนลงล่าง 
หมวดที่ 1 จะมี  curr_id รหัสหลักสูตร curr_name_th ชื่อหลักสูตรภาษาไทย curr_name_en ชื่อหลักสูตรภาษาอังกฤษ	degree_full_th ชื่อปริญญาและสาขาวิชาภาษาไทยชื่อเต็ม degree_full_en ชื่อปริญญาและสาขาวิชาภาษาอังกฤษชื่อเต็ม degree_abr_th ชื่อปริญญาและสาขาวิชาภาษาไทยชื่อย่อ degree_abr_en ชื่อปริญญาและสาขาวิชาภาษาอังกฤษชื่อย่อ 
curr_category_id รูปแบบ จาก รูปแบบของหลักสูตร (เอามาเฉพาะค่าที่ถูกเลือก) curr_type_id ประเภทของหลักสูตร จาก รูปแบบของหลักสูตร (เอามาเฉพาะค่าที่ถูกเลือก) lang-id ภาษาที่ใช้ จาก รูปแบบของหลักสูตร (เอามาเฉพาะค่าที่ถูกเลือก เอามาเฉพาะชื่อภาษา) mou ความร่วมมือกับสถาบันอื่น จาก รูปแบบของหลักสูตร (เอามาเฉพาะค่าที่ถูกเลือก) first_open_semester สถานภาพของหลักสูตรและการพิจารณาอนุมัติ/เห็นชอบหลักสูตร จาก รูปแบบของหลักสูตร ให้เอาเลขภาคการศึกษาที่เปิดสอนมาใส่ first_open_year สถานภาพของหลักสูตรและการพิจารณาอนุมัติ/เห็นชอบหลักสูตร จาก รูปแบบของหลักสูตร ให้เอาเลขปีการศึกษาที่เปิดสอนมาใส่ 
careers อาชีพที่สามารถประกอบได้หลังสำเร็จการศึกษา จาก รูปแบบของหลักสูตร (ไม่เอาลำดับข้อ หากมีหลายตัวอยากให้ใช้ ,) campus_id สถานที่จัดการเรียนการสอน จาก รูปแบบของหลักสูตร (เอามาเฉพาะค่าที่ถูกเลือก หากมีหลายตัวอยากให้ใช้ ,) expense_type ประเภทโครงการ จากประเภทโครงการ จากรูปแบบ 
หมวดที่ 2 student_nation_id การรับเข้าศึกษา (เอามาเฉพาะค่าที่ถูกเลือก) qualification_collegian คุณสมบัติของผู้เข้าศึกษา (เอามาแค่เฉพาะเนื้อหาในเกณฑ์ที่เป็นข้อๆ ไม่เอาอักษรพิเศษ ไม่เอาลำดับข้อ หากมีหลายข้อให้ใช้ , )
หมวดที่ 3 type_plo ใน ผลลัพธ์การเรียนรู้ระดับหลักสูตร (เป็นเกณฑ์ภาษาอังกฤษที่มีลำดับ เช่น plo1 plo2 k2 s2 e1 c1 เอามาแค่ตัวอักษร) num_plo ใน ผลลัพธ์การเรียนรู้ระดับหลักสูตร (เป็นเกณฑ์ภาษาอังกฤษที่มีลำดับ เช่น plo1 plo2 k2 s2 e1 c1 เอามาแค่ตัวเลข) detail_plo ใน ผลลัพธ์การเรียนรู้ระดับหลักสูตร (เป็นเกณฑ์ภาษาอังกฤษที่มีลำดับ เช่น PLO 1 PLO 2 K2 S2 E1 C1 เอามาแค่คำอธิบายของเกณฑ์นั้น)
"""

schema_chunk1 = {
    "type": "object",  # JSON หลักต้องเป็น object (dict-like)

    "properties": {    # ฟิลด์ที่ object นี้ "มีได้"
        "curr_id": {
            "type": ["string", "null"],   # เป็น string หรือ null ก็ได้
        },
        "curr_name_th": {
            "type": ["string", "null"],   # string หรือ null
        },
        "curr_name_en": {
            "type": ["string", "null"],   # string หรือ null
        },
        "degree_full_th": {
            "type": ["string", "null"],   # เป็น string หรือ null ก็ได้
        },
        "degree_full_en": {
            "type": ["string", "null"],   # string หรือ null
        },
        "degree_abr_th": {
            "type": ["string", "null"],   # string หรือ null
        },
        "degree_abr_en": {
            "type": ["string", "null"],   # string หรือ null
        },
        "curr_category_id": {
            "type": ["string", "null"],   # เป็น string หรือ null ก็ได้
        },
        "curr_type_id": {
            "type": ["string", "null"],   # string หรือ null
        },
        "lang_id": {
            "type": ["string", "null"],   # string หรือ null
        },
        "mou": {
            "type": ["string", "null"],   # string หรือ null
        },
        "first_open_semester": {
            "type": ["integer", "null"],   # เป็น string หรือ null ก็ได้
        },
        "first_open_year": {
            "type": ["integer", "null"],   # string หรือ null
        },
        "careers": {
            "type": ["string", "null"],   # string หรือ null
        },
        "campus_id": {
            "type": ["string", "null"],   # string หรือ null
        },
        "expense_type": {
            "type": ["string", "null"],   # เป็น string หรือ null ก็ได้
        },
        "student_nation_id": {
            "type": ["string", "null"],   # string หรือ null
        },
        "qualification_collegian": {
            "type": ["string", "null"],   # string หรือ null
        },
		
        "plo": {
            "type": "array",
            "items": {      
                "type": "object",
                "properties": {
                    "type_plo": {"type": ["string", "null"]},
                    "num_plo": {"type": ["integer", "null"]},
                    "detail_plo": {"type": ["string", "null"]},
                },
                "required": [],
                "additionalProperties": False,  
            },
        },
    },

    "required": [],
    "additionalProperties": False,  
}


content_chunk2 = """จากในไฟล์ที่ทำการ extract ค่อนข้างเรียงจากบนลงล่าง 
max_semester ระยะเวลาการศึกษาสูงสุด จาก ระบบการจัดการศึกษาและระยะเวลาการศึกษา (เอามาเฉพาะค่าที่ถูกเลือกและเอามาแค่เลข) day_class วัน-เวลาในการดำเนินการเรียนการสอน จาก การดำเนินการหลักสูตร (เอามาเฉพาะค่าที่ถูกเลือก หากมีหลายค่าให้ใช้ ,) type_class ระบบการศึกษา จาก การดำเนินการหลักสูตร (เอามาเฉพาะค่าที่ถูกเลือก หากมีหลายค่าให้ใช้ ,)
#'หากหลักสูตรมีหลายรูปแบบให้เลือก เลือกรูปแบบแรก' total_credits จำนวนหน่วยกิตรวม จาก หลักสูตร ใน โครงสร้างหลักสูตร รายวิชา และหน่วยกิต (เอามาแค่ค่าผลรวม) gen_ed_credits จำนวนหน่วยกิตรวมวิชาศึกษาทั่วไป จาก หลักสูตร ใน โครงสร้างหลักสูตร รายวิชา และหน่วยกิต (เอามาแค่ค่าผลรวม) spec_credits จำนวนหน่วยกิตรวมวิชาเฉพาะ จาก หลักสูตร ใน โครงสร้างหลักสูตร รายวิชา และหน่วยกิต (เอามาแค่ค่าผลรวม)  elec_credits จำนวนหน่วยกิตรวมวิชาเลือก/วิชาโท (ปล.อาจมีความต่างเล็กน้อย) จาก หลักสูตร ใน โครงสร้างหลักสูตร รายวิชา และหน่วยกิต (เอามาแค่ค่าผลรวม)  free_elec_credits จำนวนหน่วยกิตรวมวิชาเลือกเสรี จาก หลักสูตร ใน โครงสร้างหลักสูตร รายวิชา และหน่วยกิต (เอามาแค่ค่าผลรวม) 
course_type_id ข้อมูลที่มาจากหัวข้อว่าวิชานี้เป็นวิชาจากโครงสร้างหลักสูตรวิชาชนิดใด เช่น หมวดวิชาศึกษาทั่วไป, หมวดวิชาเฉพาะ, หมวดวิชาโทหรือวิชาเลือก, หมวดวิชาเลือกเสรี th_abv ชื่อรหัสวิชาย่อ ภาษาไทย th_name ชื่อวิชาเต็ม ภาษาไทย	eng_abv ชื่อรหัสวิชาย่อ ภาษาอังกฤษ	eng_name ชื่อวิชาเต็ม ภาษาอังกฤษ credit, lect_hours, practice_hours, self_hours 4 อันนี้มาจากหน่อวยกิตของแต่ละวิชา มีโครงสร้างเป็น 'credit (lect_hours-practice_hours-self_hours)' เช่น '3 (3-0-6)' ให้เอามาแค่เลข
"""

schema_chunk2 = {
    "type": "object",  # JSON หลักต้องเป็น object (dict-like)

    "properties": {    # ฟิลด์ที่ object นี้ "มีได้"

        "day_class": {
            "type": ["string", "null"],   # string หรือ null
        },
        "type_class": {
            "type": ["string", "null"],   # string หรือ null
        },
        "max_semester": {
            "type": ["string", "null"],   # เป็น string หรือ null ก็ได้
        },
        "total_credits": {
            "type": ["number", "null"],   # string หรือ null
        },
 		
        "gen_ed_credits": {
            "type": ["string", "null"],   # string หรือ null
        },
        "spec_credits": {
            "type": ["string", "null"],   # string หรือ null
        },
        "elec_credits": {
            "type": ["string", "null"],   # เป็น string หรือ null ก็ได้
        },
        "free_elec_credits": {
            "type": ["string", "null"],   # string หรือ null
        },

        "course": {
            "type": "array",
            "items": {      
                "type": "object",
                "properties": {
                    "course_type_id": {"type": ["string", "null"]},
                    "th_abv": {"type": ["integer", "null"]},
                    "th_name": {"type": ["integer", "null"]},
                    "eng_abv": {"type": ["string", "null"]},
                    "eng_name": {"type": ["string", "null"]},
                    "credit": {"type": ["string", "null"]},
                    "lect_hours": {"type": ["string", "null"]},
                    "practice_hours": {"type": ["string", "null"]},
                    "self_hours": {"type": ["string", "null"]},
                },
                "required": [],
                "additionalProperties": False,  
            },
        },
    },

    "required": [],
    "additionalProperties": False,  
}


content_chunk3 = """จากในไฟล์ที่ทำการ extract ค่อนข้างเรียงจากบนลงล่าง 
th_abv ชื่อรหัสวิชาย่อ ภาษาไทย th_desc คำอธิบายรายวิชาภาษาไทย (ไม่ต้องเอา วิชาบังคับก่อน มา) eng_abv ชื่อรหัสวิชาย่อ ภาษาอังกฤษ Prerequisite เอามาหากว่ามีชื่อรหัสวิชาภาษาอังกฤษมา นอกจากนั้นไม่เอา ไม่เอาเกณฑ์อื่น eng_desc คำอธิบายรายวิชาภาษาอังกฤษ (ไม่ต้องเอา Prerequisite มา) 
"""



schema_chunk3 = {
    "type": "object",  # JSON หลักต้องเป็น object (dict-like)

    "properties": {    # ฟิลด์ที่ object นี้ "มีได้"
        "course": {
            "type": "array",
            "items": {      
                "type": "object",
                "properties": {
                    "th_abv": {"type": ["string", "null"]},
                    "th_desc": {"type": ["integer", "null"]},
                    "eng_abv": {"type": ["integer", "null"]},
                    "prerequisite": {"type": ["string", "null"]},
                    "eng_desc": {"type": ["string", "null"]},
                },
                "required": [],
                "additionalProperties": False,  
            },
        },
    },

    "required": [],
    "additionalProperties": False,  
}



content_chunk4 = """จากในไฟล์ที่ทำการ extract ค่อนข้างเรียงจากบนลงล่าง 
หมวดที่ 6 count_research งานวิจัยหรือ บทความวิจัย (ชิ้น) จาก ด้านวิชาการ count_academic_paper ผลงานทางวิชาการอื่น ๆ จาก ด้านวิชาการ count_lecturer_academic จำนวนอาจารย์ประจำหลักสูตร (คน) จาก ด้านวิชาการ
count_lecturer_full จำนวนอาจารย์ประจำไม่ว่าชนชาติใดรวม จาก ด้านการบริหารจัดการ (เอามาแค่เลข) count_lecturer_extra  จำนวนอาจารย์พิเศษรวม (เอามาแค่เลข) จาก ด้านการบริหารจัดการ count_staff จำนวนเจ้าหน้าที่ (เอามาแค่เลข) จาก ด้านการบริหารจัดการ
qualification_responsible, name_responsible, degree_reponsible, program_responsible, institute_responsible, year_graduate_responsible เป็นข้อมูลจากตารางของอาจารย์ผู้รับผิดชอบหลักสูตรและอาจารย์ประจำหลักสูตร บางทีอาจมีอาจารย์ท่านอื่นด้วย แต่เอาเฉพาะอาจารย์ผู้รับผิดชอบ โดยqualification_responsible ตำแหน่งทางวิชาการ,name_responsible ชื่อ - สกุล, degree_reponsible คุณวุฒิ, program_responsible สาขาวิชา, institute_responsible สถาบัน, year_graduate_responsible ปีพ.ศ. เอามาแค่เลข
หมวดที่ 7 other_grade เป็นเกณฑ์การประเมิณที่ไม่ใช่เกรด A-F ให้เก็บใน format 'ตัวย่ออังกฤษ(ความหมายภาษาไทย)' เช่น 'S(ใช้ได้)' (ถ้ามีหลายตัวให้ใส่มาทั้งหมดแล้วใช้ ,) criteria_graduate เกณฑ์การสําเร็จการศึกษาตามหลักสูตร ให้เอามาเฉพาะเกณฑ์ที่ทำให้สำเร็จการศึกษาทที่เป็นข้อๆ แต่เอาข้อออก ให้ใส่มารวมกันแล้วใช้ ,
หมวดที่ 8 และ 9 curr_qa ชื่อเกณฑ์ในการประเมิณหลักสูตร อาจอยู่ในทั้ง 8 และ 9 หรืออยู่แค่อย่างละที่ ถ้าอยู่ในหมวด 9 จะอยู่แค่เฉพาะในส่วน ผลการด าเนินงานของหลักสูตร/ผลการประกันคุณภาพการศึกษา ฉันอยากได้แค่ชื่อเกณฑ์และเอาแค่ชื่อย่อ เช่น AACSB, EQUIS, AMBA, AUN-QA, EdPEx, IQA,มาตรฐานของกระทรวงฯ, สกอ., สปอว. (ถ้ามีหลายอันใส่มาแค่ใช้ ,) แต่ที่เป็นพวก มคอ. ไม่เอา
"""



schema_chunk4 = {
    "type": "object",  # JSON หลักต้องเป็น object (dict-like)

    "properties": {    # ฟิลด์ที่ object นี้ "มีได้"

        "count_research": {
            "type": ["integer", "null"],   # string หรือ null
        },
        "count_academic_paper": {
            "type": ["integer", "null"],   # string หรือ null
        },
        "count_lecturer_academic": {
            "type": ["integer", "null"],   # เป็น string หรือ null ก็ได้
        },
        "count_lecturer_full": {
            "type": ["integer", "null"],   # string หรือ null
        },
 		
        "count_lecturer_extra": {
            "type": ["integer", "null"],   # string หรือ null
        },
        "count_staff": {
            "type": ["integer", "null"],   # string หรือ null
        },				

        "qualification_responsible": {
            "type": "array",
            "items": {      
                "type": "object",
                "properties": {
                    "qualification_responsible": {"type": ["string", "null"]},
                    "name_responsible": {"type": ["integer", "null"]},
                    "degree_reponsible": {"type": ["integer", "null"]},
                    "program_responsible": {"type": ["string", "null"]},
                    "institute_responsible": {"type": ["string", "null"]},
                    "year_graduate_responsible": {"type": ["integer", "null"]},
                "required": [],
                "additionalProperties": False,  
            },
        },
    },

        "criteria_graduate": {
            "type": ["string", "null"],   # เป็น string หรือ null ก็ได้
        },
        "curr_qa": {
            "type": ["string", "null"],   # string หรือ null
        },

    },

    "required": [],
    "additionalProperties": False,  
}



# ----------------------------
# 1) ตั้งค่า config (anti-hallucinate + JSON)
# ----------------------------
config = types.GenerateContentConfig(
        # ทำให้ deterministic / anti-hallucinate
    temperature=0.0,        # ความสุ่มของคำตอบ: 0 = เน้นตรง, ไม่ครีเอทีฟ (เหมาะกับ extract/parse)
    top_p=0.3,              # nucleus sampling: บีบให้เลือกจากกลุ่มคำที่ model มั่นใจ (0.3 = ค่อนข้าง conservative)
    top_k=40,               # เลือกจาก top 40 คำที่เป็นไปได้สูงสุดก่อนสุ่ม ลดโอกาสใช้คำแปลก ๆ
    candidate_count=1,      # ให้สร้างคำตอบกี่เวอร์ชันต่อ 1 call (1 = อันเดียวพอ)
    presence_penalty=0.0,   # ปรับให้ model พยายาม/ไม่พยายามพูดหัวข้อเดิมซ้ำ ๆ (0 = ไม่บังคับอะไร)
    frequency_penalty=0.0,  # ปรับโทษการใช้คำเดิมซ้ำ ๆ ในประโยค (0 = ปล่อยธรรมชาติ, ไม่ไปดึงให้หลากหลาย)

    # JSON mode
    response_mime_type="application/json",
    response_schema=my_schema,  # ใส่ JSON schema ของคุณ

    # บทบาท
    system_instruction=(
        """
        You are an information extraction engine.

        Rules:
        - Use ONLY information that is explicitly present in the provided document (PDF/TXT).
        - Do NOT use outside knowledge.
        - Do NOT guess or infer missing values.
        - If a field is missing or not clearly specified, set it to null.
        - Copy numbers, dates, codes, and names exactly as they appear.
        - If you are uncertain, do not guess; use null.
        - responde same language as appear.

        Output must strictly follow the JSON schema. No extra keys, no free text.
        """
    ),
)

config.thinking_config = types.ThinkingConfig(thinking_budget=0) # ปิดโหมด thinking ของ 2.5-flash


resp = client.models.generate_content(
    model="gemini-2.5-flash",     # หรือ "gemini-2.0-flash" ก็ได้ (แต่ไม่มี thinking_config)
    contents=[
        file,                 # ตัวไฟล์
        content,
    ],
    config=config,
)

print(resp.text) 