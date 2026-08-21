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
  — **Tier1-9 have all finished running** (see section 6 below for the detailed status of each Tier)
- `results/`: CSV tables summarizing results at the phase/task/main-effect/combined level, exported from raw logs
  (`results_three_day_combined.csv`, `results_three_day_main_effect.csv`,
  `results_three_day_phase.csv`, `results_three_day_task.csv`)

### 5. Preliminary analysis — `Analysis_Preliminary/`
Sub-structure: `scripts/` (code run to produce results — `parse_logs.py`, `generate_charts.py`, `generate_charts_tier1.py`),
`data/` (parsed CSVs — `netimpact_master.csv`, `tier1_master.csv`), `charts/three_day/` and `charts/tier1/`
(resulting chart images) — the results-interpretation file (`findings.md`) and the folder overview (`README.md`)
have been moved and consolidated with all project documentation under `Paper/`
(see `Paper/NetImpact.md/Archive_Legacy/NetImpact_14_Analysis_Folder_Overview.md` and
`Paper/NetImpact.md/Archive_Legacy/NetImpact_15_Findings_List.md`)

### 6. Extended experiments — `Tier1_ExistingAxisRefinement/` through `Tier9_CriticalThresholdRecalibration/`
- ✅ Tier1: additional points on the existing axis (finer-grained delay/loss/jitter) — **completed**
  (320 trials, narrowed the loss degradation region from the original 50-75% down to 70-75% —
  this region is specific to the time window measured in this run, see Tier8/9)
- ✅ Tier2: new axis (bandwidth throttling, multi-round strict reviewer) — **completed**
  (272 trials, found a real network effect in multi-round mode — this result is exploratory and
  did not reproduce under later controlled conditions, see Tier6)
- ✅ Tier3: infrastructure (dual LLM-judge, GPU logging) — **dual-judge portion completed**
  (200-sample, agreement very low due to judge bias — heuristic evaluation retained going forward),
  GPU logging has no new logs to review yet
- ✅ Tier4: Replication (temporal + cross-model) — **completed**
  (2,384 trials, main results reproduce across time, but the heuristic evaluator was found not to
  transfer across agent models)
- ✅ Tier5: Mitigation (adaptive timeout + context caching) — **completed**
  (660 trials, adaptive_timeout gave significantly higher completion at loss=75% for the time window
  measured — 14/20→20/20, p=0.020; context_cache was not significant — this result is specific to the
  time window measured, see Tier9 which found the opposite result at the critical point of a later time window)
- ✅ Tier6: Mitigation × Multi-Round (optional stretch) — **completed**
  (120 trials, 0 corrupted files — tested whether adaptive_timeout/context_cache can fix the multi-round
  problem at moderate_delay, which Tier2 found to be the worst case: no comparison pair reached statistical
  significance, and the falsification check failed — the no-mitigation arm at the no-impairment scenario
  itself showed a 15-20pp completion difference, meaning this design cannot separate the mitigation effect
  from between-block variance)
- ✅ Tier7: attempt to close 3 gaps (fixed-long-timeout arm, bidirectional shaping, agent attribution in logs)
  — **all 3 parts completed** (7A 60/60, 7B 80/80, 7C retrospective review of 38 events) but **7A and 7B are
  unusable** due to a logging bug / a failed falsification check, respectively — both gaps were later
  successfully closed by Tier9 (7A) and Tier8 item 4 (7B); 7C partially succeeded
- ✅ Tier8: closing 5 scope gaps + an additional 80-trial diagnostic — **fully completed**
  (1,020+80=1,100 trials — confirmed by counting actual raw log files: item1=80, item2=180
  (including reference arms), item3=660, item4=80, item5=20). Closed the following gaps, each partially
  or fully as noted: achieved-path measurement, fixed-timeout arm, randomized-order mitigation comparison,
  bidirectional (ingress+egress) shaping, and jitter delay-floor control — and made an unplanned key finding:
  **75% configured loss no longer causes completion to drop in the later-period environment** (inference is
  about 2x faster, and this was verified separately not to be caused by thinking mode)
