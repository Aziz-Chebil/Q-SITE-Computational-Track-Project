# Computational Track — Our Approach & Results

## Current Results (as of 2026-09-24)

| Benchmark | Qubits | 2Q Gates | Baseline | v1 (SA + greedy) | **v2 (current)** | Floor* |
|---|---|---|---|---|---|---|
| ghz_star | 8 | 7 | 14.0 | 8.5 | **6.5** | 3.5 |
| chain_trotter | 10 | 9 | 15.0 | 4.5 | **4.5** | 4.5 |
| ladder_trotter | 12 | 16 | 35.5 | 6.5 | **6.5** | 3.0 |
| qaoa_random | 10 | 18 | 39.0 | 14.0 | **12.0** | 4.0 |
| dense_random | 14 | 40 | 122.0 | 52.5 | **36.0** | 6.0 |
| vqe_layers | 16 | 45 | 58.0 | 3.0 | **3.0** | 3.0 |
| **TOTAL** | | | **283.5** | **89.0** | **68.5 (−76% vs baseline)** | 24.0 |

Scoring formula: `score = swap_count + 0.5 * depth` (lower is better). All solutions pass validation.
Results are deterministic (fixed seed); reproduce with `python evaluate.py`.

\*Floor = `0.5 × depth of the logical program` (zero SWAPs, perfect parallelism). No solution can go
below it, and it is usually unreachable. **chain_trotter and vqe_layers hit the floor, so they are
provably optimal.** ghz_star at 6.5 is also optimal: the hub has at most 3 hardware neighbours, so
reaching 7 leaves needs ≥2 hub moves, and each move is serial on the hub (depth ≥ 7 + 2 = 9).

---

## Pipeline

The solver lives in `solver.py` (a copy is pasted into cell 20 of `starter.ipynb` so the notebook
runs on its own). `evaluate.py` runs it on every benchmark and prints swaps, depth, score and runtime;
`python evaluate.py --robust` also checks unseen programs (single-qubit only, one gate, mixed 1Q/2Q,
random 16- and 20-qubit programs).

### 1. Placement candidates — Simulated Annealing on distance
- Precompute all-pairs shortest-path distances on the 20-qubit hardware graph.
- Cost = `sum of dist[placement[a]][placement[b]]` over every 2Q interaction.
- Seed: degree matching (busiest logical qubits → most central physical qubits), plus 149 random starts.
- Moves: swap two logical qubits' positions, **or move a logical qubit onto an unused physical qubit**
  (v1 could never reach free physical qubits after seeding). O(degree) delta computation.
- Keep the 30 best distinct placements.

### 2. SABRE-style bidirectional refinement
For each candidate: route forward, take the final placement, route the **reversed** program from it,
and use that final placement as a new initial placement (4 rounds). This moves qubits to where the
program actually needs them. Every placement seen is scored with the fast greedy router below.

### 3. Greedy look-ahead router (fast ranking, ~1 ms)
Gates in strict program order. For each non-adjacent gate, try every SWAP on an edge touching either
qubit and pick the one minimising `dist(current gate) + Σ W^k · dist(future gate k)` over the next 20 gates.

### 4. Depth-aware beam-search router (the main v2 gain)
The greedy router only looks at distance, but the score also pays for **depth**, and depth goes up
when SWAPs pile onto the same qubits. The beam router optimises the true score:
- A state holds the placement, the SWAP count, and **each physical qubit's last layer**, updated the
  same way `schedule_layers_ordered` does. That gives the exact `swaps + 0.5·depth` at every step.
- For each gate, states are expanded with distance-reducing SWAPs (so the swap count stays minimal
  for that gate). The beam decides **which** qubit moves and **along which path**, which is exactly
  what decides whether SWAPs can run in parallel.
- Ranking: `exact score so far + λ · Σ decay^k · (dist(future gate k) − 1)`.
  States with identical placements are merged, keeping the best.
- On random placements a wider beam helps a lot (e.g. 97.0 → 68.5 on dense_random).

### 5. Routing-aware placement polish
The distance cost from step 1 is only a proxy. Run SA whose cost is the **actual routed score**
(beam width 8, ~3.5 ms per call, results cached). There are 3 independent chains of 1500 iterations,
each with its own random stream, started from the 3 best placements, and the best result wins.
A single chain often gets stuck in a poor local optimum, so the best of several is more stable.
This step took dense_random from 47.0 to 36.0.

### 6. Final routing
Re-route the polished placements with a wide beam (width 256) under four settings: two λ/decay
pairs, plus up to 1 or 2 **sideways SWAPs** per gate. A sideways SWAP doesn't shorten the current
gate but does shorten one of the next 3 gates. Return the best `(placement, routed_program)` by
`core_score`. Sideways SWAPs help on some placements and hurt on others (10 wins / 9 losses on random
dense_random placements), so they are only an extra option here. Using them inside the polish loop
made results worse and ~2.5× slower. If a result already reaches the floor, the solver
stops early.

Runtime: 1–25 s per benchmark. `time_budget` (default 60 s) is a safety cap for large unseen programs.

---

## Ideas not implemented

- **Seed ensembles**: other seeds reach 35.5 on dense_random, but running several full seeds
  multiplies runtime, so we kept one fixed seed rather than tuning the seed to the benchmarks.
- **Stretch goals A/B** (decomposition, 1Q optimisation): the starter kit ships no decomposer or 1Q
  baseline to score against, so we could not measure a bonus.
- **Benchmark-specific tuning** of beam width, λ and polish length.

---

## Key Constraints

- `validate_routed_program` (`scorer.py:62-70`) checks that stripping SWAPs recovers the EXACT
  original program (same operations, same order, same qubit orientation). Gates cannot be reordered.
- Every `("2Q", p, q)` and `("SWAP", p, q)` must be on a hardware edge.
- The returned placement is the one BEFORE any SWAPs.
- Unoccupied physical qubits can be SWAP targets.

## Key Files

- `solver.py`: the solver (source of truth; mirrored in `starter.ipynb` cell 20)
- `evaluate.py`: benchmark + robustness harness
- `starter_kit/scorer.py`: validation, scheduling, scoring (not modified)
- `starter_kit/benchmarks.py`, `starter_kit/hardware.py`: benchmarks and the 20-qubit graph
