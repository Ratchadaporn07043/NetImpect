# NetImpact

Experiments on the impact of network impairment on a Multi-Agent system (Planner -> Worker -> Reviewer),
using Docker + `tc netem` to inject delay/loss/jitter and collect results as JSON logs for statistical analysis.

## What This Project Does

- Runs a multi-agent workflow on a model via Ollama (OpenAI-compatible API)
- Simulates multiple network conditions (factorial, combined, three-day bounded design)
- Collects per-trial telemetry such as success, rounds, retries, timeout, quality score, tokens, elapsed time
- Analyzes results post-run with separate phase scripts and summarized guidelines

## Project Structure (by category)

### 1. Core library (project root)
- `multi_agent.py`:
  - Defines 3 agents (Planner / Worker / Reviewer)
  - Has early termination when the Reviewer responds `APPROVED`
  - Supports retry/timeout and records message timestamps
- `logger.py`:
  - Stores trial results as JSON
  - Includes message log, error/retry/timeout, resource snapshot, and outcome

  > These two files are intentionally kept at the root, because `experiment/`, `Tier2_NewAxis/`, `Tier5_Mitigation/`,
  > `tests_extended/` import via relative path (`from multi_agent import ...`) referencing this location.
  > Do not move these files without fixing the imports in every place mentioned.

### 2. Core experiment engine — `experiment/`
- `run_experiment.py`: entry point (`--quick`, `--pilot`, `--three-day`, `--dry-run`, `--resume`)
- `scenarios.py`: factorial / tournament / combined / three-day bounded design
- `tasks.py`: benchmark task prompts + rubric for ground-truth evaluation
- `evaluator.py`: evaluates responses using heuristic / llm / both
- `evaluate_logs.py`: post-hoc evaluation for completed logs
- `analyze_pilot.py`: analyzes readiness before a full run
- `analyze_guidelines.py`: produces practical thresholds/guidelines from three-day/full results

### 3. Infrastructure
- `docker/`: Docker image + compose to run inside a container with `NET_ADMIN` privileges
  (mounts the entire project folder as `/workspace` — new Tier1-5/logs are visible automatically)
- `scripts/`: helper scripts (`test_conn.py` checks the Ollama connection, `test_netem.sh` checks `tc netem`)

### 4. Experiment result data (raw + summary)
- `logs_three_day/`: raw per-run JSON logs from the three-day experiment set (1,544 trials)
- `logs_tierN/`: raw JSON logs for each Tier — located inside that Tier's own folder, not at the root
  (e.g. `Tier1_ExistingAxisRefinement/logs_tier1/`, `Tier5_Mitigation/logs_tier5_none/`,
  `Tier8_EnsureScopeClosure/results_completed/`, `Tier9_CriticalThresholdRecalibration/logs_tier9_*`, etc.)
  — **Tier1-9 have all finished running** (see section 6 below for the summary status of each Tier)
- `results/`: CSV tables summarizing results at the phase/task/main-effect/combined level, exported from raw logs
  (`results_three_day_combined.csv`, `results_three_day_main_effect.csv`,
  `results_three_day_phase.csv`, `results_three_day_task.csv`)

### 5. Preliminary analysis — `Analysis_Preliminary/`
Sub-structure: `scripts/` (code run to produce results — `parse_logs.py`, `generate_charts.py`, `generate_charts_tier1.py`),
`data/` (parsed CSVs — `netimpact_master.csv`, `tier1_master.csv`), `charts/three_day/` and `charts/tier1/`
(resulting chart images) — the results-interpretation file (`findings.md`) and the folder overview (`README.md`)
have been moved and consolidated with all project documentation (not part of this public repository — see below).

### 6. Extended experiments — `Tier1_ExistingAxisRefinement/` through `Tier9_CriticalThresholdRecalibration/`

Each Tier folder has its own `README.md` describing how to run it and its status. A high-level, non-technical
summary of all Tiers is provided in the table below. **Full statistical detail (test statistics, effect sizes,
confidence intervals, and trial-level result decomposition) is documented in the paper manuscript and is not
part of this public repository.**

| Tier | Focus | Trials | Status | Summary |
|---|---|---|---|---|
| **Tier1** | Finer-grained points on the existing delay/loss/jitter axis | 320 | ✅ Completed | Narrowed the observed loss-degradation region for the time window measured; region is time-window-specific (see Tier8/9) |
| **Tier2** | New axis: bandwidth throttling + multi-round strict reviewer | 272 | ✅ Completed | Found an exploratory network effect in multi-round mode; did not reproduce under later controlled conditions (see Tier6) |
| **Tier3** | Infrastructure: dual LLM-judge, GPU logging | 200 (dual-judge sample) | ✅ Dual-judge portion completed | Judge agreement too low to use; heuristic evaluation retained; GPU logging has no new logs to review yet |
| **Tier4** | Replication: temporal + cross-model | 2,384 | ✅ Completed | Main results reproduce across time; heuristic evaluator does not transfer across agent models |
| **Tier5** | Mitigation: adaptive timeout + context caching | 660 | ✅ Completed | Adaptive timeout improved completion at the measured critical loss point for that time window; context caching not effective; result is time-window-specific (see Tier9) |
| **Tier6** | Mitigation × Multi-Round (optional stretch) | 120 | ✅ Completed | No mitigation pair reached significance; design could not separate the mitigation effect from between-block variance |
| **Tier7** | Closing 3 scope gaps (fixed-long-timeout arm, bidirectional shaping, agent attribution in logs) | 60 + 80 + 38 (retrospective) | ⚠️ Partially usable | 7A and 7B unusable (logging bug / failed falsification check, respectively); both gaps later closed by Tier9 (7A) and Tier8 item 4 (7B); 7C partially succeeded |
| **Tier8** | Closing 5 scope gaps + additional diagnostic | 1,100 | ✅ Completed | Closed measurement/design gaps identified in earlier tiers; unplanned finding — the previously observed critical loss point no longer causes degradation in the later-period environment |
| **Tier9** | Recalibrating the critical loss threshold for the current environment | 120 | ✅ Completed | Found a new, higher critical loss point; fixed timeout outperforms adaptive timeout scaling at this new point — the opposite ordering from the original Tier5 result (both remain valid for their respective time windows) |