- ✅ Tier9: locating the new critical loss threshold in the current environment + comparing mitigations at
  that point — **completed** (120 trials: 60 exploratory scan + 60 critical comparison). Found a new critical
  point at **80%** (not the original 75%), and at this point **fixed timeout performs significantly better
  than adaptive timeout scaling** (65% vs 5% completion, p<0.001) — this is the opposite ordering from the
  original Tier5 result; it does not overwrite the Tier5 result (which remains correct for the time window
  measured) but is the latest evidence for the current environment
- Each folder has its own `README.md` describing how to run it and its status/summary — detailed results for
  each Tier with full statistics are in `Paper/NetImpact.md/Current/` (see section 8 below). A quick-read
  summary of all Tier results combined (results only, no narrative) is in `Docs/NetImpact_Summary_All_Tiers.md`

### 7. Supporting documentation (images/initial draft files) — `Docs/`
- `Docs/Diagram/`: `.svg` diagrams (architecture, agent workflow, experiment design, analysis pipeline)
- `Docs/Draft_Idea/`: initial draft/idea documents (`.pdf`)
- The `.md` files that used to live here (project description, in-depth results, experiment expansion plan,
  AINTEC2026 readiness) have been moved and consolidated with all project documentation under `Paper/`
  (files 10-13)

### 8. All project documentation (centralized) — `Paper/`
Consolidates all research documentation for the project in one place, split into 2 sub-folders by status —
**files in `Archive_Legacy/` must no longer be referenced as a source for the manuscript.** All files
currently in use are exclusively in `Current/`.

- **`Paper/NetImpact.md/Current/`** — the current, highest-authority document set for the project (files
  00-09 and 16-22): `00` (table of contents/reading order), `01` (baseline + architecture), `02` (Tier1+Tier2),
  `03` (Tier3 evaluator validity), `04` (Tier4 replication), `05` (Tier5 mitigation), `06` (Tier6 — results
  are now fully in, the filename still says "Pending" to keep reference links stable, but the content is the
  actual results), `07` (paper positioning/related work/checklist), `08` (end-to-end summary across all
  Tiers), `09` (paper-writing rules — no dates/no Tier labels, narrative arc, forbidden terms such as
  "loss cliff"/"controlled"/"pre-registered", no overclaiming, etc.), `16` (figure placement/captions),
  `17` (Claim Calibration Spec — sets the allowed strength of every claim that may be written), `18`
  (Implementation Verification Addendum — **has the highest authority in this set; if it conflicts with any
  other file, defer to this one**), `19` (related work reference list), `20` (Tier7 scope closure), `21`
  (Tier8 scope closure + current-environment finding), `22` (Tier9 critical threshold recalibration)
- **`Paper/NetImpact.md/Archive_Legacy/`** — older Thai-language process/analysis documents (files 10-15)
  that have been superseded by the documents in `Current/`; kept for historical record only: `10` (AINTEC2026
  readiness — old version), `11` (detailed project explanation), `12` (in-depth results), `13` (complete
  experiment expansion plan), `14` (analysis folder overview), `15` (findings list — superseded by
  `Docs/NetImpact_Summary_All_Tiers.md`, which now covers through Tier9)
- Priority order when documents conflict: `18` > `17` > (`01`-`08`, `16`) — `09` governs writing rules
  separately (applies to all files); `20`/`21`/`22` are Tier-specific documents that have the highest
  authority within their own scope
- Tier6-9 all have complete real results — files `06`, `20`, `21`, `22`, and every place `00`/`07`/`08`
  reference Tier6-9 have been fully updated. No file in `Current/` is still written as a pending plan
  awaiting execution.

### 9. Test suite — `tests_extended/`
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