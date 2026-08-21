"""
Test Tasks (Benchmarks)
=========================
แยกออกมาจาก scenarios.py เพื่อให้ scenarios.py เก็บเฉพาะเรื่อง network scenario
ส่วนไฟล์นี้เก็บเฉพาะ task prompt ที่ใช้ทดสอบ multi-agent workflow

เพิ่ม Ground Truth / Rubric สำหรับ evaluator หลังจบ workflow:
- Reviewer ยังตรวจ Worker ระหว่างคุยตามปกติ
- Ground-truth evaluator ตรวจ final answer หลังจบเท่านั้น ไม่ช่วยแก้งานระหว่างรัน
"""

TASKS = {
    "coding_task": (
        "เขียนฟังก์ชัน Python ชื่อ `is_prime(n)` ที่รับจำนวนเต็ม แล้วคืนค่า True/False "
        "ว่าเป็นจำนวนเฉพาะหรือไม่ พร้อมอธิบายหลักการสั้นๆ"
    ),
    "research_summary": (
        "สรุปข้อดี-ข้อเสียของการใช้ Retrieval-Augmented Generation (RAG) "
        "เทียบกับการ fine-tune โมเดลโดยตรง ให้ได้ใจความภายใน 5 ข้อ"
    ),
    "data_analysis": (
        "สมมติมีข้อมูลยอดขายรายเดือน 12 เดือน ให้เสนอวิธีการวิเคราะห์ trend "
        "และบอกว่าควรใช้กราฟประเภทไหนถึงจะสื่อสารได้ดีที่สุด"
    ),
    "planning_decision": (
        "ทีมมีงบ 3 อย่างให้เลือกลงทุนอย่างใดอย่างหนึ่ง: (1) ปรับปรุง UX, "
        "(2) เพิ่ม feature ใหม่, (3) แก้ bug ค้างเก่า ช่วยวางแผนว่าควรเลือกอะไรก่อน "
        "พร้อมเหตุผลสั้นๆ"
    ),
}

