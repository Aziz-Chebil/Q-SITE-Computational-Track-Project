# Computational Track — Our Approach & Results

## Current Results (as of 2026-09-21)

| Benchmark | Qubits | 2Q Gates | Baseline Score | Our Score | Improvement |
|---|---|---|---|---|---|
| ghz_star | 8 | 7 | 14.0 | 8.5 | -5.5 |
| chain_trotter | 10 | 9 | 15.0 | 4.5 | -10.5 |
| ladder_trotter | 12 | 16 | 35.5 | 6.5 | -29.0 |
| qaoa_random | 10 | 18 | 39.0 | 14.0 | -25.0 |
| dense_random | 14 | 40 | 122.0 | 52.5 | -69.5 |
| vqe_layers | 16 | 45 | 58.0 | 3.0 | -55.0 |
| **TOTAL** | | | **283.5** | **89.0** | **-194.5 (69%)** |

Scoring formula: `score = swap_count + 0.5 * depth` (lower is better).

All solutions pass validation.

---

## What Was Implemented

The `solve()` function lives in `starter.ipynb` (the cell after the "Your Submission" markdown). It has two main components:

### 1. Placement — Simulated Annealing

**Goal**: Map logical qubits to physical qubits so that frequently-interacting pairs are close on the hardware graph.

**How it works**:
- Precompute all-pairs shortest path distances on the 20-qubit hardware graph (instant, only 20 nodes).
- Build an interaction list from the program: every `("2Q", a, b)` contributes one `(a, b)` pair.
- Cost function: `sum of dist[placement[a]][placement[b]]` for every 2Q interaction. This is a proxy for how many SWAPs the router will need.
- Seed placement: degree-matching heuristic — sort logical qubits by interaction count (descending), sort physical qubits by closeness centrality (descending), zip them together.
- SA loop (3000 iterations per run): randomly swap two logical qubits' physical assignments, accept if cost decreases or with Boltzmann probability `exp(-delta/T)`. Cooling: `T *= 0.997`.
- Efficient delta computation: only recompute terms involving the two swapped qubits (O(degree) instead of O(total_interactions)).
- Multi-seed: 10 global random seeds x 15 SA restarts each = 150 SA runs total. Keep the top-5 placements per seed by placement cost.

### 2. Routing — Look-ahead Greedy

**Goal**: Insert SWAPs to make each 2Q gate act on adjacent physical qubits, choosing SWAPs that help future gates too.

**How it works**:
- Process gates strictly in program order (required by the scorer's validation, which checks that stripping SWAPs recovers the exact original program).
- For each 2Q gate where the two qubits are not adjacent:
  - Generate SWAP candidates: all hardware edges touching either of the two involved physical qubits.
  - Score each candidate SWAP with a heuristic: `H = dist_current_gate_after_swap + W * sum(decay^k * dist_future_gate_k)` where `decay = W` and `k` ranges over the next 20 future 2Q gates.
  - Apply the SWAP with the lowest H. Update both `placement` (logical->physical) and `reverse_placement` (physical->logical).
  - Repeat until the gate is on adjacent qubits.
- Safety fallback: if >40 SWAPs are tried for a single gate (shouldn't happen), fall back to greedy shortest-path routing.

**Parameter sweep**: For each top placement, route with W in {0.3, 0.5, 0.7}. Keep the best (placement, routed_program) pair by `core_score`.

### 3. Selection

The overall search evaluates: 10 seeds x 5 top placements x 3 W values = 150 routing attempts per benchmark. The best by `core_score` is returned.

---

## What Was NOT Implemented (Potential Improvements)

### High-impact ideas

1. **SABRE algorithm (DAG-based front-layer routing)**: The current router processes gates sequentially in program order. True SABRE maintains a DAG of gate dependencies, identifies a "front layer" of executable gates, and can potentially reorder independent gates. However, the scorer requires exact program order preservation (`translated != program` check in `scorer.py:68`), which constrains reordering. A modified SABRE that respects this constraint but still uses front-layer-aware SWAP scoring could improve dense benchmarks.

2. **Bidirectional routing**: Run routing forward, capture the final placement, reverse the program, route again starting from that final placement, reverse the result. Take the better of forward/reverse. The original SABRE paper shows this significantly reduces SWAP count. This is straightforward to add.

3. **Routing-aware placement optimization**: Currently SA uses placement cost (sum of distances) as a proxy. Instead, run the actual router for each SA candidate and use the real `core_score` as the SA objective. This is slower but more accurate — the proxy doesn't account for gate ordering effects. Could be done for a final refinement pass on the top-K placements.

4. **Depth-aware SWAP selection**: The current heuristic only considers SWAP count (distance). Adding a term that penalizes SWAPs which increase depth (by creating long sequential chains on the same qubits) could reduce the depth component of the score. The scheduler `schedule_layers_ordered` packs gates greedily — choosing SWAPs that land on different qubits enables more parallelism.

5. **Expanding SWAP candidates**: Currently only edges touching the two involved physical qubits are considered. Expanding to 2-hop neighbors or even all 23 hardware edges might find SWAPs that help future gates at the cost of a detour for the current gate.

### Medium-impact ideas

6. **Stretch Goal A — Gate decomposition**: The scorer has a stretch goal for improving the decomposer. Improving decomposition by N gates gives `N * 0.1` bonus. Not yet attempted.

7. **Stretch Goal B — Single-qubit gate optimization**: Fuse/cancel redundant 1Q gates. Not yet attempted. PennyLane's `qml.compile` with `cancel_inverses` and `merge_rotations` transforms could help.

8. **Benchmark-specific tuning**: Different benchmarks have different structures (star, chain, ladder, random, repeating layers). The SA and routing parameters could be tuned per-benchmark type. For example, `vqe_layers` has a very regular repeating structure that might benefit from a specialized placement strategy.

### Lower-impact ideas

9. **More SA iterations/restarts**: Diminishing returns, but the current 3000 iterations per run may not fully converge for larger benchmarks.

10. **Genetic algorithms for placement**: Instead of SA, use a population-based approach that combines good placements via crossover.

---

## Key Files

- `starter.ipynb` — the notebook with our `solve()` function and test harness
- `starter_kit/scorer.py` — validation, scheduling, scoring (DO NOT MODIFY)
- `starter_kit/baseline_routing.py` — the baseline we're beating (reference implementation)
- `starter_kit/benchmarks.py` — benchmark program definitions
- `starter_kit/hardware.py` — 20-qubit hardware graph definition
- `README.md` — full problem description and algorithm references

## Key Constraints

- The `validate_routed_program` function in `scorer.py:62-70` checks that stripping SWAPs from the routed program recovers the EXACT original program (same operations, same order). This means gates cannot be reordered even if they are independent.
- Every `("2Q", p, q)` in the routed program must satisfy `hardware_graph.has_edge(p, q)`.
- Every `("SWAP", p, q)` must also be on a valid hardware edge.
- The returned `initial_placement` must be the placement BEFORE any routing (not the final placement after SWAPs).
- Physical qubits not assigned to any logical qubit can still be SWAP targets. The reverse_placement dict handles this with `.get()` returning None.
