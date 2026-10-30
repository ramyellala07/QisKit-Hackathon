# QFF 2026 Phase 1: P3 Reversible Quantum Arithmetic & Carry-Chain Bottlenecks

**Team:** EchoNova | **Problem statement:** PS-P3, hardware routing benchmark of quantum adders and multipliers | **Framework:** Qiskit (transpile + Aer simulation)

---

## 1. Problem and approach

Quantum arithmetic circuits (adders, multipliers) rely on a *carry chain*: each bit's result depends on the carry from the bit before it. On real hardware, qubits can only interact with their neighbours on the coupling graph, so the carry chain forces extra SWAP gates, which add depth and noise.

We implemented three circuits and benchmarked them on two processors:

| Circuit | Idea | Interaction pattern |
|---|---|---|
| CDKM ripple-carry adder | MAJ/UMA blocks pass the carry from bit to bit | local, but each block needs a triangle of 3 qubits |
| Draper QFT adder | add in the Fourier basis using controlled phases | dense, every bit of one register touches every bit of the other |
| QFT multiplier | repeated QFT-based addition | dense |

| Processor | Qubits | Coupling graph |
|---|---|---|
| A | 5 | "bowtie": two triangles sharing one hub qubit |
| B | 7 | heavy-hex style: low degree (max 3), no triangles |

Graphs are in `results/figures/processor_A_graph.png` and `processor_B_graph.png`.

For every (processor, circuit, bit-width) we ran two transpilation settings:

- **Baseline:** optimization level 1, seed 42.
- **Optimized:** optimization level 3, best result over 10 seeds.

## 2. Experimental setup and controls

- **Same experiment on A and B:** identical circuits, bit-widths, input sets, shots (2048 per run) and transpiler settings on both processors. Processor definitions are the organiser-supplied files in `processors/`.
- **Noise:** the common noise model from the Challenge Kit, applied identically to A and B. [CONFIRM: same noise values and basis gates on A and B]
- **Uncertainty:** standard error of a proportion, sqrt(p(1-p)/N) with N = 2048 shots.
- **Seeds:** baseline = optimization level 1, seed 42; optimized = level 3, best of 10 seeds.
- **Separating connectivity from gate set and noise:** the ideal (all-to-all) two-qubit gate count of each circuit is identical on A and B. Any extra gates therefore come only from routing on the coupling graph (columns "Extra 2q" and "SWAPs"). Since noise per gate is the same on both processors, the success difference follows from the number of noisy operations that routing added. The loss per two-qubit gate is about the same on A and B (about 0.66% and 0.65%), which supports this. This is one finite model, so it does not prove a general advantage of either graph.

## 3. Technical correctness

Every circuit returned the expected output in noiseless simulation: **ideal success = 1.0 in all 25 runs** (both input sets, both processors, both settings). Routing and optimization therefore never changed the function the circuit computes.

## 4. Benchmark results (optimized, level 3)

"Extra 2q" = two-qubit gates added by routing compared with an all-to-all processor. One SWAP is 3 CX gates.
Success = noisy-simulation success on the carry-chain input set, mean ± standard error.

**Processor A (5q bowtie)**

| Circuit | Bits | Qubits used (logical = physical; device has 5 or 7) | Depth | 2q gates | SWAPs | Extra 2q | Noisy success |
|---|---|---|---|---|---|---|---|
| CDKM adder | 1 | 3 | 29 | 16 | 0 | 0 | 0.9106 ± 0.0063 |
| CDKM adder | 2 | 5 | 58 | 32 | 0 | 0 | 0.8091 ± 0.0087 |
| Draper QFT adder | 1 | 2 | 3 | 1 | 0 | 0 | 0.9688 ± 0.0038 |
| Draper QFT adder | 2 | 4 | 29 | 8 | 0 | 0 | 0.9116 ± 0.0063 |
| QFT multiplier | 1 | 4 | 36 | 19 | 1 | 3 | 0.8730 ± 0.0074 |

**Processor B (7q heavy-hex style)**

| Circuit | Bits | Qubits used (logical = physical; device has 5 or 7) | Depth | 2q gates | SWAPs | Extra 2q | Noisy success |
|---|---|---|---|---|---|---|---|
| CDKM adder | 1 | 3 | 46 | 21 | 3 | 5 | 0.8901 ± 0.0069 |
| CDKM adder | 2 | 5 | 90 | 42 | 6 | 10 | 0.7725 ± 0.0093 |
| CDKM adder | 3 | 7 | 133 | 63 | 10 | 15 | 0.6626 ± 0.0104 |
| Draper QFT adder | 1 | 2 | 3 | 1 | 0 | 0 | 0.9727 ± 0.0036 |
| Draper QFT adder | 2 | 4 | 34 | 11 | 1 | 3 | 0.8931 ± 0.0068 |
| Draper QFT adder | 3 | 6 | 64 | 31 | 5 | 10 | 0.7695 ± 0.0093 |
| QFT multiplier | 1 | 4 | 53 | 23 | 3 | 7 | 0.8569 ± 0.0077 |

Figures: `depth_vs_bits.png`, `twoq_vs_bits.png`, `noisy_success.png`. Full data: `results/tables/AB_comparison.csv`, `all_transpile_runs.csv`.

## 5. Performance analysis

### 5.1 Connectivity decides the SWAP overhead

