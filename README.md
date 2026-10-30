# PS-P3: PQC Performance Benchmark Across Constrained Platforms

**Team Name:** EchoNova

**Problem statement:** PS-P3 — PQC Performance Benchmark Across Constrained Platforms  
**Phase 1 work reused:** No; this submission follows the Phase 2 PQC challenge kit.

## 1. Summary

This project benchmarks the seven official CORE algorithms on Platform A and Platform B, with an optional tighter-memory Platform D profile: ML-KEM-768, RSA-2048-OAEP, ECDH-P256, ML-DSA-65, SLH-DSA-SHA2-128s, RSA-2048-PSS, and ECDSA-P256. It runs correctness and tamper checks before measuring key generation, encapsulation/decapsulation, signing, and verification, then creates reproducible A/B comparisons and deployment recommendations.

## 2. Setup — exact steps

Use Python 3.10–3.13. If PowerShell is open at the repository root (the folder containing `Phase 1` and `Phase 2`), first enter the Phase 2 folder:

```powershell
Set-Location "Phase 2"
```

Run the setup commands below from inside `Phase 2`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe common\env_check.py
```

The environment check must end with `READY - environment is correct`. Keep the laptop plugged in for the environment check and both platforms so `platform_A_info.json` records `on_battery=false`.

## 3. Reproduce the principal results — exact commands

From inside the `Phase 2` folder, run three repetitions per platform. Platform A archives prior run history and raw repeats, then starts a clean final log; Platform B appends its final run records. The runner executes correctness and tamper checks through `common/run_on_platform.py` first, then benchmarks all seven CORE algorithms. Plug in and run `common/env_check.py` before this sequence.

```powershell
.\.venv\Scripts\python.exe common\env_check.py
.\.venv\Scripts\python.exe P3_benchmark\run_repeats.py --platform A --repeats 3 --clear-log
.\.venv\Scripts\python.exe P3_benchmark\run_repeats.py --platform B --repeats 3
.\.venv\Scripts\python.exe P3_benchmark\analyze.py
```

Optional Platform D repeats use the same laptop, one-core pinning, and single-thread configuration as B, with a custom 96 MB process-tree memory budget. Run from the same project folder:

```powershell
.\.venv\Scripts\python.exe P3_benchmark\run_repeats.py --platform D --repeats 3
.\.venv\Scripts\python.exe P3_benchmark\analyze_platform_D.py
```

This is a tighter-memory emulation, not a slower physical device. `platform_D.md` contains its profile, run records, A/B/D operation medians, and chart.

`run_repeats.py` runs `correctness.py` once, then launches `bench.py` once per repetition through `common/run_on_platform.py`. The log records each launched child command, so its benchmark entries say `bench.py --platform A` or `bench.py --platform B`; this is expected even though you start the run with `run_repeats.py`. Since `bench.py` overwrites the root CSV each time, the wrapper copies each completed CSV to `results/repeats/bench_platform_<A-or-B>_run_01.csv` through `run_03.csv` before starting the next repetition. `analyze.py` reads those six saved CSVs and reports the median of the three run medians (and medians of per-run IQR/p95); `results/bench_platform_A.csv` and `bench_platform_B.csv` are only the latest-run copies.

`platform_runs.jsonl` contains successful A/B runs and the optional D correctness and benchmark records. `results/archive/` contains superseded pre-final exploratory runs and setup attempts for local traceability; those archived records are not final evidence.

For privacy, only the `command` paths in `platform_runs.jsonl` were changed from absolute paths to repository-relative paths after the runs. Timestamps, statuses, wall times, RSS values, budgets, and CPU-pinning fields were left unchanged. A later run with `--clear-log` will regenerate the log from the runner.

Expected time is a rough estimate only; three repetitions can take longer because the harness uses 1,000 samples for fast operations and SLH-DSA is comparatively slow. After both platforms finish, the analysis step writes the comparison table, sizes table, charts, and `report.md`. Trial count `n` is the sum across repetitions.

## 4. Platforms used

| Platform | Machine / profile | Evidence file |
|---|---|---|
| A | Windows 11 (build 26300; `env_check.py` reports `Windows 10`, version `10.0.26300`); 6 physical / 12 logical cores; 15.73 GB RAM | `platform_A_info.json` |
| B | Same machine, one pinned CPU core, single-threaded libraries, 128 MB process-tree memory budget | `platform_runs.jsonl` |
| D | Same Windows laptop, one pinned CPU core, single-threaded libraries, **96 MB process-tree memory budget** (custom tighter-memory emulation) | `platform_runs.jsonl`, `platform_D.md` |

Platforms B and D constrain core availability and memory; neither reduces CPU clock speed. D is a same-device memory-budget emulation, not a second or slower physical device.

## 5. Libraries and versions

The exact installed package versions are pinned in `requirements.txt`, including `cryptography==50.0.2`, `pqcrypto==1.0.0`, `numpy`, `pandas`, and `matplotlib`. Cryptographic operations use the vetted `cryptography` and `pqcrypto` libraries; no cryptographic primitive is implemented in this project.

## 6. Tests

`P3_benchmark/correctness.py` records round-trip and negative-input outcomes in `results/correctness_report.csv` and `results/correctness_report.json`. The benchmark harness also repeats correctness checks before timing each algorithm. KEM checks include altered ciphertext handling; signature checks include modified messages and modified signatures. RSA-OAEP must reject altered ciphertext by a decryption error.

The final run output shows all CORE correctness and tamper checks passing on A, B, and D. **Independent clean-clone reproduction by a teammate: pending.** Record the teammate, date, and outcome here after it is completed.

**Current checkpoint:** the environment snapshot records `on_battery=false`; all seven correctness checks passed on A, B, and D; three benchmark repetitions completed on each profile; and all recorded runs completed successfully. The D profile is the same-device 96 MB memory-cap emulation.

## 7. Results

- Raw measurements: [`results/bench_platform_A.csv`](results/bench_platform_A.csv), [`results/bench_platform_B.csv`](results/bench_platform_B.csv)
- Optional D raw measurements: [`results/bench_platform_D.csv`](results/bench_platform_D.csv) (latest run); three saved D repetitions are in `results/repeats/`
- Repeated-run summaries: `results/repeats/`
- Correctness evidence: [`results/correctness_report.csv`](results/correctness_report.csv), [`results/correctness_report.json`](results/correctness_report.json)
- A/B medians and ratios: [`results/comparison_A_vs_B.csv`](results/comparison_A_vs_B.csv)
- Key, ciphertext, and signature sizes: [`results/sizes.csv`](results/sizes.csv)
- Charts: `results/charts/`
- Technical report: [`report.md`](report.md)
- Platform D analysis: [`platform_D.md`](platform_D.md)

## 8. Baseline used

The classical reference baselines are RSA-2048-OAEP, ECDH-P256, RSA-2048-PSS, and ECDSA-P256. They provide performance and artifact-size comparisons but are not quantum resistant. PQC recommendations are based on the measured ML-KEM-768, ML-DSA-65, and SLH-DSA-SHA2-128s results.

## 9. Known limitations

Platform B and D use the same laptop and do not simulate a slower CPU. D is a same-laptop 96 MB memory-cap emulation, not real target hardware; CPU speed and device architecture are unchanged. The memory-delta method samples RSS after calls and has roughly 4 KB resolution; deltas up to about 100 KB can include allocator/sampling noise. The independent teammate clean-clone reproduction remains pending.



