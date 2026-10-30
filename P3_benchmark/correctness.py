"""Run the CORE round-trip and negative-input checks and save a report.

Run from the challenge-kit root, usually through run_on_platform.py:
    python common/run_on_platform.py --platform A -- python P3_benchmark/correctness.py --platform A
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = ROOT / "results"
sys.path.insert(0, str(HERE))
import bench  # noqa: E402


FIELDS = [
    "platform", "algorithm", "correctness_trials", "passed_trials", "overall_status",
    "roundtrip_or_valid_signature", "tampered_ciphertext", "tampered_message",
    "tampered_signature", "special_case",
]


def run(platform):
    os.environ["QFF_PLATFORM"] = platform
    RESULTS.mkdir(parents=True, exist_ok=True)
    rows = []
    all_passed = True
    for algorithm, (correctness_fn, _) in bench.ALGORITHMS.items():
        trials = bench.correctness_trials(algorithm)
        try:
            passed, total, checks = correctness_fn(n=trials, details=True)
        except Exception as exc:
            passed, total = 0, trials
            checks = {"roundtrip_or_valid_signature": False}
            print(f"[{platform}] {algorithm}: check raised {type(exc).__name__}: {exc}")
        status = "PASS" if passed == total else "FAIL"
        status = "PASS" if status == "PASS" and all(v for k, v in checks.items() if k != "special_case") else "FAIL"
        all_passed = all_passed and status == "PASS"
        is_kem = algorithm in {"ML-KEM-768", "RSA-2048-OAEP", "ECDH-P256"}
        is_rsa_oaep = algorithm == "RSA-2048-OAEP"
        rows.append({
            "platform": platform,
            "algorithm": algorithm,
            "correctness_trials": total,
            "passed_trials": passed,
            "overall_status": status,
            "roundtrip_or_valid_signature": "PASS" if checks["roundtrip_or_valid_signature"] else "FAIL",
            "tampered_ciphertext": ("PASS" if checks.get("tampered_ciphertext") else "FAIL") if is_kem else "N/A",
            "tampered_message": ("PASS" if checks.get("tampered_message") else "FAIL") if not is_kem else "N/A",
            "tampered_signature": ("PASS" if checks.get("tampered_signature") else "FAIL") if not is_kem else "N/A",
            "special_case": checks.get("special_case", "") if is_rsa_oaep else "",
        })
        print(f"[{platform}] {algorithm}: {passed}/{total} {status}")

    csv_path = RESULTS / "correctness_report.csv"
    json_path = RESULTS / "correctness_report.json"
    previous = []
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as f:
            previous = list(csv.DictReader(f))
    combined = previous + rows
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(combined)
    json_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print(f"Correctness reports -> {csv_path} and {json_path}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("A", "B", "D"), required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.platform))

