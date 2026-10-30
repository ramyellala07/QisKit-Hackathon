"""Generate the PS-P3 comparison table, charts and report from the raw CSVs.

Run from the challenge-kit root:
    python P3_benchmark/analyze.py

This script only analyzes saved results. pandas and matplotlib stay out of the
benchmark process so Platform B's memory measurement remains unaffected.
"""
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
P3 = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
FIGURES = RESULTS / "charts"
ALGORITHMS = [
    "ML-KEM-768", "RSA-2048-OAEP", "ECDH-P256",
    "ML-DSA-65", "SLH-DSA-SHA2-128s", "RSA-2048-PSS", "ECDSA-P256",
]
OPS = {
    "keygen": ALGORITHMS,
    "encapsulate": ["ML-KEM-768", "RSA-2048-OAEP", "ECDH-P256"],
    "decapsulate": ["ML-KEM-768", "RSA-2048-OAEP", "ECDH-P256"],
    "sign": ["ML-DSA-65", "SLH-DSA-SHA2-128s", "RSA-2048-PSS", "ECDSA-P256"],
    "verify": ["ML-DSA-65", "SLH-DSA-SHA2-128s", "RSA-2048-PSS", "ECDSA-P256"],
}


def load_platform(platform):
    repeat_dir = RESULTS / "repeats"
    repeat_files = sorted(repeat_dir.glob(f"bench_platform_{platform}_run_*.csv"))
    legacy_files = sorted(RESULTS.glob(f"bench_platform_{platform}_run_*.csv"))
    paths = sorted(repeat_files) or legacy_files or [RESULTS / f"bench_platform_{platform}.csv"]
    frames = [pd.read_csv(path) for path in paths]
    for path, frame in zip(paths, frames):
        if len(frame) != 21:
            raise ValueError(f"{path.name} has {len(frame)} rows; expected 21.")
        if set(frame.algorithm) != set(ALGORITHMS):
            raise ValueError(f"{path.name} is missing one or more CORE algorithms.")
        if not (frame.correct == frame.correct_total).all():
            raise ValueError(f"{path.name} includes a failed correctness check.")
        for op, algs in OPS.items():
            found = set(frame.loc[frame.operation == op, "algorithm"])
            if found != set(algs):
                raise ValueError(f"{path.name} is missing expected {op} rows.")
    repeat_count = len(frames)
    latest = frames[-1]
    if len(frames) == 1:
        summary = latest.copy()
        summary["repeat_count"] = 1
        return summary, latest, 1, 1
    reported_frames = frames[-3:]
    all_runs = pd.concat(reported_frames, ignore_index=True)
    numeric = all_runs.groupby(["algorithm", "operation"], as_index=False).agg(
        median_ms=("median_ms", "median"), iqr_ms=("iqr_ms", "median"), p95_ms=("p95_ms", "median"),
        n=("n", "sum"), warmup=("warmup", "max"), correct=("correct", "sum"),
        correct_total=("correct_total", "sum"), memory_kb=("memory_kb", "median"),
        baseline_rss_mb=("baseline_rss_mb", "median"),
    )
    latest = reported_frames[-1]
    summary = numeric.merge(latest[["algorithm", "operation", "sizes_json"]],
                            on=["algorithm", "operation"], validate="one_to_one")
    summary["repeat_count"] = len(reported_frames)
    return summary, latest, len(reported_frames), repeat_count


def load_data():
    a, a_latest, a_repeats, a_available = load_platform("A")
    b, b_latest, b_repeats, b_available = load_platform("B")
    if a_repeats != b_repeats:
        raise ValueError(f"A and B have different repeat counts ({a_repeats} vs {b_repeats}).")
    merged = a.merge(b, on=["algorithm", "operation"], suffixes=("_A", "_B"), validate="one_to_one")
    merged["B_over_A_ratio"] = merged["median_ms_B"] / merged["median_ms_A"]
    merged["A_correct_rate"] = merged["correct_A"] / merged["correct_total_A"]
    merged["B_correct_rate"] = merged["correct_B"] / merged["correct_total_B"]
    merged["repeat_count"] = a_repeats
    return a, b, merged, a_latest, b_latest, a_repeats, min(a_available, b_available)


def write_comparison(merged):
    cols = [
        "algorithm", "operation", "median_ms_A", "median_ms_B", "B_over_A_ratio",
        "warmup_A", "warmup_B", "n_A", "n_B", "repeat_count",
        "iqr_ms_A", "iqr_ms_B", "p95_ms_A", "p95_ms_B",
        "A_correct_rate", "B_correct_rate", "memory_kb_A", "memory_kb_B",
        "baseline_rss_mb_A", "baseline_rss_mb_B", "sizes_json_A", "sizes_json_B",
    ]
    out = merged[cols].copy()
    out["B_over_A_ratio"] = out["B_over_A_ratio"].round(3)
    out.to_csv(RESULTS / "comparison_A_vs_B.csv", index=False)
    return out


def write_sizes(a):
    rows = []
    expanded = {"ML-KEM-768": 2400, "ML-DSA-65": 4032}
    for alg in ALGORITHMS:
        sizes = json.loads(a.loc[a.algorithm == alg].iloc[0].sizes_json)
        rows.append({
            "algorithm": alg,
            "public_key_bytes": sizes.get("public_key"),
            "secret_key_reported_bytes": sizes.get("secret_key"),
            "secret_key_expanded_bytes": expanded.get(alg),
            "ciphertext_bytes": sizes.get("ciphertext"),
            "shared_secret_bytes": sizes.get("shared_secret"),
            "signature_bytes": sizes.get("signature"),
            "encoding": sizes.get("encoding", ""),
        })
    pd.DataFrame(rows).to_csv(RESULTS / "sizes.csv", index=False)


