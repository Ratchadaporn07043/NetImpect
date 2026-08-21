"""
Tier 2 — Bandwidth Axis Scenarios (แกนใหม่: bandwidth throttling)
====================================================================
โมดูลใหม่ที่เพิ่มเข้ามา — ไม่แก้ experiment/scenarios.py เลย

สำคัญ: NetworkController.apply() รองรับ `bandwidth_kbit` อยู่แล้ว (ผ่าน tc qdisc
tbf) ใน controller.py ต้นฉบับ — โค้ดฝั่ง network-apply ไม่ต้องแก้อะไรเลย
แค่ยังไม่เคยมี "scenario" ไหนส่ง bandwidth_kbit ที่ไม่ใช่ None เข้ามาใช้งานจริง
เท่านั้นเอง โมดูลนี้เติมส่วนที่ขาดไปตรงนั้น

ระดับ bandwidth ที่ทดสอบ (kbit/s):
  None (baseline ไม่จำกัด) / 2000 / 1000 / 500 / 250 / 100 / 50
  อิงจากสถานการณ์จริง: 2000kbit ≈ เน็ตมือถือ 3G ช้า, 500kbit ≈ เน็ตบ้านเก่ามาก,
  50kbit ≈ เกือบขาดการเชื่อมต่อ (ใกล้ระดับ dial-up)
"""
import sys
import os

_PROJECT_ROOT = os.environ.get("NETIMPACT_PROJECT_ROOT", os.getcwd())
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ============================================================
# Bandwidth levels (kbit/s) — ไม่รวม None (baseline ใช้ scenario เดิมที่มีอยู่แล้ว)
# ============================================================
BANDWIDTH_LEVELS_KBIT = [2000, 1000, 500, 250, 100, 50]


def build_bandwidth_main_effect_scenarios():
    """
    main-effect ของ bandwidth เพียงอย่างเดียว (delay=0, loss=0, jitter=0)
    เทียบรูปแบบเดียวกับ main_delay_*/main_loss_*/main_jitter_* เดิมทุกประการ
    เพื่อให้เอาไปรวมวิเคราะห์กับ main-effect เดิมได้ตรงแนวทาง
    """
    scenarios = []
    for bw in BANDWIDTH_LEVELS_KBIT:
        scenarios.append({
            "name": f"main_bandwidth_bw{bw:05d}",
            "scenario_type": "main_effect",
            "main_effect_axis": "bandwidth",
            "delay_ms": 0,
            "requested_delay_ms": 0,
            "jitter_ms": 0,
            "loss_pct": 0,
            "bandwidth_kbit": bw,
            "note": "",
            "tier": "tier2_bandwidth",
        })
    return scenarios


def build_bandwidth_x_loss_scenarios():
    """
    Tier2 extra: bandwidth x loss แบบง่าย (ไม่ full factorial ใหญ่ เพราะงบเวลา)
    จับคู่ bandwidth ต่ำ (ที่คาดว่ากระทบเยอะสุด) กับ loss ระดับกลาง-สูง
    เพื่อดูว่า "ช่องสัญญาณแคบ" กับ "แพ็กเก็ตหาย" ทำงานร่วมกันแบบไหน
    (เสริม babwidth axis ให้ไม่ใช่แค่ main-effect เดี่ยวๆ)
    """
    low_bandwidths = [500, 100]
    mid_high_losses = [10, 30, 50]
    scenarios = []
    for bw in low_bandwidths:
        for loss_pct in mid_high_losses:
            scenarios.append({
                "name": f"combined_bw{bw:05d}_loss{loss_pct:03d}",
                "scenario_type": "combined",
                "delay_ms": 0,
                "requested_delay_ms": 0,
                "jitter_ms": 0,
                "loss_pct": loss_pct,
                "bandwidth_kbit": bw,
                "combined_levels": {
                    "bandwidth_kbit": bw,
                    "loss_pct": loss_pct,
                },
                "note": "",
                "tier": "tier2_bandwidth_x_loss",
            })
    return scenarios


TIER2_BANDWIDTH_MAIN_EFFECT_SCENARIOS = build_bandwidth_main_effect_scenarios()
TIER2_BANDWIDTH_X_LOSS_SCENARIOS = build_bandwidth_x_loss_scenarios()

REPEATS_PER_BANDWIDTH_LEVEL = 5  # เท่ากับ THREE_DAY_MAIN_EFFECT_REPEATS เดิม
REPEATS_PER_BANDWIDTH_X_LOSS = 3  # ชุดเล็กกว่า เพราะเป็น combination เสริม ไม่ใช่แกนหลัก
