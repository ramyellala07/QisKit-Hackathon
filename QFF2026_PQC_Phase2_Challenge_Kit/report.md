# Technical Report — [Team Name] — QFF 2026 Phase 2 PS-P3

> **Final repeated runs recorded; team details and clean-clone reproduction remain to be recorded** — Fill in team names and roles; record the independent clean-clone reproduction if required by the judging process.

## 1. Problem and scope

This project benchmarks the seven official CORE algorithms for post-quantum cryptography and classical reference comparison on Platforms A and B. It measures the operations in the official matrix and checks correctness before timing. No quantum circuit or quantum processor is used in this Phase 2 PQC benchmark.

The KEM set is ML-KEM-768, RSA-2048-OAEP, and ECDH-P256. The signature set is ML-DSA-65, SLH-DSA-SHA2-128s, RSA-2048-PSS, and ECDSA-P256. The classical algorithms are reference baselines and are not post-quantum secure.

## 2. Design decisions and alternatives considered

The implementation follows the official CORE matrix exactly and does not add optional EXTENDED algorithms, keeping the comparison within the 24-hour scope. It uses the supplied `cryptography` and `pqcrypto` bindings rather than implementing cryptographic primitives. The classical RSA and elliptic-curve entries are retained as the required reference baselines, not as post-quantum alternatives. ECDH is represented using the kit's specified ephemeral-key KEM-style procedure. Raw encodings are used for ML-KEM/ML-DSA/pqcrypto artifacts and DER SPKI/PKCS#8 for RSA and P-256 keys, as recorded in the sizes table. The measured ML-KEM and ML-DSA private-key sizes are compact seeds; the larger expanded FIPS key forms are noted separately because they may matter for constrained storage. A different library or a physical low-power device could provide another comparison, but would reduce comparability with the official reference environment; neither was used here.

## 3. Design and measurement method

The supplied `P3_benchmark/bench_template.py` was extended into `P3_benchmark/bench.py` using the pinned `cryptography` and `pqcrypto` libraries. Correctness checks run before timing. The standalone correctness runner records successful round trips or valid signatures, modified-ciphertext rejection or changed secrets, and modified-message/signature rejection separately. The final run procedure writes these fields on both platforms.

Signatures use the fixed 1,024-byte SHAKE-256 message from `algorithm_matrix.json`. Each benchmark repetition has 10 warm-up calls per operation. Timed trials use at least 100 calls by default; selected operations below 0.1 ms use 1,000 calls, and SLH-DSA-SHA2-128s key generation/signing and RSA-2048 key generation use at least 30. Completed 3 repetitions per platform; the report summarizes the most recent 3. The comparison uses the median of repetition medians and median of per-run IQR/p95 values; n is summed across repetitions.

Timing uses `time.perf_counter_ns()` around each operation. For memory, the harness launches a fresh child process per algorithm/operation, records baseline RSS, runs the operation repeatedly, and records the largest RSS observed after a call; the CSV reports the peak-minus-baseline delta. RSS is sampled after each call, so differences below about 4 KB are at the resolution limit and deltas up to roughly 100 KB can reflect allocator/sampling noise. Treat isolated deltas around 92 KB (including those seen for Platform B RSA-OAEP key generation and ML-DSA signing) as measurement/allocator noise, not evidence of a real algorithm-specific memory difference. Large timing IQRs are a separate issue: they show run-to-run timing variability, not RSS noise, so conclusions rely on medians and the IQR is reported as spread. Baseline RSS across these operations was 24.2–30.9 MB; the platform runner separately reports total process-tree peak RSS against Platform B's 128 MB budget.

Platform A is the laptop as-is. Platform B applies one CPU core, single-threaded libraries and a 128 MB process-tree memory budget on the same machine. It does not lower CPU clock speed. Since these cryptographic primitive calls are predominantly single-threaded, similar A/B medians are plausible. B restricts available core parallelism and memory headroom, and can change contention and timing variance. Observed B/A medians span 0.596–1.293; 20 of 21 operations were within a factor of 1.4 of A. Larger differences in these measurements were: RSA-2048-OAEP encapsulate (B/A 0.60) was faster on B. Treat them as run-specific outliers unless repeated measurements show the same pattern. The runner logs show A status `ok` with peak 82.9 MB and B status `ok` with peak 83.4 MB (128 MB budget; pinned to 1 core).

