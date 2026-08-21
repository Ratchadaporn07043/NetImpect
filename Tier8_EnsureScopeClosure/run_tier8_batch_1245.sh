#!/usr/bin/env bash
# ============================================================================
# run_tier8_batch_1245.sh — รันข้อ 5, 2, 4, 1 ต่อกันในรวดเดียว (ไม่รวมข้อ 3)
# ============================================================================
# ข้อ 3 (randomized mitigation, 660 trials, หลายวัน) แยกไว้ต่างหากโดยเจตนา —
# รันเองทีหลังถ้าเวลาเพียงพอ ด้วย:
#   ./run_tier8_randomized_mitigation.py --resume
#
# ลำดับในสคริปต์นี้คือ 5 -> 2 -> 4 -> 1 (เร็ว/ปลอดภัยที่สุดก่อน ตาม README)
# ไม่ใช่ 1 -> 2 -> 4 -> 5 ตามที่พิมพ์ไว้ในคำถาม — สลับลำดับได้เองถ้าต้องการ
# โดยย้ายบล็อกด้านล่างสลับกัน (แต่ละบล็อกเป็นอิสระจากกันเต็มที่ ไม่มีผลข้างเคียง
# ข้ามกัน สลับได้อย่างปลอดภัย)
#
# ทุกสคริปต์ resume ได้ผ่าน checkpoint ของตัวเอง (logs_tier8_*/​_checkpoint/) ดังนั้น
# ถ้าเครื่องดับ/สคริปต์ถูก kill กลางทาง รันสคริปต์นี้ซ้ำได้เลย ขั้นที่เสร็จแล้ว
# จะข้ามอย่างรวดเร็ว (ไม่รันซ้ำ trial ที่เสร็จแล้ว) แล้วไปต่อจากจุดที่ค้างจริง
#
# set -e: ถ้าขั้นไหนจบด้วย exit code != 0 (เช่น self-test ของ logger พังใน
# ข้อ 2, หรือ probe_ingress_support() ไม่ผ่านในข้อ 4) สคริปต์หยุดทันที ไม่ไป
# ต่อขั้นถัดไปทับปัญหาที่ยังไม่ได้แก้
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")"

LOG_FILE="batch_1245_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

BATCH_START=$SECONDS

_section() {
    echo ""
    echo "================================================================"
    echo "  $1   ($(date '+%Y-%m-%d %H:%M:%S'))"
    echo "================================================================"
}

_section "[0/4] offline test suite ก่อนแตะอะไรจริง (ต้องผ่านทั้งหมดก่อนเสมอ)"
python3 -m pytest tests_tier8/ -q

_section "[1/4] ข้อ 5 — jitter floor (20 trials, เร็วที่สุด <1 ชม.)"
python3 run_tier8_jitter_floor.py --resume

_section "[2/4] ข้อ 2 — fixed-timeout (180 trials รวม reference arms, ~27 ชม.)"
# เอา --include-reference-arms ออกถ้าต้องการแค่ 60 trials / ~9 ชม. (arm เดียว)
python3 run_tier8_fixed_timeout.py --resume --include-reference-arms

_section "[3/4] ข้อ 4 — ingress (80 trials, ~8 ชม.)"
echo "ตรวจสอบก่อนว่ารัน 'sudo modprobe ifb numifbs=0' บน HOST (นอก container) แล้ว"
echo "ถ้ายังไม่ได้รัน ให้ Ctrl+C ตอนนี้ ไปรันบน host ก่อน แล้วค่อยรันสคริปต์นี้ใหม่"
sleep 5
python3 run_tier8_ingress.py --probe-only
python3 run_tier8_ingress.py --resume

_section "[4/4] ข้อ 1 — achieved-path (80 trials, ~2-3 ชม.)"
python3 run_tier8_achieved_path.py --resume

BATCH_ELAPSED=$((SECONDS - BATCH_START))
_section "เสร็จข้อ 5, 2, 4, 1 ครบแล้ว — ใช้เวลารวม $((BATCH_ELAPSED / 3600)) ชม. $(((BATCH_ELAPSED % 3600) / 60)) นาที"

echo ""
echo "ถ้าเวลาเพียงพอ รันข้อ 3 ต่อ (660 trials, หลายวัน) ด้วย:"
echo "  python3 run_tier8_randomized_mitigation.py --resume"
echo ""
echo "log ของ batch นี้ทั้งหมดถูกบันทึกไว้ที่: $LOG_FILE"
