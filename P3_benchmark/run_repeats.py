"""Run correctness once and repeat the full benchmark, archiving each CSV.

Examples from the kit root:
    python P3_benchmark/run_repeats.py --platform A --repeats 3 --clear-log
    python P3_benchmark/run_repeats.py --platform B --repeats 3
"""
import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RUNNER = ROOT / "common" / "run_on_platform.py"
BENCH = Path(__file__).resolve().with_name("bench.py")
CORRECTNESS = Path(__file__).resolve().with_name("correctness.py")
KIT_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PARENT_PYTHON = ROOT.parent / ".venv" / "Scripts" / "python.exe"
PYTHON = KIT_PYTHON if KIT_PYTHON.exists() else (PARENT_PYTHON if PARENT_PYTHON.exists() else Path(sys.executable))
FIELDS = [
    "platform", "algorithm", "correctness_trials", "passed_trials", "overall_status",
    "roundtrip_or_valid_signature", "tampered_ciphertext", "tampered_message",
    "tampered_signature", "special_case",
]


def reset_log():
    log = ROOT / "platform_runs.jsonl"
    if log.exists() and log.stat().st_size:
        archive = RESULTS / "archive"
        archive.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(log, archive / f"platform_runs_before_final_{stamp}.jsonl")
    log.write_text("", encoding="utf-8")


def invoke(platform, target, args=()):
    command = [str(PYTHON), str(RUNNER), "--platform", platform, "--", str(PYTHON), str(target), *args]
    return subprocess.run(command, cwd=ROOT).returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("A", "B", "D"), required=True)
    parser.add_argument("--repeats", type=int, choices=range(3, 6), default=3)
    parser.add_argument("--clear-log", action="store_true",
                        help="archive old runner history and start a final-run-only log")
    args = parser.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.clear_log:
        reset_log()

    # On the final A run archive prior CSVs; then put only final repetitions in
    # the canonical root results folder. Platform B starts at the next number.
    repeat_dir = RESULTS / "repeats"
    repeat_dir.mkdir(parents=True, exist_ok=True)
    if not args.clear_log:
        archive = RESULTS / "archive"
        archive.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        correctness_csv_old = RESULTS / "correctness_report.csv"
        correctness_json_old = RESULTS / "correctness_report.json"
        if correctness_csv_old.exists():
            shutil.copy2(correctness_csv_old, archive / f"correctness_report_before_{args.platform}_{stamp}.csv")
        if correctness_json_old.exists():
            shutil.copy2(correctness_json_old, archive / f"correctness_report_before_{args.platform}_{stamp}.json")
    if args.clear_log:
        archive = RESULTS / "archive"
        archive.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for path in list(repeat_dir.glob("bench_platform_*_run_*.csv")) + list(RESULTS.glob("bench_platform_*_run_*.csv")):
            shutil.copy2(path, archive / f"{path.stem}_{stamp}{path.suffix}")
        for platform in ("A", "B"):
            source = RESULTS / f"bench_platform_{platform}.csv"
            if source.exists():
                shutil.copy2(source, archive / f"{source.stem}_{stamp}{source.suffix}")
                source.unlink()
        for name in ("comparison_A_vs_B.csv", "sizes.csv", "correctness_report.csv", "correctness_report.json"):
            source = RESULTS / name
            if source.exists():
                shutil.copy2(source, archive / f"{source.stem}_{stamp}{source.suffix}")
                source.unlink()
        charts = RESULTS / "charts"
        if charts.exists():
            for chart in charts.glob("*.png"):
                shutil.copy2(chart, archive / f"{chart.stem}_{stamp}{chart.suffix}")
    correctness_csv = RESULTS / "correctness_report.csv"
    correctness_json = RESULTS / "correctness_report.json"
    print(f"Running correctness checks on Platform {args.platform}...")
    if invoke(args.platform, CORRECTNESS, ("--platform", args.platform)) != 0:
        raise SystemExit("Correctness checks failed; benchmark repetitions were not started.")

    if correctness_csv.exists():
        with correctness_csv.open(newline="", encoding="utf-8") as f:
            all_rows = list(csv.DictReader(f))
        by_key = {(r["platform"], r["algorithm"]): r for r in all_rows}
        with correctness_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(by_key.values())
        correctness_json.write_text(json.dumps(list(by_key.values()), indent=2), encoding="utf-8")

    final_csv = RESULTS / f"bench_platform_{args.platform}.csv"
    existing = sorted(repeat_dir.glob(f"bench_platform_{args.platform}_run_*.csv"))
    existing += sorted(RESULTS.glob(f"bench_platform_{args.platform}_run_*.csv"))
    start_number = 1 if args.clear_log else len(existing) + 1
    for run_number in range(start_number, start_number + args.repeats):
        print(f"Starting Platform {args.platform} benchmark repetition {run_number}/{args.repeats}...")
        if invoke(args.platform, BENCH, ("--platform", args.platform)) != 0:
            raise SystemExit(f"Platform {args.platform} run {run_number} failed; inspect its output and run log.")
        saved = repeat_dir / f"bench_platform_{args.platform}_run_{run_number:02d}.csv"
        shutil.copy2(final_csv, saved)
        print(f"Saved repetition {run_number}: {saved}")
    print(f"Platform {args.platform} completed {args.repeats} successful repetitions.")


if __name__ == "__main__":
    main()

