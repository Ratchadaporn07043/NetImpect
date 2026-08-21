"""
Tier 2 — "Hard" Tasks ที่ออกแบบให้บังคับคุยหลายรอบ (multi-round)
====================================================================
ปัญหาที่พบในชุดข้อมูลเดิม (1,544 trials): เกือบทุก trial จบใน 1 attempt เดียว
(Reviewer พูด APPROVED ตั้งแต่รอบแรก) ทำให้แทบไม่มีข้อมูลที่แสดงผลของ
"network เข้าไปรบกวนบทสนทนาหลายรอบ" เลย เพราะ task เดิมง่ายเกินไปสำหรับ
Qwen3:8b ที่จะทำถูกตั้งแต่รอบแรก

โมดูลนี้เพิ่ม task ที่ยากขึ้น + ซับซ้อนหลายเงื่อนไข เพื่อเพิ่มโอกาสให้ Reviewer
สั่ง REVISE อย่างน้อย 1 รอบ (โดยเฉพาะเมื่อใช้คู่กับ strict_reviewer=True ใน
multi_agent.py เวอร์ชัน Tier2 นี้)

ไม่แก้ experiment/tasks.py เดิม — TASKS/TASK_GROUND_TRUTH เดิมยังใช้งานได้ปกติ
"""

TIER2_HARD_TASKS = {
    "coding_task_hard": (
        "เขียนฟังก์ชัน Python ชื่อ `analyze_log_lines(lines: list[str]) -> dict` "
        "ที่รับ list ของ log line แต่ละบรรทัดมีรูปแบบ "
        "'YYYY-MM-DD HH:MM:SS LEVEL message' (เช่น '2026-01-01 10:00:00 ERROR disk full') "
        "แล้วคืนค่า dict ที่มี key ดังนี้ทั้งหมด: "
        "(1) 'count_by_level' เป็น dict นับจำนวนบรรทัดแยกตาม LEVEL, "
        "(2) 'error_messages' เป็น list ของ message ที่ LEVEL='ERROR' เท่านั้น เรียงตามเวลา, "
        "(3) 'first_error_timestamp' เป็น timestamp ของ ERROR แรกสุด หรือ None ถ้าไม่มี ERROR เลย, "
        "(4) 'malformed_lines' เป็น list ของบรรทัดที่ parse ไม่ได้ตามรูปแบบ (ต้อง handle "
        "โดยไม่ทำให้โปรแกรม crash). "
        "ต้องมี docstring อธิบาย input/output ชัดเจน และต้องมีตัวอย่างการเรียกใช้งาน "
        "อย่างน้อย 1 ตัวอย่างพร้อมผลลัพธ์ที่คาดหวัง"
    ),
    "planning_decision_hard": (
        "บริษัทมีงบจำกัดสามารถลงทุนได้แค่ 2 จาก 5 โครงการต่อไปนี้ในไตรมาสหน้า: "
        "(1) ปรับปรุง UX หน้าชำระเงิน คาดว่าลด cart-abandonment 8% "
        "(2) เพิ่ม feature ใหม่ที่ลูกค้า enterprise 3 รายขอมา มูลค่าสัญญารวม 2 ล้านบาท/ปี "
        "(3) แก้ bug ค้างเก่าด้าน security ที่ยังไม่มีการโจมตีเกิดขึ้นจริงแต่มีความเสี่ยงสูง "
        "(4) migrate ระบบฐานข้อมูลเก่าที่ค่า maintenance สูงขึ้นเรื่อยๆ ทุกปี "
        "(5) จ้างทีม support เพิ่มเพื่อลด response time จาก 24 ชม. เหลือ 4 ชม. "
        "ให้ (ก) จัดลำดับความสำคัญทั้ง 5 โครงการจากสำคัญที่สุดไปน้อยที่สุด พร้อมให้คะแนน "
        "impact/urgency/risk/cost แต่ละโครงการเป็นตัวเลข 1-5, "
        "(ข) เลือก 2 โครงการที่จะลงทุนจริงพร้อมเหตุผลที่อ้างอิงคะแนนจากข้อ (ก), "
        "(ค) ระบุความเสี่ยงของการ 'ไม่เลือก' โครงการที่เหลืออีก 3 โครงการ อย่างน้อยโครงการละ 1 ความเสี่ยง"
    ),
}

TIER2_HARD_TASK_GROUND_TRUTH = {
    "coding_task_hard": {
        "max_score": 5,
        "pass_score": 4,
        "rubric": [
            "มีฟังก์ชันชื่อ analyze_log_lines",
            "คืนค่า dict ที่มี count_by_level",
            "คืนค่า dict ที่มี error_messages เรียงตามเวลา",
            "คืนค่า dict ที่มี first_error_timestamp (จัดการกรณีไม่มี ERROR ด้วย)",
            "คืนค่า dict ที่มี malformed_lines และไม่ crash เมื่อ parse ไม่ได้",
            "มี docstring และตัวอย่างการใช้งาน",
        ],
        "checks": [
            {"id": "function_name", "description": "ระบุฟังก์ชัน analyze_log_lines", "any": ["analyze_log_lines"]},
            {"id": "count_by_level", "description": "มี count_by_level", "any": ["count_by_level"]},
            {"id": "error_messages", "description": "มี error_messages", "any": ["error_messages"]},
            {"id": "first_error_timestamp", "description": "มี first_error_timestamp", "any": ["first_error_timestamp"]},
            {"id": "malformed_lines", "description": "มี malformed_lines / จัดการ parse error", "any": ["malformed_lines", "malformed", "parse ไม่ได้", "ไม่ตรงรูปแบบ"]},
            {"id": "docstring_example", "description": "มี docstring/ตัวอย่างการใช้งาน", "any": ["docstring", "ตัวอย่าง", "example", ">>>"]},
        ],
    },
    "planning_decision_hard": {
        "max_score": 5,
        "pass_score": 4,
        "rubric": [
            "จัดลำดับความสำคัญทั้ง 5 โครงการ",
            "ให้คะแนน impact/urgency/risk/cost เป็นตัวเลขแต่ละโครงการ",
            "เลือก 2 โครงการชัดเจนพร้อมเหตุผลอ้างอิงคะแนน",
            "ระบุความเสี่ยงของการไม่เลือกโครงการที่เหลือ อย่างน้อย 3 ความเสี่ยง (โครงการละ 1)",
            "ครอบคลุมครบทั้ง (ก)(ข)(ค) ตามที่โจทย์กำหนด",
        ],
        "checks": [
            {"id": "ranks_all_five", "description": "จัดลำดับทั้ง 5 โครงการ", "any": ["ลำดับ", "อันดับ", "จัดอันดับ", "priorit"]},
            {"id": "scores_given", "description": "ให้คะแนน impact/urgency/risk/cost", "any": ["impact", "urgency", "risk", "cost", "คะแนน"]},
            {"id": "selects_two", "description": "เลือก 2 โครงการชัดเจน", "any": ["เลือก 2", "สอง โครงการ", "2 โครงการ", "เลือกลงทุน"]},
            {"id": "risk_of_not_choosing", "description": "ระบุความเสี่ยงของโครงการที่ไม่เลือก", "any": ["ไม่เลือก", "ความเสี่ยงของการ", "หากไม่ทำ", "ผลกระทบถ้าไม่"]},
            {"id": "structured_abc", "description": "ตอบครบตามโครงสร้าง ก/ข/ค หรือเทียบเท่า", "any": ["(ก)", "(ข)", "(ค)", "ก)", "ข)", "ค)"]},
        ],
    },
}
