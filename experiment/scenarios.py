"""
Experimental Scenarios
========================
มี 2 ชุดการทดลองหลัก:
  1. FACTORIAL_SCENARIOS + TOURNAMENT_MATCHES
     factorial 2x2x2 จำนวน 8 scenarios แล้วจับคู่ tournament พบกันหมด 28 คู่
  2. COMBINED_SCENARIOS
     จับค่า delay x packet loss x jitter แบบพบกันหมดตามระดับที่กำหนด
"""
import itertools

# ============================================================
# FACTORIAL SCENARIOS — full 2x2x2 design (Delay x Loss x Jitter)
# ============================================================
FACTOR_LEVELS = {
    "delay_ms": {"off": 0, "on": 300},
    "loss_pct": {"off": 0, "on": 5},
    "jitter_ms": {"off": 0, "on": 30},
}

# tc netem ต้องมี delay > 0 ถึงจะใส่ jitter ได้
MIN_DELAY_FOR_JITTER_MS = 50


def _netem_delay_for(delay_ms: int, jitter_ms: int) -> tuple[int, str]:
    """คืนค่า delay ที่ใช้ apply จริง พร้อม note ถ้าต้องปรับเพราะ netem constraint"""
    if delay_ms == 0 and jitter_ms > 0:
        return (
            MIN_DELAY_FOR_JITTER_MS,
            f"requested delay=0ms แต่ jitter={jitter_ms}ms ต้องใช้ delay={MIN_DELAY_FOR_JITTER_MS}ms ขั้นต่ำ เพราะ netem ต้องมี delay>0",
        )
    return delay_ms, ""


def _build_factorial_scenarios():
    """สร้าง full 2x2x2 factorial (8 combinations)"""
    scenarios = []
    factor_names = ["delay", "loss", "jitter"]

    for delay_state, loss_state, jitter_state in itertools.product(["off", "on"], repeat=3):
        states = {"delay": delay_state, "loss": loss_state, "jitter": jitter_state}

        requested_delay_ms = FACTOR_LEVELS["delay_ms"][delay_state]
        loss_pct = FACTOR_LEVELS["loss_pct"][loss_state]
        jitter_ms = FACTOR_LEVELS["jitter_ms"][jitter_state]
        delay_ms, note = _netem_delay_for(requested_delay_ms, jitter_ms)

        on_factors = [f for f in factor_names if states[f] == "on"]
        name = "factorial_" + ("_".join(on_factors) if on_factors else "baseline")

        scenarios.append({
            "name": name,
            "scenario_type": "factorial",
            "delay_ms": delay_ms,
            "requested_delay_ms": requested_delay_ms,
            "jitter_ms": jitter_ms,
            "loss_pct": loss_pct,
            "factors": states,
            "note": note,
        })

    return scenarios


# ============================================================
# COMBINED SCENARIOS — delay x packet loss x jitter พบกันหมด
# ============================================================
DELAY_LEVELS_MS = list(range(0, 1001, 50))
PACKET_LOSS_LEVELS_PCT = [0, 1, 5, 10, 15, 20, 25, 30, 40, 50, 75]
JITTER_LEVELS_MS = [0, 1, 5, 10, 15, 20, 25, 30, 50, 75]


def _format_pct(value):
    return str(value).replace(".", "p")


def _build_combined_scenarios():
    """
    สร้าง combined scenarios จากทุก combination ของ delay, packet loss, jitter
    ตามระดับที่กำหนดไว้ด้านบน
    """
    scenarios = []

    for requested_delay_ms, loss_pct, jitter_ms in itertools.product(
        DELAY_LEVELS_MS, PACKET_LOSS_LEVELS_PCT, JITTER_LEVELS_MS
    ):
        delay_ms, note = _netem_delay_for(requested_delay_ms, jitter_ms)
        name = f"combined_d{requested_delay_ms:04d}_loss{_format_pct(loss_pct)}_j{jitter_ms:03d}"

        scenarios.append({
            "name": name,
            "scenario_type": "combined",
            "delay_ms": delay_ms,
            "requested_delay_ms": requested_delay_ms,
            "jitter_ms": jitter_ms,
            "loss_pct": loss_pct,
            "combined_levels": {
                "delay_ms": requested_delay_ms,
                "loss_pct": loss_pct,
                "jitter_ms": jitter_ms,
            },
            "note": note,
        })

    return scenarios


# ============================================================
# TOURNAMENT SCHEDULE — จับคู่ factorial scenarios แบบพบกันหมด
# ============================================================
def _build_round_robin_rounds(scenarios):
    """
    จัด tournament แบบพบกันหมดด้วย circle method
    มี 8 scenarios -> 7 rounds, round ละ 4 matches, รวม 28 คู่ไม่ซ้ำ
    """
    if len(scenarios) % 2 != 0:
        raise ValueError("round-robin schedule requires an even number of scenarios")

    rotation = list(scenarios)
    rounds = []
    half = len(rotation) // 2

    for round_index in range(1, len(rotation)):
        pairs = []
        for pair_index in range(1, half + 1):
            left = rotation[pair_index - 1]
            right = rotation[-pair_index]
            pairs.append({
                "match_id": f"r{round_index:02d}_m{pair_index:02d}",
                "round_index": round_index,
                "pair_index": pair_index,
                "scenario_a": left,
                "scenario_b": right,
                "scenario_names": [left["name"], right["name"]],
            })
        rounds.append(pairs)

        rotation = [rotation[0], rotation[-1]] + rotation[1:-1]

    return rounds




