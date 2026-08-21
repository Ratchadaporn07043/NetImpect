# Tier 7 - Scope Closure

## Status

This tier investigated three methodological gaps identified during implementation review.

- **7A - Fixed long timeout:** 60/60 trials completed, but the results are unusable because the runtime root logger did not accept the `agent` parameter. Timeout/error logging raised `TypeError` and bypassed the retry budget.
- **7B - Bidirectional shaping:** 80/80 trials completed, but the falsification check failed. The baseline completion rate was 14/20 (70%) instead of approximately 100%, so the bandwidth and delay results must not be interpreted as clean bidirectional-shaping effects.
- **7C - Agent attribution:** Historical review is complete, but the logging path must be fixed before new runs.

Detailed implementation verification is documented in `Paper/NetImpact.md/Current/NetImpact_18_Implementation_Verification_Addendum.md` and `Paper/NetImpact.md/Current/NetImpact_20_Tier7_Scope_Closure.md`.

## 7A - Fixed Long Timeout

Tier5 showed that condition-aware timeout scaling increased completion at 75% configured loss from 14/20 to 20/20 (Fisher's exact test, p=0.0202). Tier7A was designed to separate condition awareness from simply allowing more time.

The fixed arm uses a 345-second timeout for every scenario. This equals the adaptive timeout at the original critical point: `120 + int(75 * 3) = 345` seconds. The comparison covers loss levels 65%, 70%, and 75%.

### Failure Cause

The Tier7 multi-agent implementation called `logger.log_timeout(..., agent=blamed_agent)` and `logger.log_error(..., agent=blamed_agent)`, but the root `logger.py` imported at runtime did not define `agent`. The resulting `TypeError` escaped the attempt handler and produced `fatal_error`, `success=false`, and `rounds=0` without retries, even though `MAX_RETRIES=2`.

The 65/70/75% results cannot be compared directly with the Tier5 control or adaptive arms because retries worked in Tier5 but not in this run.

## 7B - Bidirectional Ingress and Egress Shaping

Earlier experiments attached qdisc to the interface root and therefore shaped egress only. Tier7B uses `direction="both"` and an IFB device to shape ingress responses as well.

The selected scenarios were:

| Scenario | Role | Observed completion | Expected |
|---|---|---:|---:|
| `t7in_baseline` | Falsification check, no impairment | 14/20 (70%) | Approximately 100% |
| `t7in_bw50` | Prior egress-only null point | 10/20 (50%) | Not applicable |
| `t7in_delay1000` | Prior egress-only null point | 7/20 (35%) | Not applicable |
| `t7in_loss75` | Positive control | 0/20 (0%) | Clearly below baseline |

Every trial recorded `impairment_direction="both"`, confirming that IFB shaping was wired into the run. However, the baseline itself failed 30% of the time and the failed trials contained real OpenAI API timeouts. This suggests IFB overhead or runtime-environment instability. Baseline reliability must be restored before the other two scenarios can be interpreted.

## 7C - Agent Attribution

The runner infers the failed agent from the latest successful transcript speaker and the round-robin order. The inferred agent is written to the error log so timeout failures can be attributed to Planner, Worker, or Reviewer.

## Required Fix Before Rerunning

Add `agent=None` support to `log_error`, `log_timeout`, and `log_retry` in the actual root `logger.py`. Run the offline tests, remove the invalid checkpoint, and then rerun the affected experiment from the beginning.

```bash
python3 -m pytest tests_extended/ -v
python3 "Tier7_ScopeClosure/run_tier7_fixed_timeout.py" --dry-run
python3 "Tier7_ScopeClosure/run_tier7_ingress.py" --probe-only
```
