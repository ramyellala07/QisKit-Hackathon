# PS-P3 — Official Benchmark Protocol

Use this protocol on **Platform A and Platform B**, with the algorithms in `algorithm_matrix.json`.
Results that follow it are comparable across teams. Anything you do differently must be labelled as an
*additional experiment*.

## 1. Order of work

1. `python common/env_check.py` → must print `READY`. Commit `platform_A_info.json`.
2. **Correctness before timing.** For every CORE algorithm, run at least 100 correctness trials (10 for SLH-DSA-SHA2-128s):
   - KEM: decapsulated secret == encapsulated secret, and a modified ciphertext does **not** give the same secret (for RSA-OAEP, decryption fails).
   - Signature: a valid signature verifies, and a modified message (and a modified signature) fails.
   An algorithm that fails correctness is not benchmarked. Report the failure.
3. Run the benchmark on Platform A, then on Platform B, with the same code and inputs:
   ```
   python common/run_on_platform.py --platform A -- python P3_benchmark/<your_bench>.py
   python common/run_on_platform.py --platform B -- python P3_benchmark/<your_bench>.py
   ```
4. Commit the raw results (`results/*.csv`) and `platform_runs.jsonl`.

## 2. Measurement rules

| Item | Rule |
|---|---|
| Timer | `time.perf_counter_ns()` around each single operation (use `common/measure.py`) |
| Warm-up | 10 untimed calls per operation |
| Trials | ≥ 100 timed calls per operation. Exceptions: SLH-DSA-SHA2-128s keygen/sign and RSA-2048 keygen need ≥ 30 |
| Inputs | Prepared **outside** the timed call. Sign/verify the fixed 1,024-byte message `SHAKE-256(b"QFF2026-P3-message")[:1024]` |
| Statistics | Median (primary), IQR, p95, min/max, n. Do **not** report only the mean |
| Memory | Peak RSS delta of a fresh process per (algorithm, operation), as in `bench_template.py`, **or** another method you describe. Always state the method and its resolution |
| Sizes | Public key, secret key, ciphertext, shared secret, signature in bytes. State the encoding (raw / DER) and whether the secret key is the seed or the expanded form |
| Environment | Plugged in to power, other heavy apps closed, same machine for A and B |
| Platform B | Must report `status=ok` in `platform_runs.jsonl`. A run that exceeds the 128 MB budget is a **result**: report it, then reduce memory (e.g. don't import pandas in the benchmark process) and re-run |

## 3. Required outputs

- `results/bench_platform_A.csv` and `results/bench_platform_B.csv`, with the columns of `results_template.csv`.
- A comparison table: each algorithm × operation, A vs B median and the **B/A ratio**.
- At least **three charts**, for example:
  - operation latency (log scale), PQC vs classical;
  - artifact sizes in bytes;
  - B/A ratio;
  - bytes on the wire per handshake-equivalent.
- The **correct-operation rate** for each algorithm on each platform.

## 4. Deployment scenarios for your recommendations (choose at least two)

| ID | Scenario | Constraint to reason about |
|---|---|---|
| S1 | High-traffic TLS front-end | handshakes per second per core; keygen + encapsulate + sign cost |
| S2 | Bandwidth-limited IoT link (≈ 1–2 KB per message, e.g. LoRa/NB-IoT class) | public key + ciphertext + signature bytes; fragmentation |
| S3 | Firmware signing for constrained devices | verify cost and memory on the device; signature size in flash; signing is offline |
| S4 | Long-term archive / document signing (10+ years) | security level, conservative assumptions (hash-based vs lattice), signature size |
| S5 | Memory-constrained gateway (Platform B budget) | peak memory, secret-key storage (seed vs expanded) |

For each chosen scenario give: the recommended algorithm and parameter set, the runner-up, the evidence from
**your own measurements** that supports the choice, and the security trade-off you accept.

## 5. Platforms

- **Platform A** — your own laptop or desktop, used as-is. Mandatory.
- **Platform B** — the constrained profile applied by `common/run_on_platform.py`: 1 CPU core, single-threaded libraries, 128 MB peak-memory budget. Mandatory.
- **Platform D** — *optional*. Your own justified constraint profile, e.g. a second, slower physical device (Raspberry Pi, older laptop, phone with Termux), a tighter memory budget, or a different library/build. Measure it with the same protocol. Platform D is not needed for full marks.

> Expected behaviour: most single-call primitives are single-threaded, so B/A latency ratios can be close to 1.
> That is a valid finding. Explain *why*, and what B does change (core contention, memory headroom, variance).
> A real slower device as Platform D is the best way to show clock-speed effects.