**Notes:**
- Trial counts above match the counts already used elsewhere in this README.
- "Time-window-specific" findings mean the same experiment run at a different point in time may show different
  results, since the underlying infrastructure/models were observed to change performance characteristics
  between tiers.
- Statistical methodology used across tiers includes ANOVA, Kruskal-Wallis, Fisher's exact test, and effect-size
  reporting; the full results (test statistics, p-values, confidence intervals, and trial-level decomposition)
  are in the paper manuscript, not in this repository.

### 7. Supporting documentation (diagrams, drafts, detailed results) — not in this repository
Supporting materials (architecture/workflow diagrams, initial draft documents, and the consolidated project
documentation with in-depth Tier-by-Tier results) are maintained separately from this repository and are not
tracked here.

### 8. Test suite — `tests_extended/`
- pytest suite covering all of Tier1-6 (82 tests), using a `fake_autogen.py` stub so no real Ollama/GPU/tc
  is required
- Run: `python -m pytest tests_extended/ -v`

## Requirements

1. macOS/Linux capable of running Docker
2. Docker Desktop / Docker Engine
3. Ollama running on the host
4. A model available in Ollama (example: `qwen3:8b`)

## Quick Start

### 1) Start Ollama on the host

```bash
ollama serve
ollama pull qwen3:8b
```

### 2) Build and run the container

From the `docker/` folder

```bash
docker compose up -d --build
```

### 3) Enter the container

```bash
docker compose exec agent-lab bash
```

### 4) Test the model connection

```bash
python3 /workspace/scripts/test_conn.py
```

### 5) Run a quick experiment

```bash
python3 /workspace/experiment/run_experiment.py --quick
```

Logs are saved in the folder mounted on the host (e.g. `logs/` or `logs_three_day/` as configured)

## Main Run Modes

### Quick sanity

```bash
python3 experiment/run_experiment.py --quick
```

### Pilot

```bash
python3 experiment/run_experiment.py --pilot
```

### Three-day bounded design

```bash
python3 experiment/run_experiment.py --three-day --log-dir logs_three_day
```

### Dry run (no actual execution)

```bash
python3 experiment/run_experiment.py --three-day --dry-run
```

### Resume from checkpoint

```bash
python3 experiment/run_experiment.py --three-day --resume --log-dir logs_three_day
```

### Select a specific phase only

```bash
python3 experiment/run_experiment.py --tournament-only
python3 experiment/run_experiment.py --combined-only
```

## Analyzing Results

### Pilot readiness

```bash
python3 experiment/analyze_pilot.py --log-dir logs
```

### Guidelines from three-day/full

```bash
python3 experiment/analyze_guidelines.py --log-dir logs_three_day
python3 experiment/analyze_guidelines.py --log-dir logs_three_day --csv guideline_summary.csv
```

### Post-hoc ground-truth evaluation

```bash
python3 experiment/evaluate_logs.py --log-dir logs_three_day --mode llm --sample 200
python3 experiment/evaluate_logs.py --log-dir logs_three_day --mode both --all
```

## Important Environment Variables

- `OLLAMA_BASE_URL` (default `http://host.docker.internal:11434/v1`)
- `MODEL_NAME` (default `qwen3:8b`)
- `MAX_ROUNDS` (default `6`)
- `MAX_RETRIES` (default `2`)
- `LLM_TIMEOUT` (default `120` seconds)
- `ENABLE_GROUND_TRUTH_EVAL` (`1/0`, default `1`)
- `GROUND_TRUTH_EVAL_MODE` (`heuristic|llm|both`, default `heuristic`)

Example:

```bash
MODEL_NAME=qwen3:8b MAX_ROUNDS=8 MAX_RETRIES=3 LLM_TIMEOUT=180 \
python3 experiment/run_experiment.py --pilot
```

## Caveats

- Requires `NET_ADMIN` privileges in the container, otherwise `tc netem` will not work
- `jitter > 0` without delay will be adjusted to a minimum delay per the logic in `scenarios.py`
- If `host.docker.internal` does not work, check Docker Desktop and the `extra_hosts` setting
- A full combined run has a very large number of trials — start with `--pilot` or `--three-day` first

## Output Files

- One JSON file is produced per trial
- Key fields within `outcome` include:
  - `success`, `rounds`, `reviewer_rejections`
  - `elapsed_seconds`, `total_tokens`
  - `quality_score`, `ground_truth_score`, `ground_truth_passed`
  - `retry_count`, `timeout_count`, `total_error_count`

## Recommended Safe Workflow

1. `--quick` to check the system
2. `--pilot` to check variance/crashes/parse rate
3. `--three-day` with `--resume`
4. `analyze_guidelines.py` to summarize thresholds
5. `evaluate_logs.py` to add post-hoc ground-truth evaluation where needed