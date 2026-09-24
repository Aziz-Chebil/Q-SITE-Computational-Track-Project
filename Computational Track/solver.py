"""SA placement + depth-aware beam-search routing for the Computational Track.

Pipeline:
  1. Placement candidates from simulated annealing on summed hardware distance.
  2. SABRE-style bidirectional refinement: route forward, route the reversed
     program from the final placement, reuse that final placement as a new start.
  3. Fast greedy look-ahead router ranks all candidate placements.
  4. The best few are re-routed with a beam search that optimises the exact
     score (swaps + 0.5 * depth) instead of a distance-only proxy.
  5. Placement polish: SA over placements scored by actually routing them.
  6. Final wide-beam routing of the polished placements, optionally allowing
     "sideways" SWAPs that set up upcoming gates.
"""

import math
import random
import time
from collections import defaultdict

import networkx as nx

from starter_kit import core_score, schedule_layers_ordered


def _apply_swap(placement, rev, p1, p2):
    l1 = rev.get(p1)
    l2 = rev.get(p2)
    rev[p1], rev[p2] = l2, l1
    if l1 is not None:
        placement[l1] = p2
    if l2 is not None:
        placement[l2] = p1


def greedy_route(program, graph, dist, init_pl, lookahead=20, W=0.5):
    """Route in program order; each SWAP minimises current + decayed future distance.

    Returns (routed_program, final_placement).
    """
    placement = init_pl.copy()
    rev = {p: l for l, p in placement.items()}
    routed = []

    for idx, op in enumerate(program):
        if op[0] == "1Q":
            routed.append(("1Q", placement[op[1]]))
            continue

        a, b = op[1], op[2]
        safety = 0
        while not graph.has_edge(placement[a], placement[b]):
            safety += 1
            if safety > 40:
                # Fallback: greedy shortest path
                path = nx.shortest_path(graph, placement[a], placement[b])
                for left, right in zip(path[:-2], path[1:-1]):
                    routed.append(("SWAP", left, right))
                    _apply_swap(placement, rev, left, right)
                break

            pa, pb = placement[a], placement[b]
            candidates = set()
            for p in (pa, pb):
                for nbr in graph.neighbors(p):
                    candidates.add((min(p, nbr), max(p, nbr)))

            best_swap = None
            best_h = float("inf")
            for s1, s2 in sorted(candidates):
                ea = s2 if pa == s1 else (s1 if pa == s2 else pa)
                eb = s2 if pb == s1 else (s1 if pb == s2 else pb)
                h = dist[ea][eb]

                count = 0
                decay = 1.0
                for j in range(idx + 1, len(program)):
                    if program[j][0] != "2Q":
                        continue
                    paj, pbj = placement[program[j][1]], placement[program[j][2]]
                    eaj = s2 if paj == s1 else (s1 if paj == s2 else paj)
                    ebj = s2 if pbj == s1 else (s1 if pbj == s2 else pbj)
                    decay *= W
                    h += decay * dist[eaj][ebj]
                    count += 1
                    if count >= lookahead:
                        break

                if h < best_h:
                    best_h = h
                    best_swap = (s1, s2)

            routed.append(("SWAP", *best_swap))
            _apply_swap(placement, rev, *best_swap)

        routed.append(("2Q", placement[a], placement[b]))

    return routed, placement


