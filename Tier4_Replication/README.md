# Tier 4 - Replication (Multi-Model + Temporal)

**Goal:** Answer two reviewer questions: does the result generalize across models, and is it stable and reproducible across time?

Neither part modifies the original files. Both are purely additive and reuse the existing code with different parameters or log directories.

## Part 1: Multi-Model Replication (`run_tier4_main_effect_only.py`)

Repeat the original delay/loss/jitter main-effect axis with another model to determine whether the observed pattern, such as the ~50-75% loss degradation region, is general or specific to Qwen3:8b.

```bash
ollama pull llama3.1:8b   # Prepare a same-size comparison model.

MODEL_NAME=llama3.1:8b python3 "Tier4_Replication/run_tier4_main_effect_only.py" --dry-run
MODEL_NAME=llama3.1:8b python3 "Tier4_Replication/run_tier4_main_effect_only.py" --resume
```

**⚠️ Set `MODEL_NAME` as an environment variable before invoking Python**, not as a `--model` flag, because `multi_agent.py` reads it once at import time.

Scenarios: 42 main-effect levels (21 delay + 11 loss + 10 jitter) x 4 tasks x 5 repeats = **840 trials per model**, approximately 34.0 hours per model. Logs are separated automatically into `logs_tier4_<model_name>/` for comparison with the original Qwen3:8b logs.

## Part 2: Temporal Full Replication (`run_tier4_temporal_replicate.sh`)

Repeat the complete three-day plan (tournament + main effect + combined + baseline, 1,544 trials) in another time window to distinguish network effects from machine, timing, or LLM-sampling noise.

```bash
bash "Tier4_Replication/run_tier4_temporal_replicate.sh" --dry-run
bash "Tier4_Replication/run_tier4_temporal_replicate.sh"
bash "Tier4_Replication/run_tier4_temporal_replicate.sh" --resume
```

Results are written to `logs_three_day_replicate2/` using the original three-day runner with only `--log-dir` changed. The run contains 1,544 trials, approximately 62.5 hours.

## Files in This Folder

| File | Purpose |
|---|---|
| `run_tier4_main_effect_only.py` | Repeats the main-effect axis with another `MODEL_NAME`. |
| `run_tier4_temporal_replicate.sh` | Repeats the complete three-day plan in another time window. |

## Status

✅ Completed - 1,544 + 840 = 2,384/2,384 trials, with 0 corrupted files.

Detailed analysis, including temporal replication of the main results and the limitation that the heuristic evaluator does not transfer across models, is available in
`Paper/NetImpact.md/Current/NetImpact_04_Tier4_Replication.md`. This README contains only code-running instructions and run status.
Raw charts are in `Analysis_Preliminary/charts/tier4/`.
