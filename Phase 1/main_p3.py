import json, os, csv, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import CDKMRippleCarryAdder, DraperQFTAdder, RGQFTMultiplier
from qiskit.transpiler import CouplingMap
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError

SEED = 42
SHOTS = 2048
N_SEEDS = 10          # transpiler seeds for the optimization search (main benchmark)
N_SEEDS_SCALE = 5     # transpiler seeds for the optional scaling study
OUT = "qff_phase1_p3"
for d in ["processors", "results/tables", "results/figures"]:
    os.makedirs(OUT + "/" + d, exist_ok=True)
FIG = OUT + "/results/figures/"
TAB = OUT + "/results/tables/"

# ---------- 1. Processors A and B (our definitions) ----------
processor_A = {"name": "A_bowtie_5q", "num_qubits": 5,
    "coupling_map": [[0,1],[0,2],[1,2],[2,3],[2,4],[3,4]],
    "basis_gates": ["rz","sx","x","cx"],
    "noise": {"one_qubit_error": 0.001, "two_qubit_error": 0.01, "readout_error": 0.02}}
processor_B = {"name": "B_heavyhex_7q", "num_qubits": 7,
    "coupling_map": [[0,1],[1,2],[1,3],[3,5],[4,5],[5,6]],
    "basis_gates": ["rz","sx","x","cx"],
    "noise": {"one_qubit_error": 0.001, "two_qubit_error": 0.01, "readout_error": 0.02}}
PROCS = [processor_A, processor_B]
for p, f in [(processor_A, "processor_A.json"), (processor_B, "processor_B.json")]:
    with open(OUT + "/processors/" + f, "w") as file:
        json.dump(p, file, indent=2)

def get_cmap(p):
    edges = set(tuple(e) for e in p["coupling_map"])
    edges |= set((b, a) for a, b in edges)
    return CouplingMap([list(e) for e in sorted(edges)])

def make_noise(p):
    e = p["noise"]
    nm = NoiseModel()
    nm.add_all_qubit_quantum_error(depolarizing_error(e["one_qubit_error"], 1), ["sx", "x"])
    nm.add_all_qubit_quantum_error(depolarizing_error(e["two_qubit_error"], 2), ["cx"])
    r = e["readout_error"]
    nm.add_all_qubit_readout_error(ReadoutError([[1-r, r], [r, 1-r]]))
    return nm

# ---------- 2. Circuits: modular adders and a multiplier ----------
KINDS = ["CDKM ripple-carry adder", "Draper QFT adder", "QFT multiplier"]

def make_spec(kind, n):
    if kind == "CDKM ripple-carry adder":
        c = CDKMRippleCarryAdder(n, kind="fixed")          # a + b mod 2^n, result in b
        return {"circuit": c, "a": list(range(n)), "b": list(range(n, 2*n)),
                "out": list(range(n, 2*n)), "expected": lambda a, b: (a + b) % (2**n)}
    if kind == "Draper QFT adder":
        c = DraperQFTAdder(n, kind="fixed")
        return {"circuit": c, "a": list(range(n)), "b": list(range(n, 2*n)),
                "out": list(range(n, 2*n)), "expected": lambda a, b: (a + b) % (2**n)}
    c = RGQFTMultiplier(n)                                  # a * b, result in 'out' (2n bits)
    return {"circuit": c, "a": list(range(n)), "b": list(range(n, 2*n)),
            "out": list(range(2*n, 4*n)), "expected": lambda a, b: a * b}

def test_inputs(n):
    mask = 2**n - 1
    return {"carry_chain": (mask, 1),                       # all ones + 1: carry travels the whole chain
            "mixed": (0b010101 & mask, 0b101010 & mask)}

def build_test(spec, a_val, b_val):
    c = spec["circuit"]
    qc = QuantumCircuit(c.num_qubits, len(spec["out"]))
    for i, q in enumerate(spec["a"]):
        if (a_val >> i) & 1: qc.x(q)
    for i, q in enumerate(spec["b"]):
        if (b_val >> i) & 1: qc.x(q)
    qc.barrier()
    qc.compose(c, qubits=range(c.num_qubits), inplace=True)
    qc.barrier()
    qc.measure(spec["out"], range(len(spec["out"])))
    return qc

# ---------- 3. Compile + run helpers ----------
def compile_to(qc, cmap, basis, level, seed, keep_swap=False):
    b = basis + (["swap"] if keep_swap else [])
    return transpile(qc, coupling_map=cmap, basis_gates=b,
                     optimization_level=level, seed_transpiler=seed)

