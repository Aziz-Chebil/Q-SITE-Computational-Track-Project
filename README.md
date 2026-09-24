# Quantum Coalition QSITE 2026 Challenge

Hi, I am Aziz Chebil, an MSc. in CS & Math at Télécom Paris, France.
I worked on the computational track.

What I did this week: simulated annealing proposes placements that minimise summed hardware distance over all 2Q interactions. Each is refined SABRE-style: route forward, route the reversed program back, and reuse the final placement. Routing walks the gates in strict program order, which the scorer requires. A beam search picks which qubit moves and along which path, tracking each qubit's layer so it optimises the exact `swaps + 0.5·depth`, not just distance. Finally, a
second annealing pass tunes the placement against the actual routed score, and the best `(placement, routing)` pair is returned.

Here are my results on the six benchmarks:

| Benchmark | Qubits | 2Q Gates | Baseline | Ours | Improvement | Floor* |
|---|---|---|---|---|---|---|
| ghz_star | 8 | 7 | 14.0 | 6.5 | −7.5 | 3.5 |
| chain_trotter | 10 | 9 | 15.0 | 4.5 | −10.5 | 4.5 |
| ladder_trotter | 12 | 16 | 35.5 | 6.5 | −29.0 | 3.0 |
| qaoa_random | 10 | 18 | 39.0 | 12.0 | −27.0 | 4.0 |
| dense_random | 14 | 40 | 122.0 | 36.0 | −86.0 | 6.0 |
| vqe_layers | 16 | 45 | 58.0 | 3.0 | −55.0 | 3.0 |
| **TOTAL** | | | **283.5** | **68.5** | **−215.0 (76%)** | 24.0 |

The demo video can be found in the [Computational Track/video](./Computational%20Track/video).

You can also watch it on [YouTube](https://www.youtube.com/watch?v=t-7HvfPSCiM).

The writeup document can be found in [Computational Track/writeup/writeup.pdf](./Computational%20Track/writeup/writeup.pdf).