# ============================================================
# THREE-DAY DESIGN — ครอบคลุมคำถามหลักภายในงบเวลาประมาณ 3 วัน
# ============================================================
def _build_main_effect_scenarios():
    """
    รันทีละปัจจัยครบทุกระดับ โดยตรึงอีก 2 ปัจจัยไว้ที่ 0
    แยกชื่อ baseline ของแต่ละแกนไว้ต่างหากเพื่อวิเคราะห์ main effect ได้ตรงแกน
    """
    scenarios = []

    for delay_ms in DELAY_LEVELS_MS:
        scenarios.append({
            "name": f"main_delay_d{delay_ms:04d}",
            "scenario_type": "main_effect",
            "main_effect_axis": "delay",
            "delay_ms": delay_ms,
            "requested_delay_ms": delay_ms,
            "jitter_ms": 0,
            "loss_pct": 0,
            "note": "",
        })

    for loss_pct in PACKET_LOSS_LEVELS_PCT:
        scenarios.append({
            "name": f"main_loss_loss{_format_pct(loss_pct)}",
            "scenario_type": "main_effect",
            "main_effect_axis": "loss",
            "delay_ms": 0,
            "requested_delay_ms": 0,
            "jitter_ms": 0,
            "loss_pct": loss_pct,
            "note": "",
        })

    for jitter_ms in JITTER_LEVELS_MS:
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
        })

    return scenarios


def _scenario_by_combined_levels(delay_ms: int, loss_pct: int, jitter_ms: int) -> dict:
    for scenario in COMBINED_SCENARIOS:
        levels = scenario["combined_levels"]
        if (
            levels["delay_ms"] == delay_ms
            and levels["loss_pct"] == loss_pct
            and levels["jitter_ms"] == jitter_ms
        ):
            return scenario
    raise KeyError(f"ไม่พบ combined scenario delay={delay_ms}, loss={loss_pct}, jitter={jitter_ms}")


def _build_three_day_combined_scenarios(target_count: int = 100):
    """
    เลือก combined scenarios แบบ deterministic stratified sample:
      - ใส่ low/mid/high grid 3x3x3 ก่อน เพื่อจับ interaction สำคัญ
      - เติมจุดที่เหลือด้วยการ sample แบบกระจายทั่ว full combined space
    """
    selected = []
    seen = set()

    anchor_delays = [0, 500, 1000]
    anchor_losses = [0, 20, 75]
    anchor_jitters = [0, 20, 75]

    for delay_ms, loss_pct, jitter_ms in itertools.product(anchor_delays, anchor_losses, anchor_jitters):
        scenario = _scenario_by_combined_levels(delay_ms, loss_pct, jitter_ms)
        selected.append(scenario)
        seen.add(scenario["name"])

    candidates = [s for s in COMBINED_SCENARIOS if s["name"] not in seen]
    remaining = max(0, target_count - len(selected))

    if remaining:
        step = (len(candidates) - 1) / max(1, remaining - 1)
        for i in range(remaining):
            idx = round(i * step)
            scenario = candidates[idx]
            if scenario["name"] not in seen:
                selected.append(scenario)
                seen.add(scenario["name"])

    # กัน rounding ทำให้ได้ไม่ครบ แม้ปกติจะไม่เกิด
    if len(selected) < target_count:
        for scenario in candidates:
            if scenario["name"] not in seen:
                selected.append(scenario)
                seen.add(scenario["name"])
                if len(selected) >= target_count:
                    break

    return selected[:target_count]


FACTORIAL_SCENARIOS = _build_factorial_scenarios()
COMBINED_SCENARIOS = _build_combined_scenarios()
MAIN_EFFECT_SCENARIOS = _build_main_effect_scenarios()
THREE_DAY_COMBINED_SCENARIOS = _build_three_day_combined_scenarios(target_count=100)
BASELINE_SCENARIO = _scenario_by_combined_levels(0, 0, 0)
TOURNAMENT_ROUNDS = _build_round_robin_rounds(FACTORIAL_SCENARIOS)
TOURNAMENT_MATCHES = [match for round_matches in TOURNAMENT_ROUNDS for match in round_matches]

# รวมไว้ให้ analyzer/utility เห็นทั้งหมด แต่ runner จะแยก tournament/main-effect/combined ชัดเจน
SCENARIOS = FACTORIAL_SCENARIOS + MAIN_EFFECT_SCENARIOS + COMBINED_SCENARIOS

# Pilot: round แรกของ tournament + combined subset เล็ก ๆ สำหรับ sanity check
PILOT_MATCHES = TOURNAMENT_ROUNDS[0]
PILOT_COMBINED_SCENARIOS = [
    s for s in COMBINED_SCENARIOS
    if s["requested_delay_ms"] in (0, 300, 1000)
    and s["loss_pct"] in (0, 10, 75)
    and s["jitter_ms"] in (0, 10, 75)
]
PILOT_REPEATS = 5

# จำนวนรอบที่ต้องทำซ้ำต่อ 1 match/scenario ใน full run
REPEATS_PER_SCENARIO = 20

# Three-day bounded design repeats
THREE_DAY_TOURNAMENT_REPEATS = 1
THREE_DAY_MAIN_EFFECT_REPEATS = 5
THREE_DAY_COMBINED_REPEATS = 1
THREE_DAY_BASELINE_REPEATS = 20


def get_scenario_by_name(name: str) -> dict:
    """ดึง scenario dict จากทุก scenario ด้วยชื่อ"""
    for scenario in SCENARIOS:
        if scenario["name"] == name:
            return scenario
    raise KeyError(f"ไม่พบ scenario ชื่อ '{name}' ใน SCENARIOS")