def compile_metrics(qc, cmap, basis, level, seed):
    c = compile_to(qc, cmap, basis, level, seed)
    s = compile_to(qc, cmap, basis, level, seed, keep_swap=True)
    return c, {"depth": c.depth(), "two_qubit_gates": c.count_ops().get("cx", 0),
               "swap_count": s.count_ops().get("swap", 0)}

def success(counts, expected_value):
    total = sum(counts.values())
    good = sum(n for k, n in counts.items() if int(k, 2) == expected_value)
    ps = good / total
    return ps, math.sqrt(ps * (1 - ps) / total)

def run_ideal(c):
    return AerSimulator(seed_simulator=SEED).run(c, shots=SHOTS).result().get_counts()

def run_noisy(c, p):
    sim = AerSimulator(noise_model=make_noise(p), seed_simulator=SEED)
    return sim.run(c, shots=SHOTS).result().get_counts()

def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

# ---------- 4. Main A/B benchmark ----------
seed_rows = []     # every compile (level 3, each seed)
final_rows = []    # baseline vs optimized with quality
for p in PROCS:
    cmap = get_cmap(p)
    basis = p["basis_gates"]
    for kind in KINDS:
        for n in range(1, 4):
            spec = make_spec(kind, n)
            nq = spec["circuit"].num_qubits
            if nq > p["num_qubits"]:
                continue
            inputs = test_inputs(n)
            carry = build_test(spec, *inputs["carry_chain"])
            # routing-free reference: same decomposition, all-to-all connectivity
            ref = compile_to(carry, None, basis, 3, SEED)
            ref_cx, ref_depth = ref.count_ops().get("cx", 0), ref.depth()

            best_key, best_seed = None, 0
            for s in range(N_SEEDS):
                c, m = compile_metrics(carry, cmap, basis, 3, s)
                seed_rows.append({"processor": p["name"], "circuit": kind, "n_bits": n,
                                  "seed": s, **m})
                key = (m["two_qubit_gates"], m["depth"])
                if best_key is None or key < best_key:
                    best_key, best_seed = key, s

            for version, level, seed in [("baseline (level 1, seed 42)", 1, SEED),
                                         ("optimized (level 3, best seed)", 3, best_seed)]:
                c, m = compile_metrics(carry, cmap, basis, level, seed)
                row = {"processor": p["name"], "circuit": kind, "n_bits": n,
                       "logical_qubits": nq, "version": version, "level": level, "seed": seed,
                       "depth": m["depth"], "two_qubit_gates": m["two_qubit_gates"],
                       "swap_count": m["swap_count"],
                       "all_to_all_2q_gates": ref_cx,
                       "extra_2q_from_routing": m["two_qubit_gates"] - ref_cx,
                       "all_to_all_depth": ref_depth}
                for name, (a, b) in inputs.items():
                    ci = compile_to(build_test(spec, a, b), cmap, basis, level, seed)
                    exp = spec["expected"](a, b)
                    pi, _ = success(run_ideal(ci), exp)
                    pn, se = success(run_noisy(ci, p), exp)
                    row["ideal_success_" + name] = round(pi, 4)
                    row["noisy_success_" + name] = round(pn, 4)
                    row["noisy_success_se_" + name] = round(se, 4)
                final_rows.append(row)
                print(row["processor"], kind, n, version, "depth", row["depth"],
                      "2q", row["two_qubit_gates"], "swaps", row["swap_count"],
                      "noisy(carry)", row["noisy_success_carry_chain"])

write_csv(TAB + "all_transpile_runs.csv", seed_rows)
write_csv(TAB + "AB_comparison.csv", final_rows)

summary = []
keys = sorted(set((r["processor"], r["circuit"], r["n_bits"]) for r in seed_rows))
for (pn, kd, n) in keys:
    rs = [r for r in seed_rows if (r["processor"], r["circuit"], r["n_bits"]) == (pn, kd, n)]
    cx = [r["two_qubit_gates"] for r in rs]; dp = [r["depth"] for r in rs]
    summary.append({"processor": pn, "circuit": kd, "n_bits": n, "n_seeds": len(rs),
                    "2q_mean": round(float(np.mean(cx)), 2), "2q_std": round(float(np.std(cx)), 2),
                    "2q_min": min(cx), "depth_mean": round(float(np.mean(dp)), 2),
                    "depth_min": min(dp)})
write_csv(TAB + "optimization_summary.csv", summary)