TASK_GROUND_TRUTH = {
    "coding_task": {
        "max_score": 5,
        "pass_score": 4,
        "rubric": [
            "มีฟังก์ชันชื่อ is_prime(n)",
            "คืนค่า boolean True/False",
            "จัดการ n <= 1 เป็น False",
            "จัดการ 2 เป็น True และเลขคู่มากกว่า 2 เป็น False",
            "ตรวจตัวหารถึง sqrt(n) หรือ i*i <= n เพื่อประสิทธิภาพ",
            "มีคำอธิบายหลักการสั้นๆ",
        ],
        "checks": [
            {"id": "function_name", "description": "ระบุฟังก์ชัน is_prime", "any": ["is_prime"]},
            {"id": "boolean_return", "description": "คืนค่า True/False", "any": ["True", "False", "boolean", "บูลีน"]},
            {"id": "n_le_1", "description": "อธิบาย/จัดการ n <= 1", "any": ["<= 1", "< 2", "น้อยกว่า 2", "1 ไม่", "0 ไม่"]},
            {"id": "two_case", "description": "จัดการเลข 2", "any": ["n == 2", "เท่ากับ 2", "2 เป็น", "2 คือ"]},
            {"id": "sqrt_bound", "description": "ตรวจถึงรากที่สองหรือ i*i <= n", "any": ["sqrt", "ราก", "i * i", "i*i", "** 0.5", "กำลังสอง"]},
            {"id": "explanation", "description": "มีคำอธิบายหลักการ", "any": ["หลักการ", "เพราะ", "ตัวหาร", "จำนวนเฉพาะ"]},
        ],
    },
    "research_summary": {
        "max_score": 5,
        "pass_score": 4,
        "rubric": [
            "เปรียบเทียบ RAG กับ fine-tuning โดยตรง",
            "กล่าวถึงข้อดีของ RAG เช่น อัปเดตความรู้ได้ง่าย/ลด hallucination/อ้างอิงแหล่งข้อมูล",
            "กล่าวถึงข้อเสียของ RAG เช่น latency, retrieval quality, infrastructure complexity",
            "กล่าวถึงข้อดีของ fine-tuning เช่น ปรับ style/behavior/domain pattern ได้ดี",
            "กล่าวถึงข้อเสียของ fine-tuning เช่น ค่าใช้จ่าย/ข้อมูลฝึก/อัปเดตความรู้ยาก",
            "อยู่ในกรอบประมาณ 5 ข้อและสรุปเป็นใจความ",
        ],
        "checks": [
            {"id": "rag_mentioned", "description": "กล่าวถึง RAG", "any": ["RAG", "Retrieval-Augmented", "retrieval"]},
            {"id": "fine_tune_mentioned", "description": "กล่าวถึง fine-tune", "any": ["fine-tune", "fine tune", "fine-tuning", "ปรับจูน"]},
            {"id": "rag_advantage", "description": "มีข้อดีของ RAG", "any": ["อัปเดต", "update", "แหล่งข้อมูล", "อ้างอิง", "ลด hallucination", "ความรู้ใหม่"]},
            {"id": "rag_disadvantage", "description": "มีข้อเสียของ RAG", "any": ["latency", "retrieval", "ค้นคืน", "ซับซ้อน", "infrastructure", "คุณภาพข้อมูล"]},
            {"id": "finetune_advantage", "description": "มีข้อดีของ fine-tuning", "any": ["style", "พฤติกรรม", "domain", "เฉพาะทาง", "รูปแบบ"]},
            {"id": "finetune_disadvantage", "description": "มีข้อเสียของ fine-tuning", "any": ["ค่าใช้จ่าย", "ข้อมูลฝึก", "train", "อัปเดตยาก", "ล้าสมัย"]},
        ],
    },
    "data_analysis": {
        "max_score": 5,
        "pass_score": 4,
        "rubric": [
            "เสนอการจัดเรียงข้อมูลยอดขายรายเดือน 12 เดือนตามเวลา",
            "วิเคราะห์ trend ภาพรวม เช่น เพิ่มขึ้น/ลดลง/seasonality/outlier",
            "แนะนำ line chart เป็นกราฟหลักสำหรับ time series",
            "อาจเสริม moving average หรือเปรียบเทียบเดือนต่อเดือน",
            "สื่อสารขั้นตอนวิเคราะห์อย่างเป็นระบบ",
        ],
        "checks": [
            {"id": "time_order", "description": "กล่าวถึงข้อมูลรายเดือน/ลำดับเวลา", "any": ["รายเดือน", "12 เดือน", "เวลา", "time series", "เดือน"]},
            {"id": "trend", "description": "กล่าวถึง trend", "any": ["trend", "แนวโน้ม", "เพิ่มขึ้น", "ลดลง"]},
            {"id": "line_chart", "description": "แนะนำ line chart", "any": ["line chart", "กราฟเส้น", "line graph"]},
            {"id": "seasonality_outlier", "description": "พิจารณา seasonality หรือ outlier", "any": ["season", "ฤดูกาล", "outlier", "ผิดปกติ", "ยอดพุ่ง", "ยอดตก"]},
            {"id": "moving_average", "description": "กล่าวถึง moving average/เปรียบเทียบ MoM", "any": ["moving average", "ค่าเฉลี่ยเคลื่อนที่", "MoM", "เดือนต่อเดือน", "เปอร์เซ็นต์เปลี่ยนแปลง"]},
        ],
    },
    "planning_decision": {
        "max_score": 5,
        "pass_score": 4,
        "rubric": [
            "เลือกทางลงทุนหนึ่งอย่างอย่างชัดเจน หรือจัดลำดับความสำคัญพร้อมตัวเลือกแรก",
            "ให้เหตุผลเชิง impact/urgency/risk/customer value",
            "พิจารณา trade-off ระหว่าง UX, feature ใหม่, bug ค้างเก่า",
            "มีแผนปฏิบัติสั้นๆ เช่น ประเมินข้อมูล วัดผล ทำ sprint",
            "คำตอบเป็น actionable และเหมาะกับการตัดสินใจทีม",
        ],
        "checks": [
            {"id": "clear_choice", "description": "มีการเลือก/จัดลำดับชัดเจน", "any": ["ควรเลือก", "อันดับแรก", "ก่อน", "prioritize", "เลือก"]},
            {"id": "mentions_options", "description": "กล่าวถึงตัวเลือกหลัก", "any": ["UX", "feature", "bug", "บั๊ก"]},
            {"id": "impact_reason", "description": "มีเหตุผลด้านผลกระทบ/ลูกค้า", "any": ["impact", "ผลกระทบ", "ลูกค้า", "ผู้ใช้", "value", "คุณค่า"]},
            {"id": "risk_urgency", "description": "มีเหตุผลด้านความเสี่ยงหรือความเร่งด่วน", "any": ["เสี่ยง", "risk", "เร่งด่วน", "ค้าง", "เสียหาย", "technical debt"]},
            {"id": "action_plan", "description": "มีแผนดำเนินการ", "any": ["แผน", "ขั้นตอน", "sprint", "วัดผล", "ประเมิน", "roadmap"]},
        ],
    },
}
