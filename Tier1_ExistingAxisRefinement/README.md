# Tier 1 — เจาะจุดในแกนที่มีอยู่แล้ว

**เป้าหมาย:** เติมช่องว่างในแกน delay/loss/jitter ที่ทดลองอยู่แล้ว โดย**ไม่แก้โค้ดต้นฉบับเลยแม้แต่บรรทัดเดียว** — ปลอดภัยที่สุด, เสี่ยงพังงานเดิม = 0%

**เวลาโดยประมาณ:** (ยืนยันด้วย `--dry-run` จริง) loss_cliff 4 levels×4 tasks×5 repeats=80 + delay_extended 5×4×5=100 + jitter_extended 4×4×5=80 + delay_recheck 1×4×15=60 รวม **320 trials** ≈ 320 × 145.8s ≈ **13.0 ชั่วโมง** (ใช้ค่าเฉลี่ยเดิมจาก pilot)

## มีอะไรในนี้

| ไฟล์ | หน้าที่ |
|---|---|
| `tier1_scenarios.py` | นิยาม scenario ใหม่ 4 กลุ่ม (B.1–B.4) โดย import helper จาก `experiment/scenarios.py` เดิม |
| `run_tier1.py` | สคริปต์รันจริง ใช้ `run_single_trial`/checkpoint จาก `experiment/run_experiment.py` เดิมตรงๆ |

## สิ่งที่ทดลองเพิ่ม

1. **B.1 Loss cliff fine-graining** — loss = 55, 60, 65, 70% (เดิมกระโดดจาก 50% ไป 75%) เพื่อหาจุดพลิก (threshold) ที่แม่นขึ้น
2. **B.2 Delay=250ms re-verification** — รันซ้ำ scenario เดิมอีก 15 รอบ (รวมเป็น 20 กับของเดิม 5 รอบ) เพราะจุดนี้มี p-value ก้ำกึ่งในการวิเคราะห์เชิงลึก
3. **B.3 Delay ขยายถึง 3000ms** — 1200/1500/2000/2500/3000ms เพื่อดูว่า trend อิ่มตัว (saturate) ที่ไหน
4. **B.4 Jitter ขยายถึง 200ms** — 100/125/150/200ms เพื่อดูว่า jitter อย่างเดียว (ไม่มี base delay) มีผลชัดขึ้นไหมที่ระดับสูง

## วิธีรัน

```bash
# วางโฟลเดอร์นี้ไว้ข้างใน root ของโปรเจกต์ NetImpact (ระดับเดียวกับ multi_agent.py, experiment/)
cd NetImpact

# เช็คแผนก่อน (ไม่รันจริง)
python3 "Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py" --dry-run

# รันทีละส่วน (แนะนำ เผื่อ container ต้อง restart)
python3 "Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py" --part loss_cliff --resume
python3 "Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py" --part delay_extended --resume
python3 "Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py" --part jitter_extended --resume
python3 "Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py" --part delay_recheck --resume

# หรือรันรวดเดียวทุกส่วน
python3 "Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py" --part all --resume
```

ผลลัพธ์จะถูกเขียนไปที่ `logs_tier1/` (ไฟล์ JSON รูปแบบเดียวกับ `logs_three_day/` เป๊ะ — เอาไปรวมเข้ากับ `parse_logs.py` เดิมได้ทันที) และ checkpoint อยู่ที่ `logs_tier1/_checkpoint/checkpoint.json` รองรับ `--resume` เหมือนของเดิม

## ทำไมถึงปลอดภัย 100%

- ไม่แตะ `experiment/scenarios.py`, `experiment/run_experiment.py`, `multi_agent.py`, `logger.py`, `controller.py`, `evaluator.py`, `experiment/tasks.py` เลย
- `run_tier1.py` แค่ **import** ฟังก์ชันเดิม (`run_single_trial` ผ่าน `_run_scenario`, checkpoint functions) มาเรียกใช้กับ scenario list ของตัวเอง
- เขียน log ไปคนละโฟลเดอร์ (`logs_tier1/` ไม่ใช่ `logs_three_day/`) จึงไม่มีทางไปทับ/ชนกับ checkpoint หรือข้อมูลเดิม

## สถานะการรัน

✅ รันเสร็จแล้ว — 320/320 trials, 0 ไฟล์เสีย

ผลการวิเคราะห์แบบละเอียด (degradation region ของ loss ที่แคบลงเหลือ 70-75%, การปิดประเด็น delay=250ms, ผล null ของ delay/jitter ระดับสูง) พร้อมสถิติและการตีความเต็มรูปแบบ รวมไว้ใน
`Paper/NetImpact.md/Current/NetImpact_02_Tier1_Tier2_Measurement_Axes.md` แล้ว — ไฟล์นี้เก็บไว้เฉพาะวิธีรันโค้ดและสถานะการรันเท่านั้น (หมายเหตุ: ภูมิภาค 70-75% นี้จำเพาะกับช่วงเวลาที่วัดครั้งนี้เท่านั้น — Tier8 §6/Tier9 พบว่าช่วงเวลาหลังจุดวิกฤตย้ายไปที่ 80%)
กราฟดิบอยู่ที่ `Analysis_เบื้องต้น/charts/tier1/`
