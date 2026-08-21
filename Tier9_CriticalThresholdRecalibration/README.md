# Tier 9 - Critical Threshold Recalibration

## Status

Both steps are complete: 120/120 trials, consisting of 60 exploratory-scan trials and 60 critical-comparison trials, with 0 corrupted files. Full approved wording and statistics are in `Paper/NetImpact.md/Current/NetImpact_22_Tier9_Critical_Threshold_Recalibration.md`.

## Motivation

Tier8 showed that the `mitigation="none"` control no longer failed at 75% loss in the current environment. Completion was 20/20 with thinking mode enabled and disabled, whereas the original Tier5 run produced 14/20 at the same point. Tier9 therefore locates the current critical loss threshold and compares mitigation strategies there.

## Diagnostic Findings

1. Thinking mode was initially suspected because it made Qwen3:8b calls 10-30+ times slower.
2. A custom AutoGen client using native `/api/chat` with `"think": false` produced the same 20/20 completion at 75% loss. Thinking mode was not the cause of the ceiling effect, although it affected latency.
3. Tier5 and Tier8 retry/timeout logic was identical (`MAX_RETRIES=2`, `BASE_LLM_TIMEOUT=120`). Achieved loss from qdisc counters was 75.1%, matching configured loss, so neither explained the change.
4. Among first-try successful trials, median elapsed time was almost twice as long in Tier5 (248s versus 127s in the later run; message gap 86s versus 45s). Shorter connections were less likely to encounter packet drops.
5. The earlier Tier8 loss scan covered only 0-75% and showed approximately 100% completion for `none` at every tested level. No higher-loss data existed to identify the new threshold.

**Conclusion:** Two layers of environment drift separated Tier5 from the later runs: thinking mode was enabled, and overall inference became approximately twice as fast because of software-stack changes. Tier9 therefore recalibrates the threshold instead of reusing 75%.

## Why Tier9 Is Separate

Tier8 closed five scope gaps: achieved-path measurement, fixed timeout, randomized ordering, ingress shaping, and jitter-floor control. Tier9 asks a new question: where is the critical loss threshold in the current environment?

Tier9 is standalone. `tier9_controller.py`, `tier9_logger.py`, `tier9_checkpoint_utils.py`, `tier9_tasks.py`, and `tier9_evaluator.py` are local copies or standalone variants. `multi_agent.py` uses `OllamaNativeThinkOffClient` by default rather than an external monkey patch. Thinking-off prevents a controllable mode from becoming an additional confound; it is not itself the solution to the ceiling effect.

## Environment

Use the same host/container arrangement as Tier8. Ollama runs on the host and `requests` is already included in the existing Docker requirements.

```bash
cd "AINTEC Project/docker"
docker compose exec agent-lab bash
cd /workspace/Tier9_CriticalThresholdRecalibration
```

## Validation

Run the standalone offline tests before contacting Ollama or `tc`:

```bash
python3 -m pytest Tier9_CriticalThresholdRecalibration/tests_tier9/ -v
```

The tests verify native-client registration for Planner, Worker, Reviewer, and GroupChatManager, as well as retry, timeout, agent-attribution, and mitigation behavior.

## Step 1 - Exploratory Scan

`run_tier9_exploratory_scan.py` searches loss levels above 75% with `mitigation="none"`. The default scan uses 80/85/90/95/99% with a small sample to locate a candidate threshold.

```bash
python3 "Tier9_CriticalThresholdRecalibration/run_tier9_exploratory_scan.py" --dry-run
python3 "Tier9_CriticalThresholdRecalibration/run_tier9_exploratory_scan.py" --resume
```

The exploratory result is for locating a candidate only. It is not a paper-ready estimate because the sample is small. The critical point is the first level at which completion falls to 85% or below.

## Step 2 - Critical Comparison

`run_tier9_critical_comparison.py` compares `none`, `adaptive_timeout`, and `fixed_long_timeout` at the critical loss selected in Step 1. All three arms run in one block to reduce run-block confounding.

```bash
python3 "Tier9_CriticalThresholdRecalibration/run_tier9_critical_comparison.py" --critical-loss-pct <value> --dry-run
python3 "Tier9_CriticalThresholdRecalibration/run_tier9_critical_comparison.py" --critical-loss-pct <value> --resume
```

The critical loss must come from Step 1; there is no default. The script derives `FIXED_LONG_TIMEOUT` from the adaptive formula and includes a falsification check. If the `none` arm remains above 85% completion, do not interpret the mitigation comparison; scan for a higher threshold.

## Results

The exploratory scan found a new critical point at 80% loss. At this point, fixed timeout substantially outperformed adaptive timeout: 65% versus 5% completion, p < 0.001. This is the latest evidence for the current environment and does not overwrite the earlier Tier5 result, which remains valid for its original measurement period.