# ---------- 5. OPTIONAL scaling study on larger generic maps (metrics only) ----------
scale_maps = {"line_12": CouplingMap.from_line(12), "heavyhex_19": CouplingMap.from_heavy_hex(3)}
scale_rows = []
for mname, cmap in scale_maps.items():
    for kind in KINDS:
        for n in range(1, 6):
            spec = make_spec(kind, n)
            nq = spec["circuit"].num_qubits
            if nq > cmap.size():
                continue
            carry = build_test(spec, *test_inputs(n)["carry_chain"])
            best = None
            for s in range(N_SEEDS_SCALE):
                c, m = compile_metrics(carry, cmap, ["rz","sx","x","cx"], 3, s)
                key = (m["two_qubit_gates"], m["depth"])
                if best is None or key < best[0]:
                    best = (key, m)
            ref = compile_to(carry, None, ["rz","sx","x","cx"], 3, SEED)
            scale_rows.append({"map": mname, "circuit": kind, "n_bits": n, "logical_qubits": nq,
                               "depth": best[1]["depth"], "two_qubit_gates": best[1]["two_qubit_gates"],
                               "swap_count": best[1]["swap_count"],
                               "all_to_all_2q_gates": ref.count_ops().get("cx", 0)})
            print("scale", mname, kind, n, best[1])
write_csv(TAB + "scaling_study_optional.csv", scale_rows)

# ---------- 6. Figures ----------
opt = [r for r in final_rows if r["version"].startswith("optimized")]
colors = {"CDKM ripple-carry adder": "tab:blue", "Draper QFT adder": "tab:orange"}
styles = {"A_bowtie_5q": "-", "B_heavyhex_7q": "--"}

for field, title, fname in [("two_qubit_gates", "Two-qubit gates (optimized)", "twoq_vs_bits.png"),
                            ("depth", "Circuit depth (optimized)", "depth_vs_bits.png")]:
    plt.figure(figsize=(7, 4))
    for p in PROCS:
        for kind in ["CDKM ripple-carry adder", "Draper QFT adder"]:
            rs = sorted([r for r in opt if r["processor"] == p["name"] and r["circuit"] == kind],
                        key=lambda r: r["n_bits"])
            if rs:
                plt.plot([r["n_bits"] for r in rs], [r[field] for r in rs], styles[p["name"]],
                         marker="o", color=colors[kind], label=p["name"][:1] + " - " + kind)
    plt.xlabel("Register width n (bits)"); plt.ylabel(field.replace("_", " "))
    plt.title(title); plt.xticks([1, 2, 3]); plt.legend(fontsize=8); plt.tight_layout()
    plt.savefig(FIG + fname, dpi=150); plt.close()

plt.figure(figsize=(9, 4))
labels = [r["processor"][:1] + " " + r["circuit"].split()[0] + " n=" + str(r["n_bits"]) for r in opt]
x = np.arange(len(opt))
plt.bar(x - 0.2, [r["noisy_success_carry_chain"] for r in opt], 0.4,
        yerr=[r["noisy_success_se_carry_chain"] for r in opt], capsize=2, label="carry-chain input")
plt.bar(x + 0.2, [r["noisy_success_mixed"] for r in opt], 0.4,
        yerr=[r["noisy_success_se_mixed"] for r in opt], capsize=2, label="mixed input")
plt.xticks(x, labels, rotation=60, ha="right", fontsize=7)
plt.ylabel("P(correct result), noisy"); plt.title("Correctness under noise (optimized circuits)")
plt.legend(); plt.tight_layout(); plt.savefig(FIG + "noisy_success.png", dpi=150); plt.close()

fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=False)
for ax, mname in zip(axes, scale_maps):
    for kind in KINDS[:2]:
        rs = sorted([r for r in scale_rows if r["map"] == mname and r["circuit"] == kind],
                    key=lambda r: r["n_bits"])
        ax.plot([r["n_bits"] for r in rs], [r["two_qubit_gates"] for r in rs], marker="o",
                color=colors[kind], label=kind)
        ax.plot([r["n_bits"] for r in rs], [r["all_to_all_2q_gates"] for r in rs], ":",
                color=colors[kind], label=kind + " (all-to-all)")
    ax.set_title("Optional scaling: " + mname); ax.set_xlabel("n bits"); ax.set_ylabel("two-qubit gates")
    ax.legend(fontsize=7)
plt.tight_layout(); plt.savefig(FIG + "scaling_optional.png", dpi=150); plt.close()

for name, p in [("A", processor_A), ("B", processor_B)]:
    plt.figure(figsize=(4, 3))
    g = nx.Graph(); g.add_edges_from(p["coupling_map"])
    nx.draw(g, with_labels=True, node_size=700)
    plt.title("Processor " + name)
    plt.savefig(FIG + "processor_" + name + "_graph.png", dpi=150); plt.close()

print("Done. Check the", OUT, "folder.")
