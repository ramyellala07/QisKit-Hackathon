# Qiskit Fall Fest 2026 – Phase 1 Submission

**Team / participant:** [Sai Ram / EchoNova]
**Registered email:** [sairamyellala27@gmail.com]
**Selected problem statement:** PS-P3 – Reversible Quantum Arithmetic & Carry-Chain Bottlenecks (Hardware Routing Benchmark of Quantum Modular Adders & Multipliers), as listed on the QFF SRM-AP hackathon portal.

## What this project does

We benchmark quantum modular adders and a small multiplier on two processor models with different qubit connectivity (Processor A and Processor B). For each circuit and register width we measure how connectivity changes the compiled circuit (depth, two-qubit gates, SWAPs, routing overhead), how much compiler optimization reduces that cost, and how the circuit size affects the probability of getting the correct arithmetic result under a shared synthetic noise model.

## Circuits benchmarked

| Circuit | Qiskit class | Idea |
|---|---|---|
| Ripple-carry adder | `CDKMRippleCarryAdder` (kind="fixed") | Carry travels bit by bit along a chain (the "carry-chain bottleneck") |
| QFT adder | `DraperQFTAdder` (kind="fixed") | No carry chain, but needs many controlled-phase gates between qubit pairs |
| QFT multiplier | `RGQFTMultiplier` | Multiplication built from QFT-based addition |

Adders compute (a + b) mod 2^n with the result in register b. Register widths tested: as many as fit on each processor (n = 1 to 3 for adders, n = 1 for the multiplier).

**Test inputs.** (1) *carry-chain input*: a = 2^n - 1 (all ones) and b = 1, so the carry has to travel through the whole register; (2) a *mixed input*. Correctness is the fraction of shots that return the exactly correct result.

## Important assumptions (please read)

- No Challenge Kit with processor definitions was provided. The coordinators told participants to find the processors themselves, so **we defined Processors A and B ourselves**, guided by the organizer slides:
  - **Processor A:** 5 qubits, "bowtie" coupling graph `0-1, 0-2, 1-2, 2-3, 2-4, 3-4` (IBM-style 5-qubit layout).
  - **Processor B:** 7 qubits, heavy-hex-style "H" graph `0-1, 1-2, 1-3, 3-5, 4-5, 5-6`.
  - Both use basis gates `rz, sx, x, cx`.
  - Both use the **same** synthetic noise: 1-qubit depolarizing error 0.001 (on `sx`, `x`), 2-qubit depolarizing error 0.01 (on `cx`), readout error 0.02.
- Because A has 5 qubits and B has 7, bigger circuits only fit on B. Comparisons at the same register width are made only where both fit.
- An **optional scaling study** on a 12-qubit line and a 19-qubit heavy-hex map is included to look at larger widths. It reports compilation metrics only (no noisy runs) and is kept separate from the main A/B benchmark.
- Everything is simulation (Qiskit Aer). No real hardware was used.

## How to run

```
pip install -r requirements.txt
python main_p3.py
```

Outputs are written to `qff_phase1_p3/`. To print the results as tables, run `python show_results.py`.

## Repository contents

| Path | Content |
|---|---|
| `main_p3.py` | Full experiment: circuits, processors, compilation, noisy runs, tables, figures |
| `show_results.py` | Prints the main result table from the CSV |
| `qff_phase1_p3/processors/` | `processor_A.json`, `processor_B.json` |
| `qff_phase1_p3/results/tables/` | `AB_comparison.csv`, `all_transpile_runs.csv`, `optimization_summary.csv`, `scaling_study_optional.csv` |
| `qff_phase1_p3/results/figures/` | Processor graphs, two-qubit gates vs bits, depth vs bits, noisy success, optional scaling |
| `report.md` | Analysis, interpretation and limitations |
| `requirements.txt` | Python dependencies |

## Method (short)

1. Build each circuit and prepare the test input with X gates (barriers keep the input preparation separate from the arithmetic circuit).
2. Compile for each processor with its coupling map and basis gates. **Baseline:** optimization level 1, seed 42. **Optimized:** best of 10 transpiler seeds at level 3 (fewest two-qubit gates, then lowest depth).
3. Record depth, two-qubit gates, SWAP count (from a second compile that keeps SWAP gates), and the extra two-qubit gates compared with an all-to-all compile of the same circuit.
4. Run on an ideal and a noisy Aer simulator (2048 shots, seed 42) and record the probability of the correct result with its standard error sqrt(p(1-p)/N).

## Key results

See `report.md` for the full table and interpretation, and `qff_phase1_p3/results/tables/AB_comparison.csv` for all numbers.

## AI assistance disclosure

An AI assistant (Claude, by Anthropic) was used to help plan the approach, draft the code and draft documentation. The team ran the code, checked the outputs and takes responsibility for the submitted work.
