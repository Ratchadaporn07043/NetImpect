# Tier 5 — Mitigation Strategies

**เป้าหมาย:** จากทุก Tier ก่อนหน้าที่ "วัดปัญหา" — Tier5 นี้ "แก้ปัญหา" 2 อย่างที่พบ แล้วพิสูจน์ด้วยข้อมูลว่าแก้ได้จริงหรือไม่ (before/after comparison) ซึ่งเป็นเนื้อหาที่ทำให้ paper มีมุม contribution ที่แข็งแรงขึ้นมาก (ไม่ใช่แค่ "รายงานปัญหา" แต่ "เสนอและพิสูจน์วิธีแก้")

## Mitigation A — Adaptive Timeout

ปัญหา: `LLM_TIMEOUT` เดิมคงที่ 120 วินาทีทุก scenario แม้ delay/loss สูงจะทำให้แต่ละ LLM call ช้าลงมาก → เกิด timeout "ปลอม" (แค่ต้องรอนานกว่านี้ ไม่ใช่ระบบพัง) → เสีย retry โดยไม่จำเป็น

วิธีแก้: ขยาย timeout ตามสัดส่วนของ delay_ms/loss_pct/jitter_ms ของ scenario นั้นๆ (สูตรอยู่ใน `_adaptive_timeout_seconds()` ใน `multi_agent.py`)

## Mitigation B — Context Caching

ปัญหา: เมื่อเกิด timeout/error กลางบทสนทนาต้อง retry ทั้ง task ใหม่ Planner ต้องคิดแผนใหม่จากศูนย์ทุกรอบ retry ทั้งที่แผนเดิมอาจใช้ได้อยู่แล้ว → เสีย LLM call ที่เสี่ยงเจอ network แย่ซ้ำโดยไม่จำเป็น

วิธีแก้: cache ข้อความแรกของ Planner จาก attempt แรก ถ้าต้อง retry ให้ข้าม Planner ไปเลย ส่งแผนที่ cache ไว้ให้ Worker เริ่มทำงานต่อได้ทันที (ลด 1 LLM call ที่เสี่ยงเจอ network แย่ต่อทุก retry)

## ⚠️ ขั้นตอนก่อนรัน

```bash
cd NetImpact
cp multi_agent.py multi_agent.py.backup_original   # สำรองไว้เสมอ (รวมถ้าเคยใช้ Tier2 มาก่อนด้วย)
cp "Tier5_Mitigation/multi_agent.py" multi_agent.py
```

ไฟล์นี้เป็น**เวอร์ชันสะสม**ที่รวม `strict_reviewer` จาก Tier2 ไว้ในตัวแล้ว (ใช้ Tier2 + Tier5 พร้อมกันได้โดยไม่ต้อง merge เอง) และ `mitigation="none"` เป็นค่า default เสมอ — ถ้าไม่ส่งพารามิเตอร์นี้ พฤติกรรมเหมือนต้นฉบับ 100% (ตรวจสอบโดย `tests_extended/test_baseline_regression.py`)

## วิธีรัน — Before/After Comparison

รันแกน **loss main-effect เดิม** (11 ระดับ: 0,1,5,10,15,20,25,30,40,50,75%) × 4 tasks × 5 repeats = **220 trials ต่อเงื่อนไข** เลือก loss axis เพราะมีผลชัดเจนที่สุดจากการวิเคราะห์เชิงลึก (degradation region ที่ 70-75% ตาม Tier1 — จำเพาะกับช่วงเวลาที่วัดครั้งนี้เท่านั้น: การวัดในช่วงเวลาหลัง (Tier8 §6 / Tier9) พบว่าจุดวิกฤตย้ายไปที่ 80% แทน)

```bash
python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --dry-run

# รันทีละเงื่อนไข (แนะนำ):
python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition none --resume             # baseline ควบคุม
python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition adaptive_timeout --resume  # Mitigation A
python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition context_cache --resume     # Mitigation B

# หรือรันรวดเดียวทั้ง 3 เงื่อนไข (660 trials ≈ 26.7 ชม.)
python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition all --resume
```

log แยกเป็น `logs_tier5_none/`, `logs_tier5_adaptive_timeout/`, `logs_tier5_context_cache/` — เทียบ error/timeout rate, จำนวน LLM call เฉลี่ยต่อ trial, success rate, ground_truth_score เฉลี่ย ระหว่าง 3 โฟลเดอร์นี้เพื่อสรุปว่า mitigation แต่ละอันช่วยได้จริงแค่ไหน

## ไฟล์ในโฟลเดอร์นี้

| ไฟล์ | หน้าที่ |
|---|---|
| `multi_agent.py` | **แทนที่** root เดิม — รวม strict_reviewer (Tier2) + mitigation A/B (default="none"=เดิม 100%) |
| `run_tier5_mitigation_comparison.py` | รัน before/after comparison บนแกน loss |

## สถานะการรัน

✅ รันเสร็จแล้ว — 220×3=660/660 trials, 0 ไฟล์เสีย

**หมายเหตุ code:** field `mitigation` ใน `multi_agent.py` ถูกคำนวณแต่ไม่ถูกบันทึกลง JSON log จริง (`logger.log_outcome()` ไม่รับพารามิเตอร์นี้) — ไม่กระทบผลการวิเคราะห์เพราะแยกโฟลเดอร์ต่อเงื่อนไขอยู่แล้วและ field `phase` ระบุเงื่อนไขถูกต้อง 100%

ผลการวิเคราะห์แบบละเอียด (adaptive_timeout ปิด loss cliff ได้มีนัยสำคัญ, context_cache ไม่มีนัยสำคัญพร้อมคำอธิบายกลไก, trade-off ด้านเวลา) พร้อมสถิติและการตีความเต็มรูปแบบ รวมไว้ใน
`Paper/NetImpact.md/Current/NetImpact_05_Tier5_Mitigation.md` แล้ว — ไฟล์นี้เก็บไว้เฉพาะวิธีรันโค้ดและสถานะการรันเท่านั้น
กราฟดิบอยู่ที่ `Analysis_เบื้องต้น/charts/tier5/`