## 4. Environment and reproducibility

Exact measurements shown in the report were produced with these commands from the kit root:

```powershell
..\.venv\Scripts\python.exe common\env_check.py
..\.venv\Scripts\python.exe common\run_on_platform.py --platform A -- ..\.venv\Scripts\python.exe P3_benchmark\bench_template.py
..\.venv\Scripts\python.exe common\run_on_platform.py --platform B -- ..\.venv\Scripts\python.exe P3_benchmark\bench_template.py
```

The one-run measurements were first captured with the kit template. The maintained harness is `P3_benchmark/bench.py`; final repetitions use `P3_benchmark/run_repeats.py` as listed below.

Environment: Windows 11 (build 26300); Python 3.11.9 (CPython); 6 physical / 12 logical cores; 15.73 GB RAM. Recorded CPU string: `Intel64 Family 6 Model 165 Stepping 2, GenuineIntel`. Locked package versions: `cffi==2.1.1, contourpy==1.3.3, cryptography==50.0.2, cycler==0.12.1, fonttools==4.68.0, kiwisolver==1.5.1, matplotlib==3.11.2, numpy==2.4.6, packaging==26.3, pandas==3.1.0, pillow==13.0.0, pqcrypto==1.0.0, psutil==7.2.2, pycparser==3.12, pyparsing==3.3.3, python-dateutil==3.0.0, six==1.17.0, tzdata==2026.6`. See `platform_A_info.json` and `platform_runs.jsonl` for environment and run records. The A environment snapshot says `on_battery=False`.