def beam_route(program, graph, dist, init_pl, width=32, lam=1.0, decay=0.7, K=12, slack=0, ahead=3):
    """Beam search over SWAP sequences, ranked by exact score so far + look-ahead.

    Each 2Q gate is routed with distance-reducing SWAPs only (minimal swaps for
    that gate), but the beam explores which qubit moves and along which path,
    tracking per-qubit layer counts so depth is scored exactly as the scorer does.

    With slack > 0, up to `slack` extra SWAPs per gate may be spent on moves that do
    not shorten the current gate but do shorten one of the next `ahead` gates.
    """
    logical = sorted(init_pl)
    index = {l: i for i, l in enumerate(logical)}
    n_phys = max(graph.nodes) + 1
    nbrs = {p: list(graph.neighbors(p)) for p in graph.nodes}
    adjacent = {(u, v) for u, v in graph.edges} | {(v, u) for u, v in graph.edges}

    prog = []
    for op in program:
        if op[0] == "1Q":
            prog.append(("1Q", index[op[1]]))
        else:
            prog.append(("2Q", index[op[1]], index[op[2]]))

    # Upcoming 2Q gates (with decay weights) after each position
    weights = [decay ** (k + 1) for k in range(K)]
    future = []
    twoq = [(i, op[1], op[2]) for i, op in enumerate(prog) if op[0] == "2Q"]
    ptr = 0
    for i in range(len(prog)):
        while ptr < len(twoq) and twoq[ptr][0] <= i:
            ptr += 1
        future.append([(a, b) for _, a, b in twoq[ptr:ptr + K]])

    def rank(pos, swaps, depth, gate, fut):
        h = 0.0
        if gate is not None:
            h += dist[pos[gate[0]]][pos[gate[1]]] - 1
        for w, (x, y) in zip(weights, fut):
            h += w * (dist[pos[x]][pos[y]] - 1)
        return swaps + 0.5 * depth + lam * h

    pos0 = [init_pl[l] for l in logical]
    rev0 = [-1] * n_phys
    for i, p in enumerate(pos0):
        rev0[p] = i
    # state: (pos, rev, last_layer, swaps, depth, op_chain)
    beam = [(pos0, rev0, [0] * n_phys, 0, 0, None)]

    for i, op in enumerate(prog):
        if op[0] == "1Q":
            q = op[1]
            beam = [(pos, rev, last, sw, dp, (("1Q", pos[q]), chain))
                    for pos, rev, last, sw, dp, chain in beam]
            continue

        a, b = op[1], op[2]
        fut = future[i]
        done = {}
        frontier = [s + (0,) for s in beam]
        near = fut[:ahead]
        while frontier:
            nxt = {}
            for pos, rev, last, sw, dp, chain, extra in frontier:
                pa, pb = pos[a], pos[b]
                if (pa, pb) in adjacent:
                    layer = max(last[pa], last[pb]) + 1
                    last2 = last[:]
                    last2[pa] = last2[pb] = layer
                    dp2 = max(dp, layer)
                    key = tuple(pos)
                    r = rank(pos, sw, dp2, None, fut)
                    if key not in done or r < done[key][0]:
                        done[key] = (r, (pos, rev, last2, sw, dp2, (("2Q", pa, pb), chain)))
                    continue

                d = dist[pa][pb]
                moves = [(p, q, False) for p in (pa, pb) for q in nbrs[p]]
                if extra < slack:
                    for x, y in near:
                        for p in (pos[x], pos[y]):
                            moves.extend((p, q, True) for q in nbrs[p])
                for p, q, sideways in moves:
                    ea = q if pa == p else (p if pa == q else pa)
                    eb = q if pb == p else (p if pb == q else pb)
                    extra2 = extra
                    if dist[ea][eb] >= d:
                        if not sideways or dist[ea][eb] > d:
                            continue
                        # Only worth it if it shortens an upcoming gate
                        if not any(
                            dist[q if pos[x] == p else (p if pos[x] == q else pos[x])]
                                [q if pos[y] == p else (p if pos[y] == q else pos[y])]
                            < dist[pos[x]][pos[y]]
                            for x, y in near
                        ):
                            continue
                        extra2 = extra + 1
                    pos2 = pos[:]
                    rev2 = rev[:]
                    lp, lq = rev[p], rev[q]
                    rev2[p], rev2[q] = lq, lp
                    if lp >= 0:
                        pos2[lp] = q
                    if lq >= 0:
                        pos2[lq] = p
                    layer = max(last[p], last[q]) + 1
                    last2 = last[:]
                    last2[p] = last2[q] = layer
                    dp2 = max(dp, layer)
                    key = tuple(pos2)
                    r = rank(pos2, sw + 1, dp2, (a, b), fut)
                    if key not in nxt or r < nxt[key][0]:
                        nxt[key] = (r, (pos2, rev2, last2, sw + 1, dp2, (("SWAP", p, q), chain), extra2))
            frontier = [s for _, s in sorted(nxt.values(), key=lambda x: x[0])[:width]]
        beam = [s for _, s in sorted(done.values(), key=lambda x: x[0])[:width]]

    best = min(beam, key=lambda s: s[3] + 0.5 * s[4])
    ops = []
    chain = best[5]
    while chain is not None:
        ops.append(chain[0])
        chain = chain[1]
    ops.reverse()
    return ops


