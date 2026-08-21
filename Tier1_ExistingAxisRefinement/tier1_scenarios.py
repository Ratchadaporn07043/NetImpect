"""
Tier 1 - Extended Scenarios (targeted refinement of existing axes)
==========================================================
This is a new module and does not modify experiment/scenarios.py, so existing
logs_three_day/ data and checkpoints are unaffected.

Coverage:
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

# Resolve the project root containing experiment/ and add it to sys.path.
# This module may live outside the project root when NETIMPACT_PROJECT_ROOT is set.
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
    """Build a main-effect loss scenario for each new level."""
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
    """Build the original main_delay_d0250 scenario with non-conflicting run indexes."""
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


DELAY_250_RECHECK_START_RUN_INDEX = 6  # Runs 1-5 already exist in logs_three_day.
DELAY_250_RECHECK_REPEATS = 15  # 20 total repeats: 5 original plus 15 new.


# ============================================================
# B.3 - Extend delay through 3000ms.
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
# B.4 - Extend jitter through 200ms.
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
# Combine all Tier1 scenarios.
# ============================================================
TIER1_LOSS_CLIFF_SCENARIOS = build_loss_cliff_scenarios()
TIER1_DELAY_EXTENDED_SCENARIOS = build_delay_extended_scenarios()
TIER1_JITTER_EXTENDED_SCENARIOS = build_jitter_extended_scenarios()
TIER1_DELAY_250_RECHECK_SCENARIO = build_delay_250_recheck_scenario()

TIER1_ALL_NEW_LEVEL_SCENARIOS = (
    TIER1_LOSS_CLIFF_SCENARIOS + TIER1_DELAY_EXTENDED_SCENARIOS + TIER1_JITTER_EXTENDED_SCENARIOS
)

REPEATS_PER_NEW_LEVEL = 5  # Match THREE_DAY_MAIN_EFFECT_REPEATS for direct comparison.
TASKS_COUNT = 4  # coding_task, research_summary, data_analysis, planning_decision