From a clean clone, open a terminal in the challenge-kit root and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe common\env_check.py
.\.venv\Scripts\python.exe P3_benchmark\run_repeats.py --platform A --repeats 3 --clear-log
.\.venv\Scripts\python.exe P3_benchmark\run_repeats.py --platform B --repeats 3
.\.venv\Scripts\python.exe P3_benchmark\analyze.py
```

The analysis script validates the raw CSVs and correctness report, aggregates the repeated run summaries, then regenerates `results/comparison_A_vs_B.csv`, `results/sizes.csv`, the charts and this report. The supplied records do not establish who independently reran the README from a clean clone; record the teammate's name, date and outcome after that reproduction step is completed. Do not claim it has been completed before then.

## 5. Validation results (C1 evidence)

The table reports successful correctness trials, not a judging score. It uses the separate correctness report for round-trip and tamper results on both platforms; correctness totals alone do not provide that evidence.

| Algorithm | Platform A pass rate | Platform B pass rate | Negative/tamper check |
|---|---:|---:|---|
| ML-KEM-768 | 300/300 | 300/300 | A: roundtrip PASS; ciphertext PASS (altered ciphertext produced a different secret or was rejected); B: roundtrip PASS; ciphertext PASS (altered ciphertext produced a different secret or was rejected). Changed ciphertext did not reproduce the encapsulated secret |
| RSA-2048-OAEP | 300/300 | 300/300 | A: roundtrip PASS; ciphertext PASS (Modified OAEP ciphertext rejected by decryption error); B: roundtrip PASS; ciphertext PASS (Modified OAEP ciphertext rejected by decryption error). Changed ciphertext rejected by OAEP decryption |
| ECDH-P256 | 300/300 | 300/300 | A: roundtrip PASS; ciphertext PASS (altered ciphertext produced a different secret or was rejected); B: roundtrip PASS; ciphertext PASS (altered ciphertext produced a different secret or was rejected). Substituted ephemeral public key produced a different shared secret |
| ML-DSA-65 | 300/300 | 300/300 | A: signature PASS; modified message PASS; modified signature PASS; B: signature PASS; modified message PASS; modified signature PASS. Changed message and changed signature rejected |
| SLH-DSA-SHA2-128s | 30/30 | 30/30 | A: signature PASS; modified message PASS; modified signature PASS; B: signature PASS; modified message PASS; modified signature PASS. Changed message and changed signature rejected |
| RSA-2048-PSS | 300/300 | 300/300 | A: signature PASS; modified message PASS; modified signature PASS; B: signature PASS; modified message PASS; modified signature PASS. Changed message and changed signature rejected |
| ECDSA-P256 | 300/300 | 300/300 | A: signature PASS; modified message PASS; modified signature PASS; B: signature PASS; modified message PASS; modified signature PASS. Changed message and changed signature rejected |

Platform A latest run status is `ok`. Platform B latest run status is `ok` and its reported peak RSS was 83.4 MB against the 128 MB budget. Confirm the final `platform_runs.jsonl` contains only the intended final runs.

## 6. Performance results

Each row shows 10 warm-ups per repetition, total timed trial counts across A/B repetitions, and median / IQR / p95 in milliseconds. For repeated runs, the displayed median is the median of run medians; IQR and p95 are medians of the per-run statistics. B/A is the B median divided by the A median. A value above 1 means B was slower; below 1 means B was faster.

| Algorithm | Operation | Warm-up | n (A/B) | A median / IQR / p95 (ms) | B median / IQR / p95 (ms) | B/A |
|---|---:|---:|---:|---:|---:|---:|
| ECDH-P256 | decapsulate | 10 | 3000 / 3000 | 0.0565 / 0.0195 / 0.1075 | 0.0584 / 0.0102 / 0.0917 | 1.034 |
| ECDH-P256 | encapsulate | 10 | 3000 / 3000 | 0.0909 / 0.0066 / 0.1182 | 0.0959 / 0.0102 / 0.1431 | 1.055 |
| ECDH-P256 | keygen | 10 | 3000 / 3000 | 0.0242 / 0.0047 / 0.0410 | 0.0268 / 0.0047 / 0.0474 | 1.107 |
| ECDSA-P256 | keygen | 10 | 3000 / 3000 | 0.0241 / 0.0021 / 0.0331 | 0.0251 / 0.0085 / 0.0467 | 1.041 |
| ECDSA-P256 | sign | 10 | 3000 / 3000 | 0.0441 / 0. 0056 / 0.0692 | 0.0430 / 0.0192 / 0.0805 | 0.975 |
| ECDSA-P256 | verify | 10 | 3000 / 3000 | 0.0993 / 0.0677 / 0.1958 | 0.0922 / 0.0255 / 0.1598 | 0.928 |
| ML-DSA-65 | keygen | 10 | 300 / 300 | 0.2746 / 0.0287 / 0.3690 | 0.2856 / 0.0194 / 0.4172 | 1.040 |
| ML-DSA-65 | sign | 10 | 300 / 300 | 1.2329 / 1.2815 / 4.1574 | 1.2612 / 1.2304 / 4.6865 | 1.023 |
| ML-DSA-65 | verify | 10 | 3000 / 3000 | 0.2753 / 0.0578 / 0.4867 | 0.2765 / 0.0302 / 0.4156 | 1.004 |
| ML-KEM-768 | decapsulate | 10 | 300 / 300 | 0.0917 / 0.0022 / 0.0989 | 0.1186 / 0.0278 / 0.1515 | 1.293 |
| ML-KEM-768 | encapsulate | 10 | 3000 / 3000 | 0.0605 / 0.0058 / 0.0841 | 0.0613 / 0.0044 / 0.0831 | 1.013 |
| ML-KEM-768 | keygen | 10 | 300 / 300 | 0.2558 / 0.0774 / 0.3782 | 0.2737 / 0.0934 / 0.4698 | 1.070 |
| RSA-2048-OAEP | decapsulate | 10 | 300 / 300 | 0.7557 / 0.2899 / 1.2508 | 0.6473 / 0.0755 / 1.0853 | 0.857 |
| RSA-2048-OAEP | encapsulate | 10 | 3000 / 3000 | 0.0532 / 0.0233 / 0.0725 | 0.0317 / 0.0030 / 0.0485 | 0.596 |
| RSA-2048-OAEP | keygen | 10 | 300 / 300 | 51.0411 / 48.7707 / 123.5003 | 52.9273 / 44.9500 / 117.9384 | 1.037 |
| RSA-2048-PSS | keygen | 10 | 300 / 300 | 55.9641 / 51.5886 / 127.3556 | 53.1974 / 45.9396 / 141.9050 | 0.951 |
| RSA-2048-PSS | sign | 10 | 300 / 300 | 0.6438 / 0.0649 / 1.0554 | 0.7035 / 0.0770 / 0.8913 | 1.093 |
| RSA-2048-PSS | verify | 10 | 3000 / 3000 | 0.0357 / 0.0021 / 0.0463 | 0.0410 / 0.0142 / 0.0775 | 1.148 |
| SLH-DSA-SHA2-128s | keygen | 10 | 90 / 90 | 225.2755 / 13.8775 / 249.1313 | 225.8861 / 6.1868 / 249.1005 | 1.003 |
| SLH-DSA-SHA2-128s | sign | 10 | 90 / 90 | 2039.4524 / 547.0508 / 2479.7282 | 1744.8764 / 53.4975 / 1887.9273 | 0.856 |
| SLH-DSA-SHA2-128s | verify | 10 | 300 / 300 | 1.6918 / 0.2580 / 2.2675 | 1.7854 / 0.1377 / 2.2198 | 1.055 |

![Operation latency by platform](results/charts/latency_A_vs_B.png)

![Artifact sizes](results/charts/artifact_sizes.png)

![Platform B to A ratios](results/charts/platform_B_over_A.png)

![Bytes on wire with IoT limits](results/charts/bytes_on_wire.png)

### Reported artifact sizes

Sizes are those recorded by the harness on Platform A; encodings are stated per algorithm. The ML-KEM and ML-DSA secret sizes are compact seed forms (64 B and 32 B); the FIPS expanded secret-key forms are 2,400 B and 4,032 B respectively and should be considered for storage planning. Do not compare DER-encoded classical keys to raw PQC keys without accounting for encoding.

| Algorithm | Type | Sizes | Encoding |
|---|---|---|---|
| ML-KEM-768 | KEM | public_key=1184 B; secret_key=64 B; ciphertext=1088 B; shared_secret=32 B | raw |
| RSA-2048-OAEP | KEM | public_key=294 B; secret_key=1217 B; ciphertext=256 B; shared_secret=32 B | DER SPKI / DER PKCS#8 |
| ECDH-P256 | KEM | public_key=91 B; secret_key=138 B; ciphertext=91 B; shared_secret=32 B | DER SPKI / DER PKCS#8; ciphertext is ephemeral public key |
| ML-DSA-65 | Signature | public_key=1952 B; secret_key=32 B; signature=3309 B | raw; secret key is compact seed form |
| SLH-DSA-SHA2-128s | Signature | public_key=32 B; secret_key=64 B; signature=7856 B | raw; pqcrypto expanded secret key |
| RSA-2048-PSS | Signature | public_key=294 B; secret_key=1217 B; signature=256 B | DER SPKI / DER PKCS#8 |
| ECDSA-P256 | Signature | public_key=91 B; secret_key=138 B; signature=71 B | DER SPKI / DER PKCS#8; signature is ASN.1 DER |

## 7. Security, trade-offs and deployment recommendations

ML-KEM-768 and ML-DSA-65 are NIST security level 3 in the supplied matrix; SLH-DSA-SHA2-128s is level 1 and hash-based, while ML-KEM/ML-DSA are lattice-based. The different assumptions are a real design choice, not a ranking from timing alone. Classical RSA and P-256 are useful performance and size baselines but are not quantum resistant. In these measurements, ML-DSA signing on A was 1.2329 ms with a 3,309 B signature, versus RSA-PSS at 0.6438 ms / 256 B and ECDSA at 0.0441 ms / 71 B; those smaller/faster classical signatures do not provide the target post-quantum protection. SLH-DSA signing was 2039.45 ms and its signature was 7,856 B, trading much higher cost and size for a hash-based security assumption.

### S1 — High-traffic TLS front-end

**Recommendation:** ML-KEM-768 for key establishment with ML-DSA-65 for authentication. On A, ML-KEM keygen/encapsulation/decapsulation medians were 0.2558, 0.0605, and 0.0917 ms; ML-DSA sign/verify were 1.2329 / 0.2753 ms. On B, the corresponding values were 0.2737, 0.0613, 0.1186 ms and 1.2612 / 0.2765 ms. ML-DSA-65 also has a smaller signature than SLH-DSA in these results (3,309 B versus 7,856 B) and much lower signing latency. **Runner-up:** the RSA-2048-OAEP + RSA-2048-PSS reference pair for environments prioritizing smaller artifacts or compatibility; it is classical and not quantum resistant, so it is not a security-equivalent PQC substitute.

### S3 — Firmware signing for constrained devices

**Recommendation:** ML-DSA-65 where the device can store and process a 3,309-byte signature. Verification medians were 0.2753 ms on A and 0.2765 ms on B. **Runner-up:** SLH-DSA-SHA2-128s when a hash-based signature is preferred; it verified in 1.6918 / 1.7854 ms but uses a 7,856-byte signature, and signing took 2039.45 / 1744.88 ms. This trade-off favors ML-DSA for verification speed and flash footprint, while SLH-DSA offers a different, hash-based security assumption and is substantially slower here. Confirm actual firmware memory and flash constraints before deployment.

For the S2 bandwidth-limited IoT scenario, the chart marks the 1–2 KiB message budget. Measured public-key-plus-ciphertext sizes are 2,272 B for ML-KEM-768, 550 B for RSA-OAEP, and 182 B for the ECDH ephemeral exchange. For signatures, public key plus signature is 5,261 B for ML-DSA-65 and 7,888 B for SLH-DSA-SHA2-128s. These sums exclude certificates, framing and protocol metadata. Classical references are smaller but do not provide post-quantum security; the measured PQC artifacts exceed the nominal link budget and would require fragmentation or protocol redesign.

## 8. Limitations and improvements

- Platform B is a constrained profile on the same laptop, not a slower physical device. It limits cores, threading and process memory but does not emulate reduced clock speed.
- Run-to-run timing variation is visible in several IQRs, especially RSA key generation and SLH-DSA signing. Recommendations use medians; repeat measurements and target-device validation would improve confidence.
- The environment snapshot records `on_battery=false`; the runner does not record power state per individual run, so keep the laptop on AC power throughout measurements.
- Memory deltas are sampled RSS changes; small increments up to about 100 KB, including isolated 92 KB readings, are within allocator/sampling noise and should not be read as real algorithm-specific memory differences. Large timing IQRs describe timing variability, not memory noise. The platform-level peak RSS is a separate process-tree measurement.
- Classical baselines are included for comparison only; they are not quantum safe.
- No optional Platform D or real-device deployment test was performed. A slower physical device would show clock-speed and hardware effects that Platform B cannot emulate.

## 9. Files and regeneration

- Raw results: `results/bench_platform_A.csv` and `results/bench_platform_B.csv`; individual repetitions in `results/repeats/`
- Correctness evidence: `results/correctness_report.csv` and `.json`
- Comparison and artifact sizes: `results/comparison_A_vs_B.csv`, `results/sizes.csv`
- Charts: `results/charts/`
- Reproduction harness: `P3_benchmark/bench.py`; correctness runner: `P3_benchmark/correctness.py`
- Analysis script: `P3_benchmark/analyze.py`
- Environment/run evidence: `platform_A_info.json`, `platform_runs.jsonl`
- Exact installed environment: `requirements.txt` (also recorded in `requirements-lock.txt`)

Replace `[Team Name]` before submission.