def solve(program, hardware_graph, seed=0, time_budget=60.0, polish_chains=3, polish_iters=1500):
    """
    Simulated-annealing placement + bidirectional refinement + beam-search routing.

    Returns (initial_placement, routed_program); the best pair by core_score.
    """
    start = time.perf_counter()
    rng = random.Random(seed)

    dist = dict(nx.all_pairs_shortest_path_length(hardware_graph))
    logical_qubits = sorted({q for op in program for q in op[1:]})
    physical_qubits = sorted(hardware_graph.nodes)
    n_logical = len(logical_qubits)

    interactions = [(op[1], op[2]) for op in program if op[0] == "2Q"]
    interactions_of = defaultdict(list)
    for a, b in interactions:
        interactions_of[a].append(b)
        interactions_of[b].append(a)

    # Degree-matching seed: high-interaction logical qubits -> central physical qubits
    centrality = nx.closeness_centrality(hardware_graph)
    logical_degree = defaultdict(int)
    for a, b in interactions:
        logical_degree[a] += 1
        logical_degree[b] += 1
    sorted_logical = sorted(logical_qubits, key=lambda q: logical_degree[q], reverse=True)
    sorted_physical = sorted(physical_qubits, key=lambda q: centrality[q], reverse=True)
    seed_placement = dict(zip(sorted_logical, sorted_physical[:n_logical]))

    if not interactions:
        routed, _ = greedy_route(program, hardware_graph, dist, seed_placement)
        return seed_placement, routed

    def placement_cost(pl):
        return sum(dist[pl[a]][pl[b]] for a, b in interactions)

    def run_sa(seed_pl, iterations=3000):
        """SA over placements; moves swap two logical qubits or relocate one to a free physical qubit."""
        current = seed_pl.copy()
        current_cost = placement_cost(current)
        best = current.copy()
        best_cost = current_cost
        T = max(current_cost * 0.3, 5.0)
        alpha = 0.997
        lq = list(current.keys())
        free = [p for p in physical_qubits if p not in set(current.values())]

        for _ in range(iterations):
            if free and (n_logical < 2 or rng.random() < 0.3):
                la = rng.choice(lq)
                fi = rng.randrange(len(free))
                pa, pf = current[la], free[fi]
                delta = sum(dist[pf][current[x]] - dist[pa][current[x]] for x in interactions_of[la])
                if delta <= 0 or rng.random() < math.exp(-delta / max(T, 1e-10)):
                    current[la], free[fi] = pf, pa
                    current_cost += delta
            elif n_logical >= 2:
                la, lb = rng.sample(lq, 2)
                pa, pb = current[la], current[lb]
                delta = 0
                for x in interactions_of[la]:
                    if x != lb:
                        delta += dist[pb][current[x]] - dist[pa][current[x]]
                for x in interactions_of[lb]:
                    if x != la:
                        delta += dist[pa][current[x]] - dist[pb][current[x]]
                if delta <= 0 or rng.random() < math.exp(-delta / max(T, 1e-10)):
                    current[la], current[lb] = current[lb], current[la]
                    current_cost += delta
            if current_cost < best_cost:
                best_cost = current_cost
                best = current.copy()
            T *= alpha

        return best, best_cost

    # ── 1. SA placement candidates ────────────────────────────────────────
    sa_results = []
    for r in range(150):
        if r == 0:
            s = seed_placement.copy()
        else:
            s = dict(zip(logical_qubits, rng.sample(physical_qubits, n_logical)))
        sa_results.append(run_sa(s))
    sa_results.sort(key=lambda x: x[1])

    unique = {}
    for pl, cost in sa_results:
        unique.setdefault(tuple(sorted(pl.items())), pl)
    top_placements = list(unique.values())[:30]

    # ── 2. Greedy routing + bidirectional refinement ──────────────────────
    reversed_program = program[::-1]
    candidates = {}  # placement key -> (greedy score, placement, routed)

    def consider(pl, W):
        routed, final = greedy_route(program, hardware_graph, dist, pl, W=W)
        s = core_score(routed)
        key = tuple(sorted(pl.items()))
        if key not in candidates or s < candidates[key][0]:
            candidates[key] = (s, pl.copy(), routed)
        return final

    for pl in top_placements:
        for W in (0.3, 0.5, 0.7):
            consider(pl, W)
        current = pl
        for _ in range(4):
            final = consider(current, 0.5)
            _, current = greedy_route(reversed_program, hardware_graph, dist, final, W=0.5)
        consider(current, 0.5)
        if time.perf_counter() - start > time_budget * 0.3:
            break

    ranked = sorted(candidates.values(), key=lambda x: x[0])
    best_score, best_pl, best_routed = ranked[0]

    # Zero SWAPs at the program's own dependency depth cannot be beaten
    lower_bound = 0.5 * len(schedule_layers_ordered(program))
    if best_score <= lower_bound:
        return best_pl, best_routed

    # ── 3. Beam-search routing on the most promising placements ───────────
    beam_ranked = []
    for _, pl, _ in ranked[:8]:
        routed = beam_route(program, hardware_graph, dist, pl, width=32)
        s = core_score(routed)
        beam_ranked.append((s, pl))
        if s < best_score:
            best_score, best_pl, best_routed = s, pl.copy(), routed
    beam_ranked.sort(key=lambda x: x[0])

    # ── 4. Routing-aware placement polish: SA on the true routed score ────
    # Several independent chains (own RNG stream each) from the best starts: a single
    # chain often stalls in a poor local optimum, the best of several is far more stable.
    score_cache = {}

    def routed_score(pl):
        key = tuple(sorted(pl.items()))
        if key not in score_cache:
            score_cache[key] = core_score(beam_route(program, hardware_graph, dist, pl, width=8))
        return score_cache[key]

    # Fixed iteration counts keep results reproducible; the deadline is only a safety cap
    polish_starts = [pl for _, pl in beam_ranked[:3]]
    deadline = start + time_budget * 0.85
    alpha = (0.05 / 1.0) ** (1.0 / polish_iters)
    polished = []
    for chain in range(polish_chains):
        chain_rng = random.Random(seed * 1000 + chain)
        current = polish_starts[chain % len(polish_starts)].copy()
        current_cost = routed_score(current)
        best_local, best_local_cost = current.copy(), current_cost
        T = 1.0
        for _ in range(polish_iters):
            if time.perf_counter() > deadline:
                break
            cand = current.copy()
            used = set(cand.values())
            free = [p for p in physical_qubits if p not in used]
            if free and (n_logical < 2 or chain_rng.random() < 0.3):
                cand[chain_rng.choice(logical_qubits)] = chain_rng.choice(free)
            elif n_logical >= 2:
                la, lb = chain_rng.sample(logical_qubits, 2)
                cand[la], cand[lb] = cand[lb], cand[la]
            cost = routed_score(cand)
            if cost <= current_cost or chain_rng.random() < math.exp(-(cost - current_cost) / T):
                current, current_cost = cand, cost
                if cost < best_local_cost:
                    best_local, best_local_cost = cand.copy(), cost
            T = max(T * alpha, 0.05)
        polished.append((best_local_cost, best_local))
    polished = [pl for _, pl in sorted(polished, key=lambda x: x[0])[:6]]

    # ── 5. Final wide-beam routing of the polished placements ─────────────
    for pl in polished + polish_starts:
        for lam, decay, slack in ((1.0, 0.7, 0), (0.5, 0.8, 0), (1.0, 0.7, 1), (1.0, 0.7, 2)):
            if time.perf_counter() - start > time_budget:
                break
            routed = beam_route(program, hardware_graph, dist, pl, width=256, lam=lam, decay=decay, slack=slack)
            s = core_score(routed)
            if s < best_score:
                best_score, best_pl, best_routed = s, pl.copy(), routed

    return best_pl, best_routed