def write_correctness_reports(a, b):
    rows = []
    evidence_path = RESULTS / "correctness_report.csv"
    correctness_evidence = {}
    if evidence_path.exists():
        with evidence_path.open(newline="", encoding="utf-8") as f:
            correctness_evidence = {(r["platform"], r["algorithm"]): r for r in csv.DictReader(f)}
    frames = [("A", a), ("B", b)]
    d_repeats = sorted((RESULTS / "repeats").glob("bench_platform_D_run_*.csv"))
    if d_repeats:
        d, _, _, _ = load_platform("D")
        frames.append(("D", d))
    for platform, frame in frames:
        for alg in ALGORITHMS:
            row = frame.loc[frame.algorithm == alg].iloc[0]
            status = "PASS" if row.correct == row.correct_total else "FAIL"
            exact = correctness_evidence.get((platform, alg), {})
            is_kem = alg in OPS["encapsulate"]
            is_rsa_oaep = alg == "RSA-2048-OAEP"
            rows.append({
                "platform": platform,
                "algorithm": alg,
                "correctness_trials": int(row.correct_total),
                "passed_trials": int(row.correct),
                "overall_status": status,
                "roundtrip_or_valid_signature": exact.get("roundtrip_or_valid_signature", "NOT RUN"),
                "tampered_ciphertext": exact.get("tampered_ciphertext", "NOT RUN") if is_kem else "N/A",
                "tampered_message": exact.get("tampered_message", "N/A" if is_kem else "NOT RUN"),
                "tampered_signature": exact.get("tampered_signature", "N/A" if is_kem else "NOT RUN"),
                "special_case": exact.get("special_case", "") if is_rsa_oaep else "",
            })
    fields = ["platform", "algorithm", "correctness_trials", "passed_trials", "overall_status",
              "roundtrip_or_valid_signature", "tampered_ciphertext", "tampered_message",
              "tampered_signature", "special_case"]
    with (RESULTS / "correctness_report.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (RESULTS / "correctness_report.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def make_latency_chart(a, b):
    fig, axes = plt.subplots(1, 5, figsize=(19, 6.6), constrained_layout=True)
    colors = {"A": "#2864a5", "B": "#e07a32"}
    for ax, op in zip(axes, OPS):
        algs = OPS[op]
        x = np.arange(len(algs))
        width = 0.36
        for offset, platform, data in ((-width / 2, "A", a), (width / 2, "B", b)):
            vals = [float(data.loc[(data.algorithm == alg) & (data.operation == op), "median_ms"].iloc[0])
                    for alg in algs]
            ax.bar(x + offset, vals, width, label=f"Platform {platform}", color=colors[platform])
        ax.set_title(f"{op.capitalize()}\nPlatform A/B; n={int(a.loc[a.operation == op, 'n'].sum())}/{int(b.loc[b.operation == op, 'n'].sum())}")
        ax.set_yscale("log")
        ax.set_ylabel("Median latency (ms, log scale)")
        ax.set_xticks(x, algs, rotation=68, ha="right", fontsize=8)
        ax.grid(axis="y", which="both", alpha=0.2)
    axes[0].legend(fontsize=8)
    fig.suptitle("Median latency: Platform A vs B | 10 warm-ups; n=100–1000; SLH-DSA keygen/sign n=30 per run (90 total)", fontsize=14)
    fig.savefig(FIGURES / "latency_A_vs_B.png", dpi=180)
    plt.close(fig)


def make_sizes_chart(a):
    fig, axes = plt.subplots(1, 2, figsize=(15, 6), constrained_layout=True)
    groups = [
        ("KEM artifacts", ["ML-KEM-768", "RSA-2048-OAEP", "ECDH-P256"],
         [("public_key", "Public key"), ("secret_key", "Secret key"), ("ciphertext", "Ciphertext")]),
        ("Signature artifacts", ["ML-DSA-65", "SLH-DSA-SHA2-128s", "RSA-2048-PSS", "ECDSA-P256"],
         [("public_key", "Public key"), ("secret_key", "Secret key"), ("signature", "Signature")]),
    ]
    for ax, (title, algs, fields) in zip(axes, groups):
        width = 0.8 / len(fields)
        x = np.arange(len(algs))
        for j, (key, label) in enumerate(fields):
            vals = []
            for alg in algs:
                row = a.loc[a.algorithm == alg].iloc[0]
                sizes = json.loads(row.sizes_json)
                vals.append(sizes.get(key, np.nan))
            ax.bar(x + (j - (len(fields) - 1) / 2) * width, vals, width, label=label)
        if title == "KEM artifacts":
            ax.scatter([x[0]], [2400], marker="D", color="#8e44ad", s=42,
                       label="Expanded FIPS secret key")
            ax.annotate("ML-KEM-768 expanded secret key: 2,400 B\n(seed form shown: 64 B)",
                        xy=(0, 2400), xytext=(-0.35, 4200), fontsize=8,
                        arrowprops={"arrowstyle": "->", "lw": 0.8})
        else:
            ax.scatter([x[0]], [4032], marker="D", color="#8e44ad", s=42,
                       label="Expanded FIPS secret key")
            ax.annotate("ML-DSA-65 expanded secret key: 4,032 B\n(seed form shown: 32 B)",
                        xy=(0, 4032), xytext=(-0.35, 6200), fontsize=8,
                        arrowprops={"arrowstyle": "->", "lw": 0.8})
        ax.set_title(f"{title} | Platform A/B; {len(algs)} algorithms")
        ax.set_ylabel("Artifact size (bytes, log scale)")
        ax.set_yscale("log")
        ax.set_ylim(30, 10000)
        ax.set_xticks(x, algs, rotation=35, ha="right")
        ax.grid(axis="y", which="both", alpha=0.2)
        ax.legend(fontsize=8)
    fig.suptitle("Artifact sizes (bytes; A/B configurations; 3 KEM and 4 signature algorithms)", fontsize=14)
    fig.savefig(FIGURES / "artifact_sizes.png", dpi=180)
    plt.close(fig)


def make_ratio_chart(merged):
    data = merged.copy()
    data["label"] = data.algorithm + " / " + data.operation
    data = data.sort_values("B_over_A_ratio")
    fig, ax = plt.subplots(figsize=(10, 9), constrained_layout=True)
    colors = ["#4b8b62" if v < 1 else "#bd5b54" for v in data.B_over_A_ratio]
    y = np.arange(len(data))
    ax.barh(y, data.B_over_A_ratio - 1.0, left=1.0, color=colors)
    ax.axvline(1, color="#222222", linewidth=1.2, linestyle="--", label="Equal median (B/A = 1)")
    for yi, value in zip(y, data.B_over_A_ratio):
        ax.annotate(f"{value:.2f}", (value, yi), xytext=(4 if value >= 1 else -4, 0),
                    textcoords="offset points", va="center",
                    ha="left" if value >= 1 else "right", fontsize=8)
    ax.set_xscale("log")
    ax.set_xlabel("Platform B / Platform A median latency ratio (log scale)")
    ax.set_yticks(y, data.label)
    ax.set_title(f"Platform B/A medians | A vs B; n={int(data.n_A.sum())}/{int(data.n_B.sum())}, 10 warm-ups")
    ax.grid(axis="x", which="both", alpha=0.2)
    ax.legend()
    fig.savefig(FIGURES / "platform_B_over_A.png", dpi=180)
    plt.close(fig)


def make_wire_chart(a):
    kem = ["ML-KEM-768", "RSA-2048-OAEP", "ECDH-P256"]
    sigs = ["ML-DSA-65", "SLH-DSA-SHA2-128s", "RSA-2048-PSS", "ECDSA-P256"]
    fig, axes = plt.subplots(1, 2, figsize=(15, 6), constrained_layout=True)
    for ax, title, algs, second in (
        (axes[0], "KEM exchange", kem, "ciphertext"),
        (axes[1], "Signature verification material", sigs, "signature"),
    ):
        wire = []
        for alg in algs:
            sizes = json.loads(a.loc[a.algorithm == alg].iloc[0].sizes_json)
            wire.append(sizes["public_key"] + sizes[second])
        bars = ax.bar(np.arange(len(algs)), wire, color=["#3684a8" if a in {"ML-KEM-768", "ML-DSA-65", "SLH-DSA-SHA2-128s"} else "#8c8c8c" for a in algs])
        for bar, value in zip(bars, wire):
            ax.annotate(f"{value:,} B", (bar.get_x() + bar.get_width() / 2, value),
                        xytext=(0, 4), textcoords="offset points", ha="center", fontsize=8)
        ax.axhline(1024, color="#c33", linestyle="--", linewidth=1, label="1 KiB")
        ax.axhline(2048, color="#d78a18", linestyle="--", linewidth=1, label="2 KiB")
        ax.set_title(f"{title}\nPlatform A/B; {len(algs)} algorithms")
        ax.set_ylabel("Public key + ciphertext/signature (bytes)")
        ax.set_xticks(np.arange(len(algs)), algs, rotation=30, ha="right")
        ax.set_ylim(0, max(wire) * 1.2)
        ax.grid(axis="y", alpha=0.2)
        ax.legend(fontsize=8)
    fig.suptitle("Estimated bytes on wire | Platform A/B sizes; 3 KEM and 4 signature algorithms", fontsize=14)
    fig.savefig(FIGURES / "bytes_on_wire.png", dpi=180)
    plt.close(fig)


def fmt(v, digits=3):
    return f"{float(v):.{digits}f}"


def make_report(a, b, merged, available_repeats):
    info_path = ROOT / "platform_A_info.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    runs_path = ROOT / "platform_runs.jsonl"
    runs = [json.loads(line) for line in runs_path.read_text(encoding="utf-8").splitlines() if line.strip()] if runs_path.exists() else []
    latest = {}
    for record in runs:
        if record.get("platform") in ("A", "B"):
            latest.setdefault(record["platform"], []).append(record)
    latest_record = {platform: records[-1] for platform, records in latest.items() if records}
    final_logs_ok = all(records and all(r.get("status") == "ok" for r in records) for records in latest.values()) and set(latest) == {"A", "B"}
    correctness_path = RESULTS / "correctness_report.csv"
    correctness_rows = {}
    if correctness_path.exists():
        with correctness_path.open(newline="", encoding="utf-8") as f:
            correctness_rows = {(r["platform"], r["algorithm"]): r for r in csv.DictReader(f)}
    valid_correctness = (len(correctness_rows) == 14 and
                         all(r.get("overall_status") == "PASS" and
                             r.get("roundtrip_or_valid_signature") == "PASS" and
                             all(r.get(field) == "PASS" for field in
                                 (("tampered_ciphertext",) if r.get("algorithm") in OPS["encapsulate"] else ("tampered_message", "tampered_signature")))
                             for r in correctness_rows.values()))
    def tamper_summary(platform, alg):
        check = correctness_rows.get((platform, alg), {})
        if check.get("roundtrip_or_valid_signature") != "PASS":
            return "NOT RUN / NOT RECORDED"
        if alg in OPS["encapsulate"]:
            outcome = check.get("tampered_ciphertext", "NOT RUN")
            detail = check.get("special_case") or "altered ciphertext produced a different secret or was rejected"
            return f"roundtrip PASS; ciphertext {outcome} ({detail})"
        return (f"signature PASS; modified message {check.get('tampered_message', 'NOT RUN')}; "
                f"modified signature {check.get('tampered_signature', 'NOT RUN')}")

    timing_rows = []
    for _, row in merged.iterrows():
        timing_rows.append(
            f"| {row.algorithm} | {row.operation} | {int(row.warmup_A)} | {int(row.n_A)} / {int(row.n_B)} | "
            f"{fmt(row.median_ms_A, 4)} / {fmt(row.iqr_ms_A, 4)} / {fmt(row.p95_ms_A, 4)} | "
            f"{fmt(row.median_ms_B, 4)} / {fmt(row.iqr_ms_B, 4)} / {fmt(row.p95_ms_B, 4)} | "
            f"{fmt(row.B_over_A_ratio, 3)} |"
        )
    tamper_checks = {
        "ML-KEM-768": "Changed ciphertext did not reproduce the encapsulated secret",
        "RSA-2048-OAEP": "Changed ciphertext rejected by OAEP decryption",
        "ECDH-P256": "The tamper check substitutes a different ephemeral public key; the resulting shared secret differs",
        "ML-DSA-65": "Changed message and changed signature rejected",
        "SLH-DSA-SHA2-128s": "Changed message and changed signature rejected",
        "RSA-2048-PSS": "Changed message and changed signature rejected",
        "ECDSA-P256": "Changed message and changed signature rejected",
    }
    validation_rows = []
    for alg in ALGORITHMS:
        ra = a[a.algorithm == alg].iloc[0]
        rb = b[b.algorithm == alg].iloc[0]
        validation_rows.append(
            f"| {alg} | {int(ra.correct)}/{int(ra.correct_total)} | "
            f"{int(rb.correct)}/{int(rb.correct_total)} | A: {tamper_summary('A', alg)}; "
            f"B: {tamper_summary('B', alg)}. {tamper_checks[alg]} |"
        )
    alg_sizes = []
    for alg in ALGORITHMS:
        row = a.loc[a.algorithm == alg].iloc[0]
        sizes = json.loads(row.sizes_json)
        kind = "KEM" if alg in OPS["encapsulate"] else "Signature"
        fields = ["public_key", "secret_key", "ciphertext", "shared_secret"] if kind == "KEM" else ["public_key", "secret_key", "signature"]
        encoded = "; ".join(f"{name}={sizes[name]} B" for name in fields if name in sizes)
        alg_sizes.append(f"| {alg} | {kind} | {encoded} | {sizes.get('encoding', '')} |")

    kem_rows = merged[merged.algorithm == "ML-KEM-768"]
    kem_by_op = {r.operation: r for _, r in kem_rows.iterrows()}
    slh_sign = merged[(merged.algorithm == "SLH-DSA-SHA2-128s") & (merged.operation == "sign")].iloc[0]
    slh_verify = merged[(merged.algorithm == "SLH-DSA-SHA2-128s") & (merged.operation == "verify")].iloc[0]
    mldsa_sign = merged[(merged.algorithm == "ML-DSA-65") & (merged.operation == "sign")].iloc[0]
    mldsa_verify = merged[(merged.algorithm == "ML-DSA-65") & (merged.operation == "verify")].iloc[0]
    rsa_pss_sign = merged[(merged.algorithm == "RSA-2048-PSS") & (merged.operation == "sign")].iloc[0]
    ecdsa_sign = merged[(merged.algorithm == "ECDSA-P256") & (merged.operation == "sign")].iloc[0]
    ecdh_enc = merged[(merged.algorithm == "ECDH-P256") & (merged.operation == "encapsulate")].iloc[0]
    s1_a_pqc_ms = float(kem_by_op["encapsulate"].median_ms_A + mldsa_sign.median_ms_A)
    s1_a_classical_ms = float(ecdh_enc.median_ms_A + ecdsa_sign.median_ms_A)
    s1_b_pqc_ms = float(kem_by_op["encapsulate"].median_ms_B + mldsa_sign.median_ms_B)
    s1_b_classical_ms = float(ecdh_enc.median_ms_B + ecdsa_sign.median_ms_B)
    kem_sizes = json.loads(a.loc[a.algorithm == "ML-KEM-768"].iloc[0].sizes_json)
    ecdh_sizes = json.loads(a.loc[a.algorithm == "ECDH-P256"].iloc[0].sizes_json)
    mldsa_sizes = json.loads(a.loc[a.algorithm == "ML-DSA-65"].iloc[0].sizes_json)
    slh_sizes = json.loads(a.loc[a.algorithm == "SLH-DSA-SHA2-128s"].iloc[0].sizes_json)
    kem_wire_bytes = int(kem_sizes["public_key"] + kem_sizes["ciphertext"])
    ecdh_wire_bytes = int(ecdh_sizes["public_key"] + ecdh_sizes["ciphertext"])
    mldsa_verify_bytes = int(mldsa_sizes["public_key"] + mldsa_sizes["signature"])
    recommendation_rows = [
        f"| S1 — High-traffic TLS | ML-KEM-768 + ML-DSA-65 | ECDH-P256 + ECDSA-P256, only if classical security is acceptable | Crypto-only serial proxy: PQC {s1_a_pqc_ms:.3f} ms on A / {s1_b_pqc_ms:.3f} ms on B; ECDH/ECDSA {s1_a_classical_ms:.3f} / {s1_b_classical_ms:.3f} ms. PQC is about {s1_a_pqc_ms/s1_a_classical_ms:.1f}× slower here, before protocol and network overhead. |",
        f"| S2 — Bandwidth-limited IoT | ML-KEM-768 when post-quantum protection is required and fragmentation is available | ECDH-P256 when the byte cap dominates and classical security is allowed | ML-KEM public key + ciphertext: {kem_wire_bytes:,} B ({kem_wire_bytes-2048} B above 2 KiB); ECDH public key + ephemeral key: {ecdh_wire_bytes} B. ML-DSA public key + signature: {mldsa_verify_bytes:,} B. |",
        f"| S3 — Firmware signing | ML-DSA-65 | SLH-DSA-SHA2-128s when a hash-based signature is specifically preferred and storage/time allow | ML-DSA signature {mldsa_sizes['signature']:,} B; verify {mldsa_verify.median_ms_A:.3f}/{mldsa_verify.median_ms_B:.3f} ms on A/B. SLH-DSA signature {slh_sizes['signature']:,} B; sign {slh_sign.median_ms_A:.1f}/{slh_sign.median_ms_B:.1f} ms. |",
    ]
    a_record, b_record = latest_record.get("A", {}), latest_record.get("B", {})
    env = (
        f"Windows 11 (build {str(info.get('os_version', '26300')).split('.')[-1]}; the environment tool reported "
        f"OS label `{info.get('os', 'unknown')}`, version `{info.get('os_version', 'unknown')}`); Python {info.get('python', 'unknown')} "
        f"({info.get('python_impl', 'unknown')}); {info.get('physical_cores', '?')} physical / "
        f"{info.get('logical_cores', '?')} logical cores; {info.get('ram_total_gb', '?')} GB RAM. "
        f"Recorded CPU string: `{info.get('cpu_model', 'not recorded')}`."
    )
    battery_note = ""
    if info.get("on_battery") is True:
        battery_note = (
            "**Protocol caveat:** `platform_A_info.json` captured `on_battery: true`. This environment snapshot is "
            "not valid for the requested final AC-powered measurement; plug in the laptop, rerun `common/env_check.py`, "
            "then rerun both platforms before submission."
        )
        battery_limitation = "The environment snapshot records `on_battery=true`; the current benchmark set must be rerun while plugged in."
    elif info.get("on_battery") is False:
        battery_limitation = "The environment snapshot records `on_battery=false`; the runner does not record power state per individual run, so keep the laptop on AC power throughout measurements."
    else:
        battery_limitation = "Power state was not recorded; repeat the environment check on AC power."
    lock_path = ROOT / "requirements-lock.txt"
    locked = [line.strip() for line in lock_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")] if lock_path.exists() else []
    version_text = ", ".join(locked)
    ratio_range = f"{merged.B_over_A_ratio.min():.3f}–{merged.B_over_A_ratio.max():.3f}"
    within_factor = int(((merged.B_over_A_ratio >= (1 / 1.4)) & (merged.B_over_A_ratio <= 1.4)).sum())
    larger_differences = merged.loc[(merged.B_over_A_ratio > 1.4) | (merged.B_over_A_ratio < (1 / 1.4))].copy()
    larger_differences = larger_differences.sort_values("B_over_A_ratio")
    outlier_note = "; ".join(
        f"{r.algorithm} {r.operation} (B/A {r.B_over_A_ratio:.2f}) was {'faster' if r.B_over_A_ratio < 1 else 'slower'} on B"
        for r in larger_differences.itertuples()
    ) or "No operation differed by more than a factor of 1.4."
    repeat_count = int(merged.repeat_count.iloc[0])
    repeat_note = (f"Completed {available_repeats} repetitions per platform; the report summarizes the most recent {repeat_count}. "
                   f"Each completed CSV is preserved as `results/repeats/bench_platform_<platform>_run_01.csv` and so on before the next repetition overwrites the root CSV. "
                   f"The comparison uses the median of the {repeat_count} per-run medians (and median of per-run IQR/p95 values). "
                   + (f"{available_repeats - repeat_count} additional run(s) per platform are included in the repetition files." if available_repeats > repeat_count else ""))
    # One correctness run plus each benchmark repetition is logged per platform.
    final_logs_ok = final_logs_ok and len(runs) == 2 * (available_repeats + 1)
    baseline_min = min(float(a.baseline_rss_mb.min()), float(b.baseline_rss_mb.min()))
    baseline_max = max(float(a.baseline_rss_mb.max()), float(b.baseline_rss_mb.max()))
    clean_log = final_logs_ok and len(runs) > 0 and all(r.get("status") == "ok" for r in runs)
    readme_path = ROOT / "README.md"
    team_line = next((line for line in readme_path.read_text(encoding="utf-8-sig").splitlines() if line.startswith("**Team Name:**")), "**Team Name:** ____________________")
    report = f"""# QFF 2026 Phase 2 — PS-P3 Technical Report

{team_line}

## 1. Problem and scope

This project benchmarks the seven official CORE algorithms for post-quantum cryptography and classical reference comparison on Platforms A and B. It measures the operations in the official matrix and checks correctness before timing. No quantum circuit or quantum processor is used in this Phase 2 PQC benchmark.

The KEM set is ML-KEM-768, RSA-2048-OAEP, and ECDH-P256. The signature set is ML-DSA-65, SLH-DSA-SHA2-128s, RSA-2048-PSS, and ECDSA-P256. The classical algorithms are reference baselines and are not post-quantum secure.

## 2. Design decisions and alternatives considered

The implementation follows the official CORE matrix exactly and does not add optional EXTENDED algorithms, keeping the comparison within the 24-hour scope. It uses the supplied `cryptography` and `pqcrypto` bindings rather than implementing cryptographic primitives. The classical RSA and elliptic-curve entries are retained as the required reference baselines, not as post-quantum alternatives. ECDH is represented using the kit's specified ephemeral-key KEM-style procedure. Raw encodings are used for ML-KEM/ML-DSA/pqcrypto artifacts and DER SPKI/PKCS#8 for RSA and P-256 keys, as recorded in the sizes table. The measured ML-KEM and ML-DSA private-key sizes are compact seeds; the larger expanded FIPS key forms are noted separately because they may matter for constrained storage. A different library or a physical low-power device could provide another comparison, but would reduce comparability with the official reference environment; neither was used here.

## 3. Design and measurement method

The maintained `P3_benchmark/bench.py` harness uses the pinned `cryptography` and `pqcrypto` libraries. Correctness checks run before timing. The standalone correctness runner records successful round trips or valid signatures, modified-ciphertext rejection or changed secrets, and modified-message/signature rejection separately. The final run procedure writes these fields on both platforms.

Signatures use the fixed 1,024-byte SHAKE-256 message from `algorithm_matrix.json`. Each benchmark repetition has 10 warm-up calls per operation. Timed trials use at least 100 calls by default; selected operations below 0.1 ms use 1,000 calls, and SLH-DSA-SHA2-128s key generation/signing and RSA-2048 key generation use at least 30. {repeat_note} Trial count `n` is summed across repetitions.

Timing uses `time.perf_counter_ns()` around each operation. For memory, the harness launches a fresh child process per algorithm/operation, records baseline RSS, runs the operation repeatedly, and records the largest RSS observed after a call; the CSV reports the peak-minus-baseline delta. RSS is sampled after each call, so differences below about 4 KB are at the resolution limit and deltas up to roughly 100 KB can reflect allocator/sampling noise. Treat isolated deltas around 92 KB (including those seen for Platform B RSA-OAEP key generation and ML-DSA signing) as measurement/allocator noise, not evidence of a real algorithm-specific memory difference. Large timing IQRs are a separate issue: they show run-to-run timing variability, not RSS noise, so conclusions rely on medians and the IQR is reported as spread. Baseline RSS across these operations was {baseline_min:.1f}–{baseline_max:.1f} MB; the platform runner separately reports total process-tree peak RSS against Platform B's 128 MB budget.

Platform A is the laptop as-is. Platform B applies one CPU core, single-threaded libraries and a 128 MB process-tree memory budget on the same machine. It does not lower CPU clock speed. Since these cryptographic primitive calls are predominantly single-threaded, similar A/B medians are plausible. B restricts available core parallelism and memory headroom, and can change contention and timing variance. Observed B/A medians span {ratio_range}; {within_factor} of 21 operations were within a factor of 1.4 of A. Larger differences in these measurements were: {outlier_note}. ML-KEM-768 decapsulation was also slower on B (B/A {merged.loc[(merged.algorithm == 'ML-KEM-768') & (merged.operation == 'decapsulate'), 'B_over_A_ratio'].iloc[0]:.3f}); three repetitions do not establish whether this is a stable platform effect. The runner logs show A status `{a_record.get('status', 'not found')}` with peak {a_record.get('peak_rss_mb', 'n/a')} MB and B status `{b_record.get('status', 'not found')}` with peak {b_record.get('peak_rss_mb', 'n/a')} MB (128 MB budget; {b_record.get('cpu_pinning', 'n/a')}).

## 4. Environment and reproducibility

To reproduce the measurements from the Phase 2 folder, use:

```powershell
.venv\\Scripts\\python.exe common\\env_check.py
.venv\\Scripts\\python.exe P3_benchmark\\run_repeats.py --platform A --repeats 3 --clear-log
.venv\\Scripts\\python.exe P3_benchmark\\run_repeats.py --platform B --repeats 3
.venv\\Scripts\\python.exe P3_benchmark\\analyze.py
```

These commands run from the Phase 2 folder and use its `.venv`. The saved `platform_runs.jsonl` records the interpreter path used for the original runs (`..\\.venv\\Scripts\\python.exe` in the original folder layout); those historical command paths were made repository-relative for privacy. The run log still records the platform, script, arguments, status, elapsed time, memory, and Platform B settings. The wrapper saves each child CSV before the next `bench.py` invocation overwrites the latest-run CSV. `analyze.py` aggregates the three saved per-run CSVs, not only the latest-run copy.

Environment: {env} Locked package versions: `{version_text}`. See `platform_A_info.json` and `platform_runs.jsonl` for environment and run records. The A environment snapshot says `on_battery={info.get('on_battery', 'unknown')}`.

{battery_note}

The README contains the clean-clone setup commands using a `.venv` created inside the cloned project. Independent clean-clone reproduction by a teammate remains pending. The analysis script validates the raw CSVs and correctness report, aggregates the repeated run summaries, then regenerates `results/comparison_A_vs_B.csv`, `results/sizes.csv`, the charts and this report.

## 5. Validation results (C1 evidence)

The table reports successful correctness trials, not a judging score. Each correctness case counts as passed only when both the round-trip/signature check and that algorithm's negative/tamper check succeed. Each of the three `bench.py` repetitions runs 100 cases per algorithm (300/300 total) or 10 per repetition for SLH-DSA-SHA2-128s (30/30 total). `correctness_report.csv` separately names each tamper outcome from the standalone correctness run on each platform.

| Algorithm | Platform A pass rate | Platform B pass rate | Negative/tamper check |
|---|---:|---:|---|
{chr(10).join(validation_rows)}

Platform A latest run status is `{a_record.get('status', 'not found')}`. Platform B latest run status is `{b_record.get('status', 'not found')}` and its reported peak RSS was {b_record.get('peak_rss_mb', 'n/a')} MB against the 128 MB budget.

## 6. Performance results

Each row shows 10 warm-ups per repetition, total timed trial counts across A/B repetitions, and median / IQR / p95 in milliseconds. For repeated runs, the displayed median is the median of run medians; IQR and p95 are medians of the per-run statistics. B/A is the B median divided by the A median. A value above 1 means B was slower; below 1 means B was faster.

| Algorithm | Operation | Warm-up | n (A/B) | A median / IQR / p95 (ms) | B median / IQR / p95 (ms) | B/A |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(timing_rows)}

Per-operation memory deltas are reported in `results/comparison_A_vs_B.csv`, in columns `memory_kb_A` and `memory_kb_B`; the individual repetition CSVs contain the corresponding `memory_kb` values for each run.

![Operation latency by platform](results/charts/latency_A_vs_B.png)

![Artifact sizes](results/charts/artifact_sizes.png)

![Platform B to A ratios](results/charts/platform_B_over_A.png)

![Bytes on wire with IoT limits](results/charts/bytes_on_wire.png)

### Reported artifact sizes

Sizes are those recorded by the harness on Platform A; encodings are stated per algorithm. The ML-KEM and ML-DSA secret sizes are compact seed forms (64 B and 32 B); the FIPS expanded secret-key forms are 2,400 B and 4,032 B respectively and should be considered for storage planning. Do not compare DER-encoded classical keys to raw PQC keys without accounting for encoding.

| Algorithm | Type | Sizes | Encoding |
|---|---|---|---|
{chr(10).join(alg_sizes)}

## 7. Security, trade-offs and deployment recommendations

### Deployment decision summary

| Scenario | Recommendation | Runner-up | Evidence and constraint |
|---|---|---|---|
{chr(10).join(recommendation_rows)}

These are crypto-operation comparisons, not end-to-end application benchmarks. Select the post-quantum option when post-quantum protection is a requirement; use the classical runner-up only when policy accepts classical security and the size or latency constraint takes priority. Confirm the choice against the target device and protocol framing before deployment.

ML-KEM-768 and ML-DSA-65 are NIST security level 3 in the supplied matrix; SLH-DSA-SHA2-128s is level 1 and hash-based, while ML-KEM/ML-DSA are lattice-based. The different assumptions are a real design choice, not a ranking from timing alone. Classical RSA and P-256 are useful performance and size baselines but are not quantum resistant. In these measurements, ML-DSA signing on A was {fmt(mldsa_sign.median_ms_A, 4)} ms with a 3,309 B signature, versus RSA-PSS at {fmt(rsa_pss_sign.median_ms_A, 4)} ms / 256 B and ECDSA at {fmt(ecdsa_sign.median_ms_A, 4)} ms / 71 B; those smaller/faster classical signatures do not provide the target post-quantum protection. SLH-DSA signing was {fmt(slh_sign.median_ms_A, 2)} ms and its signature was 7,856 B, trading much higher cost and size for a hash-based security assumption.

**Secret-key storage trade-off:** the measured compact seed forms use 64 B for ML-KEM-768 and 32 B for ML-DSA-65, compared with expanded forms of 2,400 B and 4,032 B (37.5× and 126× larger). Compact forms reduce persistent storage; expanded forms require more storage. Runtime expansion cost was not separately benchmarked.

### S1 — High-traffic TLS front-end

**Recommendation:** ML-KEM-768 for key establishment with ML-DSA-65 for authentication. On A, ML-KEM keygen/encapsulation/decapsulation medians were {fmt(kem_by_op['keygen'].median_ms_A, 4)}, {fmt(kem_by_op['encapsulate'].median_ms_A, 4)}, and {fmt(kem_by_op['decapsulate'].median_ms_A, 4)} ms; ML-DSA sign/verify were {fmt(mldsa_sign.median_ms_A, 4)} / {fmt(mldsa_verify.median_ms_A, 4)} ms. On B, the corresponding values were {fmt(kem_by_op['keygen'].median_ms_B, 4)}, {fmt(kem_by_op['encapsulate'].median_ms_B, 4)}, {fmt(kem_by_op['decapsulate'].median_ms_B, 4)} ms and {fmt(mldsa_sign.median_ms_B, 4)} / {fmt(mldsa_verify.median_ms_B, 4)} ms. ML-DSA-65 also has a smaller signature than SLH-DSA in these results (3,309 B versus 7,856 B) and much lower signing latency. As a server-side, single-core crypto-only proxy, encapsulation plus signing takes {s1_a_pqc_ms:.4f} ms on A ({1000/s1_a_pqc_ms:.0f} handshakes/s/core) and {s1_b_pqc_ms:.4f} ms on B ({1000/s1_b_pqc_ms:.0f}/s/core). ECDH encapsulation plus ECDSA signing takes {s1_a_classical_ms:.4f} ms on A ({1000/s1_a_classical_ms:.0f}/s/core) and {s1_b_classical_ms:.4f} ms on B ({1000/s1_b_classical_ms:.0f}/s/core). The PQC pair takes about {s1_a_pqc_ms/s1_a_classical_ms:.1f}× as long by these serial operation medians; this excludes protocol, certificate and network overhead and is not an end-to-end throughput test. **Runner-up:** ECDH-P256 + ECDSA-P256 when an existing deployment must use classical cryptography and classical security is acceptable. This pair is much faster and smaller in these measurements, but it is not quantum resistant and is not a security-equivalent PQC substitute. RSA-2048-OAEP and RSA-2048-PSS remain additional classical baselines. A migration could use a standards-based ECDH+ML-KEM hybrid with an approved combiner; this project did not implement or benchmark a hybrid, and the raw public-key-plus-ciphertext artifacts total about 2,454 B before framing.

### S2 — Bandwidth-limited IoT link

**Recommendation:** ML-KEM-768 when post-quantum key establishment is required and the link can fragment or tolerate a small overage: public key plus ciphertext is 2,272 B, 224 B above 2 KiB, with A encapsulation/decapsulation medians of {fmt(kem_by_op['encapsulate'].median_ms_A, 4)} / {fmt(kem_by_op['decapsulate'].median_ms_A, 4)} ms. ML-DSA verification material (public key plus signature) is 5,261 B, so a PQC-authenticated exchange needs fragmentation or a protocol redesign. **Runner-up:** ECDH-P256 where a strict bandwidth cap takes priority and classical security is acceptable: its public-key-plus-ephemeral-key exchange is 182 B, with A encapsulation/decapsulation medians of {fmt(ecdh_enc.median_ms_A, 4)} / {fmt(merged[(merged.algorithm == 'ECDH-P256') & (merged.operation == 'decapsulate')].iloc[0].median_ms_A, 4)} ms; it is not quantum resistant. If the link cannot fragment at all, none of the measured post-quantum exchanges fits the 2 KiB budget together with signature material.

### S3 — Firmware signing for constrained devices

**Recommendation:** ML-DSA-65 where the device can store and process a 3,309-byte signature. Verification medians were {fmt(mldsa_verify.median_ms_A, 4)} ms on A and {fmt(mldsa_verify.median_ms_B, 4)} ms on B. **Runner-up:** SLH-DSA-SHA2-128s when a hash-based signature is preferred; it verified in {fmt(slh_verify.median_ms_A, 4)} / {fmt(slh_verify.median_ms_B, 4)} ms but uses a 7,856-byte signature, and signing took {fmt(slh_sign.median_ms_A, 2)} / {fmt(slh_sign.median_ms_B, 2)} ms. A's SLH-DSA signing IQR was {fmt(slh_sign.iqr_ms_A, 2)} ms versus {fmt(slh_sign.iqr_ms_B, 2)} ms on B, showing much greater run-to-run variability on A; three repeats do not establish why, so treat this spread as timing noise rather than a stable platform effect. This trade-off favors ML-DSA for verification speed and flash footprint, while SLH-DSA offers a different, hash-based security assumption and is substantially slower here. Confirm actual firmware memory and flash constraints before deployment.

## 8. Limitations and improvements

- Platform B is a constrained profile on the same laptop, not a slower physical device. It limits cores, threading and process memory but does not emulate reduced clock speed.
- Run-to-run timing variation is visible in several IQRs, especially RSA key generation and SLH-DSA signing. Recommendations use medians; repeat measurements and target-device validation would improve confidence.
- {battery_limitation}
- Memory deltas are sampled RSS changes; small increments up to about 100 KB, including isolated 92 KB readings, are within allocator/sampling noise and should not be read as real algorithm-specific memory differences. Large timing IQRs describe timing variability, not memory noise. The platform-level peak RSS is a separate process-tree measurement.
- Classical baselines are included for comparison only; they are not quantum safe.
- Passing these test cases shows the tested operations behaved as expected; it does not independently establish implementation security, side-channel resistance, protocol safety, or production readiness.
- Platform D is a same-laptop 96 MB process-tree memory-cap emulation, not a physical device. It does not model slower CPU clocks, different hardware, or power use. A real target device would add those effects.

## 9. Files and regeneration

- Raw results: `results/bench_platform_A.csv` and `results/bench_platform_B.csv`; individual repetitions in `results/repeats/`
- Correctness evidence: `results/correctness_report.csv` and `.json`
- Comparison and artifact sizes: `results/comparison_A_vs_B.csv`, `results/sizes.csv`
- Charts: `results/charts/`
- Reproduction harness: `P3_benchmark/bench.py`; correctness runner: `P3_benchmark/correctness.py`
- Analysis script: `P3_benchmark/analyze.py`
- Environment/run evidence: `platform_A_info.json`, `platform_runs.jsonl`
- Exact installed environment: `requirements.txt` (also recorded in `requirements-lock.txt`)
- Optional tighter-memory profile and comparison: `platform_D.md`; generated by `P3_benchmark/analyze_platform_D.py`

"""
    (ROOT / "report.md").write_text(report, encoding="utf-8")


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    a, b, merged, a_latest, b_latest, repeats, available_repeats = load_data()
    write_comparison(merged)
    write_sizes(a)
    write_correctness_reports(a, b)
    make_latency_chart(a, b)
    make_sizes_chart(a)
    make_ratio_chart(merged)
    make_wire_chart(a)
    make_report(a, b, merged, available_repeats)
    if list((RESULTS / "repeats").glob("bench_platform_D_run_*.csv")):
        from analyze_platform_D import main as analyze_d
        analyze_d()
    print(f"Wrote comparison, sizes, four charts and report under {RESULTS} and {ROOT / 'report.md'} ({repeats}-run summary; {available_repeats} available per platform)")


if __name__ == "__main__":
    main()



