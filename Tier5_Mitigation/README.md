# Tier 5 — Mitigation Strategies

**Goal:** Previous tiers measured the problems. Tier5 addresses the two identified problems and tests whether the solutions work using before/after comparisons. This strengthens the paper's contribution by proposing and validating solutions rather than only reporting problems.

## Mitigation A — Adaptive Timeout

Problem: `LLM_TIMEOUT` was fixed at 120 seconds for every scenario. High delay/loss can make each LLM call much slower, causing false timeouts and unnecessary retries.

Solution: Scale the timeout according to the scenario's delay_ms/loss_pct/jitter_ms using `_adaptive_timeout_seconds()` in `multi_agent.py`.

## Mitigation B — Context Caching

Problem: A timeout or error in the middle of a conversation retries the entire task. Planner must rebuild the plan from scratch even when the previous plan is still valid, wasting an LLM call under the same poor network conditions.

Solution: Cache Planner's first message from the first attempt. On retry, skip Planner and give the cached plan directly to Worker, removing one risky LLM call per retry.

## ⚠️ Pre-Run Steps

```bash
cd NetImpact
cp multi_agent.py multi_agent.py.backup_original   # Always create a backup, including after Tier2.
cp "Tier5_Mitigation/multi_agent.py" multi_agent.py
```

This is an **accumulated version** that already includes Tier2's `strict_reviewer`, so Tier2 and Tier5 can be used together without manual merging. `mitigation="none"` is always the default; omitting it preserves the original behavior, verified by `tests_extended/test_baseline_regression.py`.

## How to Run - Before/After Comparison

Run the original **loss main-effect axis** (11 levels: 0,1,5,10,15,20,25,30,40,50,75%) x 4 tasks x 5 repeats = **220 trials per condition**. The loss axis was selected because it showed the clearest effect. The 70-75% degradation region is specific to this measurement period; later measurements (Tier8 §6 / Tier9) found that the critical point shifted to 80%.

```bash
python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --dry-run

# Run one condition at a time (recommended):
python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition none --resume             # control baseline
python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition adaptive_timeout --resume  # Mitigation A
python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition context_cache --resume     # Mitigation B

# Or run all three conditions at once (660 trials, approximately 26.7 hours).
python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition all --resume
```

Logs are separated into `logs_tier5_none/`, `logs_tier5_adaptive_timeout/`, and `logs_tier5_context_cache/`. Compare error/timeout rate, mean LLM calls per trial, success rate, and mean ground_truth_score to determine how effective each mitigation is.

## Files in This Folder

| File | Purpose |
|---|---|
| `multi_agent.py` | **Replaces** the root version and combines Tier2 `strict_reviewer` with mitigation A/B (`default="none"` preserves original behavior). |
| `run_tier5_mitigation_comparison.py` | Runs the before/after comparison on the loss axis. |

## Run Status

✅ Completed - 220 x 3 = 660/660 trials, 0 corrupted files.

**Code note:** The `mitigation` field is calculated in `multi_agent.py` but is not written to the JSON log because `logger.log_outcome()` does not accept it. This does not affect analysis because each condition has a separate directory and the `phase` field identifies the condition correctly.

Detailed analysis, including the significant loss-cliff improvement from adaptive_timeout, the non-significant context_cache result, timing trade-offs, statistics, and interpretation, is available in
`Paper/NetImpact.md/Current/NetImpact_05_Tier5_Mitigation.md`. This README contains only code-running instructions and run status.
Raw charts are in `Analysis_Preliminary/charts/tier5/`.
