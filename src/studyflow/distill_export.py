"""
distill_export.py — Convert recorded teacher completions into MLX-ready
train/valid JSONL splits for LoRA fine-tuning.

Reads distillation_data/records.jsonl (written by core/distillation.py
during pipeline runs with distill=True) and writes:
    distillation_data/train.jsonl
    distillation_data/valid.jsonl

in the chat-message format mlx_lm.lora expects:
    {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}

Usage:
    python distill_export.py
    python distill_export.py --valid-fraction 0.1 --min-examples 50
"""

import argparse
import json
import random
from pathlib import Path


def load_records(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def to_chat_example(record: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": record["system"]},
            {"role": "user", "content": record["prompt"]},
            {"role": "assistant", "content": json.dumps(record["response"], ensure_ascii=False)},
        ]
    }


def export(dataset_dir: Path, valid_fraction: float = 0.1, min_examples: int = 20, seed: int = 42) -> None:
    records_path = dataset_dir / "records.jsonl"
    records = load_records(records_path)

    if len(records) < min_examples:
        print(
            f"Only {len(records)} recorded examples found in {records_path} "
            f"(minimum recommended: {min_examples}).\n"
            f"Run more pipeline executions with distill=True and a strong teacher "
            f"model (e.g. model='llama3.1:8b') before fine-tuning — more diverse "
            f"real study material gives a better student model."
        )
        if len(records) == 0:
            return

    # Report per-task counts so it's obvious if one task type dominates.
    by_task: dict[str, int] = {}
    for r in records:
        by_task[r["task"]] = by_task.get(r["task"], 0) + 1
    print("Examples per task:")
    for task, n in sorted(by_task.items()):
        print(f"  {task}: {n}")

    random.seed(seed)
    shuffled = records[:]
    random.shuffle(shuffled)
    n_valid = max(1, int(len(shuffled) * valid_fraction)) if len(shuffled) >= 10 else 0
    valid_records = shuffled[:n_valid]
    train_records = shuffled[n_valid:]

    train_path = dataset_dir / "train.jsonl"
    valid_path = dataset_dir / "valid.jsonl"

    with train_path.open("w", encoding="utf-8") as f:
        for r in train_records:
            f.write(json.dumps(to_chat_example(r), ensure_ascii=False) + "\n")

    with valid_path.open("w", encoding="utf-8") as f:
        for r in valid_records:
            f.write(json.dumps(to_chat_example(r), ensure_ascii=False) + "\n")

    print(f"\nWrote {len(train_records)} train examples -> {train_path}")
    print(f"Wrote {len(valid_records)} valid examples -> {valid_path}")
    print("\nNext: see DISTILLATION.md for the mlx_lm.lora fine-tuning command.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset-dir", default="distillation_data")
    parser.add_argument("--valid-fraction", type=float, default=0.1)
    parser.add_argument("--min-examples", type=int, default=20)
    args = parser.parse_args()

    export(Path(args.dataset_dir), args.valid_fraction, args.min_examples)