- **CDKM on A needs zero SWAPs** for 1-bit and 2-bit. Each MAJ/UMA block acts on three qubits that all interact, which is a triangle, and the bowtie is two triangles sharing a qubit. Depth equals the all-to-all depth (29 and 58).
- **CDKM on B needs SWAPs from the first bit** (3, 6, 10 for 1, 2, 3 bits). A heavy-hex style graph has no triangles, so every 3-qubit block must be rearranged. Optimized depth is about 1.5x the all-to-all depth (46 vs 29, 90 vs 58, 133 vs 87).
- **The QFT adder and multiplier** need dense interactions. On B the 3-bit QFT adder adds 10 extra 2q gates on top of 21 ideal (about 48% overhead), against 15 on 48 (about 31%) for the 3-bit CDKM adder. So the QFT adder is more sensitive to connectivity, even though it uses fewer gates in total (31 vs 63 two-qubit gates at 3 bits).

### 5.2 Gate count, depth and noise

- The cost of SWAP overhead grows with bit-width on B: extra 2q gates go 5, 10, 15 for CDKM and 0, 3, 10 for the QFT adder.
- Noisy success falls steadily with two-qubit gate count. Across A and B, CDKM results line up on roughly **0.65 to 0.66% success loss per two-qubit gate** (32 gates give 0.809 on A, 63 gates give 0.663 on B). This is why removing SWAPs matters.
- Differences smaller than about 2 standard errors are not meaningful. For example, the 1-bit QFT adder on A (0.9688) and B (0.9727) is a tie, as expected because neither needs routing.

### 5.3 Effect of optimization (level 3, best of 10 seeds)

| Circuit (B) | Bits | Extra 2q: baseline → optimized | Depth: baseline → optimized | Success: baseline → optimized |
|---|---|---|---|---|
| CDKM | 1 | 9 → 5 | 42 → 46 | 0.874 → 0.890 |
| CDKM | 2 | 18 → 10 | 82 → 90 | 0.743 → 0.773 |
| CDKM | 3 | 33 → 15 | 125 → 133 | 0.616 → 0.663 |
| QFT adder | 2 | 5 → 3 | 32 → 34 | 0.889 → 0.893 |
| QFT adder | 3 | 21 → 10 | 73 → 64 | 0.729 → 0.770 |
| QFT multiplier | 1 | 9 → 7 | 50 → 53 | 0.850 → 0.857 |

- Optimization cut routing overhead by 40 to 55% on B for the larger circuits. Success improved because fewer two-qubit gates matter more than depth.
- For CDKM it traded a slightly larger depth (+6 to 10%) for fewer 2q gates.
- On A, optimization changed nothing for CDKM, because the circuit already fits the graph without SWAPs.
- Across 10 seeds the two-qubit count is very stable (std 0 on A; at most 1.56 on B), see `optimization_summary.csv`. Results are not a lucky seed.

## 6. Limitations

- Sizes are small: the largest runs are 2-bit on A and 3-bit on B, and the multiplier is only run at 1 bit. Larger sizes do not fit in 5 or 7 qubits.
- Noise is simulated with a synthetic model, not measured on hardware, so absolute success values are indicative; the *trends* (SWAPs, gate count, success) are the finding.
- Success uses fixed input sets (carry-chain stress inputs and mixed inputs), not every possible input.

## 7. Problem faced and proposed Processor D

**Problem observed.** On A and B the carry chain either fits poorly (B, no triangles) or the processor is too small (A and B cannot hold larger adders or the 2-bit multiplier). On B, CDKM loses about 1.5x depth and a third to half of its 2q budget to routing.

**Proposal (not benchmarked in Phase 1).** Processor D: 9 qubits on a "triangle strip", where qubit *i* connects to *i+1* and *i+2*:

```
q0 - q1 - q2 - q3 - q4 - q5 - q6 - q7 - q8      (neighbour links)
q0 - q2, q1 - q3, q2 - q4, ... , q6 - q8         (skip-one links)
```

- Order the CDKM qubits as c0, b0, a0, b1, a1, b2, a2, ... Every MAJ/UMA block then acts on three consecutive qubits, which are mutually connected. **Expected: zero SWAPs for CDKM adders up to 4 bits**, with depth equal to the all-to-all depth.
- Max degree is 4, so it stays realistic for fixed-frequency hardware, unlike an all-to-all device.
- Projection for the 3-bit CDKM adder using the 0.65 to 0.66% per-gate loss from Section 5.2: 48 two-qubit gates (ideal) instead of 63 would give roughly **0.73 success vs 0.66 measured on B**.
- For the QFT adder and multiplier, add 2 or 3 long-range links across the strip (for example q0-q8 and q2-q6) to cut the SWAPs that the dense interaction pattern needs. We would evaluate this with the same scripts in Phase 2.

## 8. Reproducibility

```
pip install -r requirements.txt
python main_p3.py        # builds circuits, transpiles on A and B, runs noisy simulation, writes results/
python show_results.py   # prints and plots the saved results
```

- Baseline seed is 42. Optimized runs use 10 seeds and keep the best.
- Code: `circuit.py` (circuit builders), `main_p3.py` (benchmark), `show_results.py` (summaries).
- Outputs: `results/tables/*.csv`, `results/figures/*.png`.

## 9. AI assistance disclosure

An AI assistant (Claude, by Anthropic) was used to help write parts of the code and this report, and to explain concepts. The team ran the code, produced the results, and reviewed and takes responsibility for the submitted work.
