# Tier 8 - Scope Closure in a Fresh Environment

This folder is self-contained and does not modify the original root files. It was created to run corrected follow-up experiments on another machine without affecting the original 5,300 trials or leaving changes elsewhere.

## Gaps Covered

| Item | Gap | Main file |
|---|---|---|
| 1 | Achieved-path measurement | `run_tier8_achieved_path.py` |
| 2 | Fixed-long-timeout arm | `run_tier8_fixed_timeout.py` |
| 3 | Randomized mitigation ordering | `run_tier8_randomized_mitigation.py` |
| 4 | Bidirectional ingress and egress shaping through IFB | `run_tier8_ingress.py` |
| 5 | Jitter-floor matched control | `run_tier8_jitter_floor.py` |

## Folder Contents and Status

- `logger.py`, `controller.py`, `multi_agent.py`, and `checkpoint_utils.py` are Tier8-local implementations.
- `run_tier8_*.py` contains the five experiment runners.
- `tests_tier8/` contains the offline pytest suite.
- `results_completed/` contains the completed results from the five main items.
- `thinking_off_diagnostic/` contains the 80 diagnostic trials and the native Ollama client used to disable thinking mode.

All five main items and the diagnostic work have completed. The diagnostic runs showed that thinking mode was not the cause of the ceiling effect: disabling it did not materially change completion. The later environment was approximately twice as fast overall, which changed exposure to packet loss and motivated Tier9.

## Why Tier8 Is Separate

The original root `logger.py` did not accept `agent` in `log_error`, `log_retry`, or `log_timeout`, even though Tier7 documentation said that it did. The original root `experiment/controller.py` also lacked `direction`, `ifb_dev`, and `probe_ingress_support()`. Tier8 therefore keeps local copies of the logger, controller, and multi-agent implementation and tests them in isolation.

The Tier8 modules continue to import the verified root task, evaluator, and scenario definitions where appropriate.

## Environment

Run this tier on an Ubuntu VM when possible. `tc`, `ip`, IFB, and ingress shaping depend on the Linux kernel. Docker Desktop on macOS adds another virtual-machine layer that may affect IFB behavior. The existing Dockerfile and compose configuration can be reused on Ubuntu.

The host must provide Ollama and the required model. The container must have `NET_ADMIN`, `iproute2`, and access to the Ollama endpoint.

## Offline Validation

Run the offline tests before touching Ollama, GPU, or `tc`:

```bash
python3 -m pytest Tier8_EnsureScopeClosure/tests_tier8/ -v
```

The tests cover achieved-path parsing, ingress preflight checks, egress backward compatibility, agent attribution, mitigation dispatch, runner imports, and the Tier8 logger contract.

## Main Runners

```bash
python3 "Tier8_EnsureScopeClosure/run_tier8_achieved_path.py" --dry-run
python3 "Tier8_EnsureScopeClosure/run_tier8_fixed_timeout.py" --dry-run
python3 "Tier8_EnsureScopeClosure/run_tier8_randomized_mitigation.py" --dry-run
python3 "Tier8_EnsureScopeClosure/run_tier8_ingress.py" --dry-run
python3 "Tier8_EnsureScopeClosure/run_tier8_jitter_floor.py" --dry-run
```

Use `--resume` for interrupted runs. Keep each result directory separate and do not overwrite `results_completed/` unless intentionally rerunning an item.

## Results

Tier8 completed more than 1,100 trials across the five scope items and diagnostic work. It verified achieved-path instrumentation, fixed-timeout behavior, randomized mitigation ordering, bidirectional shaping support, and jitter-floor control. The later environment no longer showed the original 75% loss failure, so Tier9 searched for a new critical threshold.
