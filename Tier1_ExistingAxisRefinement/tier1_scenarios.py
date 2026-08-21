"""
Tier 1 — Extended Scenarios (เจาะจุดในแกนที่มีอยู่แล้ว)
==========================================================
โมดูลนี้เป็นไฟล์ *ใหม่* ที่เพิ่มเข้ามา — ไม่แก้ไข experiment/scenarios.py ต้นฉบับเลย
(ปลอดภัยที่สุด: ไม่กระทบ logs_three_day/ หรือ checkpoint เดิมที่มีอยู่)

ครอบคลุม:
  B.1 — Loss cliff fine-graining: เพิ่มระดับ 55/60/65/70%
  B.2 — Delay=250ms re-verification: scenario เดิมแต่เตรียม repeat เพิ่ม
  B.3 — Delay ขยายถึง 3000ms
  B.4 — Jitter ขยายถึง 200ms

ใช้งาน:
    python3 run_tier1.py --dry-run
    python3 run_tier1.py --part loss_cliff
    python3 run_tier1.py --part delay_recheck
    python3 run_tier1.py --part delay_extended
    python3 run_tier1.py --part jitter_extended
    python3 run_tier1.py --part all
"""
import sys
import os

# หา path ของ project_root (ที่มี experiment/ อยู่) แล้วเพิ่มเข้า sys.path
# วางไฟล์นี้ไว้ในโฟลเดอร์ Tier1_.../ ที่อยู่ "ข้างนอก" project_root ก็ใช้ได้
# ตราบใดที่ตั้งค่า NETIMPACT_PROJECT_ROOT ให้ชี้ไปที่ root ของโปรเจกต์ NetImpact จริง
_PROJECT_ROOT = os.environ.get("NETIMPACT_PROJECT_ROOT", os.getcwd())
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from experiment.scenarios import (  # noqa: E402
    _netem_delay_for,
    _format_pct,
)

# ============================================================
# B.1 — Loss cliff fine-graining (55, 60, 65, 70%)
# ============================================================
LOSS_CLIFF_LEVELS_PCT = [55, 60, 65, 70]


def build_loss_cliff_scenarios():
    """สร้าง main-effect scenario สำหรับ loss แต่ละระดับใหม่ (delay=0, jitter=0 คงที่ตามแบบ main-effect เดิม)"""
    scenarios = []
    for loss_pct in LOSS_CLIFF_LEVELS_PCT:
        scenarios.append({
            "name": f"main_loss_loss{_format_pct(loss_pct)}",
            "scenario_type": "main_effect",
            "main_effect_axis": "loss",
            "delay_ms": 0,
            "requested_delay_ms": 0,
            "jitter_ms": 0,
            "loss_pct": loss_pct,
            "note": "",
            "tier": "tier1_loss_cliff",
        })
    return scenarios


# ============================================================
# B.2 — Delay=250ms re-verification
# ============================================================
def build_delay_250_recheck_scenario():
    """scenario เดียวกับ main_delay_d0250 เดิมเป๊ะ (เผื่อ analysis เอาไปรวมกับของเก่าได้ตรงชื่อ)
    ใช้ run_index เริ่มที่ 6 ต่อจาก 5 repeats เดิม เพื่อไม่ให้ไฟล์ log ชื่อชนกัน"""
    return {
        "name": "main_delay_d0250",
        "scenario_type": "main_effect",
        "main_effect_axis": "delay",
        "delay_ms": 250,
        "requested_delay_ms": 250,
        "jitter_ms": 0,
        "loss_pct": 0,
        "note": "",
        "tier": "tier1_delay_recheck",
    }


DELAY_250_RECHECK_START_RUN_INDEX = 6  # เดิมมี run1-run5 อยู่แล้วใน logs_three_day
DELAY_250_RECHECK_REPEATS = 15  # รวมเป็น 20 repeats ทั้งหมด (5 เดิม + 15 ใหม่)


# ============================================================
# B.3 — Delay ขยายถึง 3000ms
# ============================================================
DELAY_EXTENDED_LEVELS_MS = [1200, 1500, 2000, 2500, 3000]


def build_delay_extended_scenarios():
    scenarios = []
    for delay_ms in DELAY_EXTENDED_LEVELS_MS:
        scenarios.append({
            "name": f"main_delay_d{delay_ms:04d}",
            "scenario_type": "main_effect",
            "main_effect_axis": "delay",
            "delay_ms": delay_ms,
            "requested_delay_ms": delay_ms,
            "jitter_ms": 0,
            "loss_pct": 0,
            "note": "",
            "tier": "tier1_delay_extended",
        })
    return scenarios


# ============================================================
# B.4 — Jitter ขยายถึง 200ms
# ============================================================
JITTER_EXTENDED_LEVELS_MS = [100, 125, 150, 200]


def build_jitter_extended_scenarios():
    scenarios = []
    for jitter_ms in JITTER_EXTENDED_LEVELS_MS:
        delay_ms, note = _netem_delay_for(0, jitter_ms)
        scenarios.append({
            "name": f"main_jitter_j{jitter_ms:03d}",
            "scenario_type": "main_effect",
            "main_effect_axis": "jitter",
            "delay_ms": delay_ms,
            "requested_delay_ms": 0,
            "jitter_ms": jitter_ms,
            "loss_pct": 0,
            "note": note,
            "tier": "tier1_jitter_extended",
        })
    return scenarios


# ============================================================
# รวมทุกอย่างของ Tier1
# ============================================================
TIER1_LOSS_CLIFF_SCENARIOS = build_loss_cliff_scenarios()
TIER1_DELAY_EXTENDED_SCENARIOS = build_delay_extended_scenarios()
TIER1_JITTER_EXTENDED_SCENARIOS = build_jitter_extended_scenarios()
TIER1_DELAY_250_RECHECK_SCENARIO = build_delay_250_recheck_scenario()

TIER1_ALL_NEW_LEVEL_SCENARIOS = (
    TIER1_LOSS_CLIFF_SCENARIOS + TIER1_DELAY_EXTENDED_SCENARIOS + TIER1_JITTER_EXTENDED_SCENARIOS
)

REPEATS_PER_NEW_LEVEL = 5  # ให้เท่ากับ main-effect เดิม (THREE_DAY_MAIN_EFFECT_REPEATS) เพื่อเทียบกันได้ตรงๆ
TASKS_COUNT = 4  # coding_task, research_summary, data_analysis, planning_decision
