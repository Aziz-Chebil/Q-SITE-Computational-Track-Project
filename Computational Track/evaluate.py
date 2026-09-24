"""Run solve() on every benchmark and report validity, swaps, depth, score and runtime."""

import random
import sys
import time

from starter_kit import BENCHMARKS, build_hardware_graph, score_summary
from solver import solve

PREVIOUS_TOTAL = 72.5
BASELINE_TOTAL = 283.5


def random_program(num_qubits, num_gates, seed, with_1q=False):
    rng = random.Random(seed)
    program = []
    for _ in range(num_gates):
        a, b = rng.sample(range(num_qubits), 2)
        program.append(("2Q", a, b))
        if with_1q and rng.random() < 0.3:
            program.append(("1Q", rng.randrange(num_qubits)))
    return program


def main():
    graph = build_hardware_graph()
    print(f"{'benchmark':16s} {'valid':5s} {'swaps':>5s} {'depth':>5s} {'score':>6s} {'time':>6s}")
    total = 0.0
    for name, program in BENCHMARKS.items():
        t = time.perf_counter()
        placement, routed = solve(program, graph)
        elapsed = time.perf_counter() - t
        s = score_summary(program, graph, placement, routed)
        total += s["score"]
        print(f"{name:16s} {str(s['valid']):5s} {s['swap_count']:5d} {s['depth']:5d} {s['score']:6.1f} {elapsed:5.1f}s")
    print(f"{'TOTAL':16s} {'':5s} {'':5s} {'':5s} {total:6.1f}   (previous {PREVIOUS_TOTAL}, baseline {BASELINE_TOTAL})")

    if "--robust" in sys.argv:
        print("\nRobustness checks on unseen programs:")
        extra = {
            "single_1q": [("1Q", 0)],
            "one_gate": [("2Q", 3, 1)],
            "mixed_1q": random_program(10, 25, seed=1, with_1q=True),
            "rand_16q_60g": random_program(16, 60, seed=2),
            "rand_20q_80g": random_program(20, 80, seed=3),
        }
        for name, program in extra.items():
            t = time.perf_counter()
            placement, routed = solve(program, graph)
            s = score_summary(program, graph, placement, routed)
            print(f"{name:16s} valid={s['valid']} score={s['score']:.1f} time={time.perf_counter() - t:.1f}s")
            assert s["valid"], s["message"]


if __name__ == "__main__":
    main()
