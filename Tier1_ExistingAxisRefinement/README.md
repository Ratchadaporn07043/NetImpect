# Tier 1 - Existing-Axis Refinement

**Goal:** Fill gaps in the existing delay/loss/jitter axes without modifying any original code. This is an additive, low-risk extension.

**Estimated time:** Based on the verified `--dry-run` plan, 320 trials require approximately 13.0 hours using the original pilot average.

## Contents

| File | Purpose |
|---|---|
| `tier1_scenarios.py` | Defines four new scenario groups (B.1-B.4) using helpers from `experiment/scenarios.py`. |
| `run_tier1.py` | Runs trials using the original `run_single_trial` and checkpoint functions. |

## Additional Experiments

1. **B.1 Loss cliff fine-graining** - loss = 55, 60, 65, 70% to locate the threshold more precisely.
2. **B.2 Delay=250ms re-verification** - add 15 repeats, for 20 total, because the earlier p-value was borderline.
3. **B.3 Extended delay** - 1,200/1,500/2,000/2,500/3,000 ms to identify saturation.
4. **B.4 Extended jitter** - 100/125/150/200 ms to test high jitter without base delay.

## Usage

```bash
# Place this folder inside the NetImpact project root, alongside multi_agent.py and experiment/.
cd NetImpact

# Check the plan without running trials.
python3 "Tier1_ExistingAxisRefinement/run_tier1.py" --dry-run

# Run each part separately; --resume supports container restarts.
python3 "Tier1_ExistingAxisRefinement/run_tier1.py" --part loss_cliff --resume
python3 "Tier1_ExistingAxisRefinement/run_tier1.py" --part delay_extended --resume
python3 "Tier1_ExistingAxisRefinement/run_tier1.py" --part jitter_extended --resume
python3 "Tier1_ExistingAxisRefinement/run_tier1.py" --part delay_recheck --resume

# Or run all parts at once.
python3 "Tier1_ExistingAxisRefinement/run_tier1.py" --part all --resume
```

Results are written to `logs_tier1/` in the same JSON format as `logs_three_day/`, so the existing `parse_logs.py` can process them. Checkpoints are stored in `logs_tier1/_checkpoint/checkpoint.json`.

## Safety

- It does not modify the core experiment modules.
- `run_tier1.py` imports the existing trial and checkpoint functions and applies them to its own scenario list.
- Logs use a separate `logs_tier1/` directory and cannot overwrite the original checkpoints or data.

## Status

✅ Completed - 320/320 trials, 0 corrupted files.

Detailed analysis of the narrower 70-75% loss degradation region, the 250 ms delay result, and the high-delay/jitter null results is available in
`Paper/NetImpact.md/Current/NetImpact_02_Tier1_Tier2_Measurement_Axes.md`. The 70-75% region is specific to this measurement period; Tier8 §6/Tier9 found a later critical point at 80%.
Raw charts are in `Analysis_Preliminary/charts/tier1/`.
