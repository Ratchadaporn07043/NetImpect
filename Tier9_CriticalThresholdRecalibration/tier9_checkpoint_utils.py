"""
Checkpoint utilities shared by the run_tier8_*.py scripts.
================================================================
Uses the Tier7_ScopeClosure format: a JSON file storing completed keys. Keeping it
centralized avoids five copies across the runners and reduces mismatch risk.
"""
import json
import os
import time


def checkpoint_path(log_dir):
    return os.path.join(log_dir, "_checkpoint", "checkpoint.json")


def load_checkpoint(log_dir):
    path = checkpoint_path(log_dir)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass
    return {"completed": {}}


def save_checkpoint(log_dir, checkpoint):
    path = checkpoint_path(log_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(checkpoint, fh, ensure_ascii=False, indent=2)


def mark_completed(log_dir, checkpoint, key, log_file):
    checkpoint.setdefault("completed", {})[key] = {
        "log_file": log_file,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    save_checkpoint(log_dir, checkpoint)


def should_skip(resume, checkpoint, key):
    return bool(resume and checkpoint is not None and key in checkpoint.get("completed", {}))
