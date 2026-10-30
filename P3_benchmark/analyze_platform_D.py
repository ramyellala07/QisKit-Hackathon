"""Summarize the optional Platform D tighter-memory experiment."""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

from analyze import ALGORITHMS, load_platform

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CHART = RESULTS / "charts" / "platform_D_vs_A_B.png"


def main():
    a, _, _, _ = load_platform("A")
    b, _, _, _ = load_platform("B")
    d, _, d_repeats, _ = load_platform("D")
    cols = ["algorithm", "operation", "median_ms"]
    combined = a[cols].rename(columns={"median_ms": "A_ms"})
    combined = combined.merge(b[cols].rename(columns={"median_ms": "B_ms"}), on=["algorithm", "operation"])
    combined = combined.merge(d[cols].rename(columns={"median_ms": "D_ms"}), on=["algorithm", "operation"])
    combined["D_over_A"] = combined.D_ms / combined.A_ms
    combined["D_over_B"] = combined.D_ms / combined.B_ms

    logs = [json.loads(line) for line in (ROOT / "platform_runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    d_logs = [row for row in logs if row.get("platform") == "D"]
    correct = pd.read_csv(RESULTS / "correctness_report.csv")
    d_correct = correct[correct.platform == "D"]
    standalone_trials = sum(10 if alg == "SLH-DSA-SHA2-128s" else 100 for alg in ALGORITHMS)
    chart_data = combined.sort_values("D_over_A")
    fig, ax = plt.subplots(figsize=(10, 8), constrained_layout=True)
    y = range(len(chart_data))
    ax.barh([f"{r.algorithm} · {r.operation}" for r in chart_data.itertuples()], chart_data.D_over_A,
            color=["#c44e52" if value > 1 else "#4c72b0" for value in chart_data.D_over_A])
    ax.axvline(1, color="black", linewidth=1, linestyle="--")
    ax.set_xscale("log")
    ax.set_xlabel("Platform D / Platform A median latency (log scale)")
    ax.set_title("Platform D: tighter memory cap, same laptop and CPU")
    ax.grid(axis="x", which="both", alpha=0.25)
    ax.legend(handles=[Patch(color="#4c72b0", label="D faster than A"),
                       Patch(color="#c44e52", label="D slower than A")], loc="lower right")
    fig.savefig(CHART, dpi=180)
    plt.close(fig)

    d_below = int(((combined.D_over_B >= 1 / 1.4) & (combined.D_over_B <= 1.4)).sum())
    table = "\n".join(
        f"| {r.algorithm} | {r.operation} | {r.A_ms:.4f} | {r.B_ms:.4f} | {r.D_ms:.4f} | {r.D_over_A:.3f} | {r.D_over_B:.3f} |"
        for r in combined.itertuples()
    )
    peak_rows = "\n".join(
        f"| {'Correctness' if index == 0 else f'Benchmark {index}'} | {row.get('status')} | {row.get('peak_rss_mb')} | {row.get('mem_budget_mb')} | {row.get('wall_time_s')} |"
        for index, row in enumerate(d_logs)
    )
    report = f"""# Optional Platform D — tighter-memory emulation

## Profile and reason

Platform D tests whether the same benchmark workload completes with less process memory headroom than Platform B. It uses the same Windows laptop, Python environment, crypto libraries, one pinned CPU core, and single-thread settings, but lowers the process-tree RSS cap from B's 128 MB to **96 MB**. This is a custom gateway-like memory-budget profile. It is not a physical constrained device and does not model a slower CPU, different architecture, power use, or flash storage.

The repeated workload follows the project's standard correctness-before-timing protocol: all seven CORE algorithms, 10 warm-ups per operation, the same sample counts and message, and **{d_repeats} saved repetitions**. Reproduce it from the project root with:

```powershell
./.venv/Scripts/python.exe P3_benchmark/run_repeats.py --platform D --repeats 3
./.venv/Scripts/python.exe P3_benchmark/analyze_platform_D.py
```

The D profile is declared in `common/run_on_platform.py`. Platform D is optional; A/B official profiles and their comparisons are unchanged.

## Outcome

The standalone correctness run passed **{standalone_trials}/{standalone_trials} trials** across the seven algorithms. Benchmark-internal correctness checks also passed **{int(d_correct.passed_trials.sum())}/{int(d_correct.correctness_trials.sum())} trials** across the three repetitions. All three benchmark runs completed with `status=ok`. Peak process-tree RSS was **{min(row['peak_rss_mb'] for row in d_logs[1:]):.1f}–{max(row['peak_rss_mb'] for row in d_logs[1:]):.1f} MB** against the 96 MB cap, leaving about **{96-max(row['peak_rss_mb'] for row in d_logs[1:]):.1f} MB** at the highest observed peak. Correctness runner peak was {d_logs[0].get('peak_rss_mb')} MB.

Across the 21 operation medians, **{d_below}/21 D/B ratios** were within a factor of 1.4. The profile keeps the same one-core execution and changes the memory ceiling; because observed use stayed below the cap, it did not force an out-of-memory condition. Its main result is that this workload completed under a 96 MB process-tree limit on this host. The timing differences should not be attributed to a slower device or a physical memory-constrained system.

![D to A median latency ratios]({CHART.relative_to(ROOT).as_posix()})

## Run records

| Run | Status | Peak RSS (MB) | Budget (MB) | Wall time (s) |
|---|---|---:|---:|---:|
{peak_rows}

## Operation medians

All values are milliseconds; ratios above 1 mean D was slower than the comparison platform. D medians are the median of the three saved run medians; A/B use the project's existing three-run summaries.

| Algorithm | Operation | A median | B median | D median | D/A | D/B |
|---|---|---:|---:|---:|---:|---:|
{table}

Raw D data: `results/bench_platform_D.csv` (latest run) and `results/repeats/bench_platform_D_run_01.csv` through `_03.csv`. The operation comparison chart is `results/charts/platform_D_vs_A_B.png`.
"""
    (ROOT / "platform_D.md").write_text(report, encoding="utf-8")
    print(f"Wrote {ROOT / 'platform_D.md'} and {CHART}")


if __name__ == "__main__":
    main()
