"""Build the 2-page technical write-up (writeup.pdf) and its figures (figs/*.png).

Numbers are the ones measured with solver.py / evaluate.py; routing time profiles are read
from routing_data.json (real v1 and v2 routings of dense_random).
Run with any Python that has matplotlib and reportlab:  python build_writeup.py
"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "figs")
os.makedirs(FIGS, exist_ok=True)
DATA = json.load(open(os.path.join(HERE, "routing_data.json")))

NAVY, INK, MUTED, AMBER, TEAL, RED, GREY, PAPER = "#172033", "#1B2336", "#5A6475", "#D9962B", "#2F9E8F", "#D0604E", "#A9B1BF", "#F5F2EB"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"],
    "font.size": 9,
    "axes.edgecolor": "#C9CED6",
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titleweight": "bold",
    "axes.titlesize": 10,
    "axes.titlelocation": "left",
})

BENCH = ["ghz_star", "chain_trotter", "ladder_trotter", "qaoa_random", "dense_random", "vqe_layers"]
BASE = [14.0, 15.0, 35.5, 39.0, 122.0, 58.0]
V1 = [8.5, 4.5, 6.5, 14.0, 52.5, 3.0]
FINAL = [6.5, 4.5, 6.5, 12.0, 36.0, 3.0]
FLOOR = [6.5, 4.5, 3.0, 4.0, 6.0, 3.0]  # ghz_star: proven by hand; others: 0.5 x logical depth
OPTIMAL = [True, True, False, False, False, True]


def save(fig, name):
    path = os.path.join(FIGS, name)
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ── Fig 1: pipeline ─────────────────────────────────────────────────────────
def fig_pipeline():
    steps = [
        ("1  Anneal", "150 SA runs on\nwire distance"),
        ("2  Round trip", "forward, reverse,\nreuse final layout"),
        ("3  Rank", "1 ms greedy router\nscores candidates"),
        ("4  Tune", "SA on routed score,\nbest of 3 chains"),
        ("5  Beam-route", "256-wide beam on\nSWAPs + 0.5×depth"),
    ]
    fig, ax = plt.subplots(figsize=(7.4, 1.35))
    ax.set_xlim(-0.08, 10.08)
    ax.set_ylim(0, 1.5)
    ax.axis("off")
    w, gap = 1.8, 0.25
    for i, (title, body) in enumerate(steps):
        x = i * (w + gap)
        final = i == len(steps) - 1
        ax.add_patch(FancyBboxPatch((x, 0.05), w, 1.35, boxstyle="round,pad=0.02,rounding_size=0.08",
                                    fc=NAVY if final else "#FBF9F4", ec=NAVY if final else "#D8D2C4", lw=1))
        ax.text(x + 0.1, 1.12, title, fontsize=9, weight="bold", color=AMBER if final else INK, va="center")
        ax.text(x + 0.1, 0.55, body, fontsize=7.2, color="#DCE2EC" if final else MUTED, va="center", linespacing=1.35)
        if not final:
            ax.annotate("", xy=(x + w + gap - 0.02, 0.72), xytext=(x + w + 0.02, 0.72),
                        arrowprops=dict(arrowstyle="-|>", color=GREY, lw=1.2))
    return save(fig, "fig1_pipeline.png")


# ── Fig 2: per-benchmark results ────────────────────────────────────────────
def fig_results():
    fig, ax = plt.subplots(figsize=(7.4, 2.35))
    x = range(len(BENCH))
    bw = 0.26
    ax.bar([i - bw for i in x], BASE, bw, color=GREY, label="Baseline (283.5)")
    ax.bar(list(x), V1, bw, color="#8FA3BF", label="Our v1: SA + greedy (89.0)")
    bars = ax.bar([i + bw for i in x], FINAL, bw, color=AMBER, label="Final (68.5)")
    for i, (f, fl) in enumerate(zip(FINAL, FLOOR)):
        ax.plot([i + bw - 0.17, i + bw + 0.17], [fl, fl], color=INK, lw=1.4, ls=(0, (2, 1.5)))
        ax.text(i + bw, f + 2.5, f"{f:g}", ha="center", fontsize=8, weight="bold", color=INK)
        if OPTIMAL[i]:
            ax.text(i + bw, f + 11, "optimal", ha="center", fontsize=7.5, color=TEAL, weight="bold")
    ax.plot([], [], color=INK, lw=1.4, ls=(0, (2, 1.5)), label="Lower bound")
    ax.set_xticks(list(x), BENCH, fontsize=8.5)
    ax.set_ylabel("score (lower is better)")
    ax.set_ylim(0, 130)
    ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper left", bbox_to_anchor=(0, 1.13))
    ax.grid(axis="y", color="#ECEEF1", lw=0.8)
    ax.set_axisbelow(True)
    return save(fig, "fig2_results.png")


# ── Fig 3: time profile of v1 vs v2 routing on dense_random ─────────────────
def fig_time_profile():
    fig, axes = plt.subplots(2, 1, figsize=(7.4, 2.5), sharex=True)
    for ax, key, name in ((axes[0], "v1", "v1 router (distance only)"), (axes[1], "v2", "Final router (depth-aware beam)")):
        rec = DATA[key]
        swaps = [sum(op[0] == "SWAP" for op in l["ops"]) for l in rec["layers"]]
        gates = [sum(op[0] == "2Q" for op in l["ops"]) for l in rec["layers"]]
        steps = range(1, len(swaps) + 1)
        ax.bar(steps, swaps, color=AMBER, width=0.8, label="SWAPs")
        ax.bar(steps, gates, bottom=swaps, color=TEAL, width=0.8, label="program gates")
        ax.set_ylim(0, 7)
        ax.set_yticks([0, 3, 6])
        ax.text(0.99, 0.92, f"{name}:  {rec['swaps']} SWAPs · depth {rec['depth']} · score {rec['score']:g}",
                transform=ax.transAxes, ha="right", va="top", fontsize=8.5, weight="bold",
                color=RED if key == "v1" else INK)
        ax.set_ylabel("ops / step", fontsize=8)
        ax.grid(axis="y", color="#ECEEF1", lw=0.8)
        ax.set_axisbelow(True)
    axes[0].legend(frameon=False, fontsize=8, loc="upper left", ncol=2)
    axes[1].set_xlabel("time step (layer)")
    axes[1].set_xlim(0.3, 29.7)
    return save(fig, "fig3_time_profile.png")


# ── Fig 4: ablation on dense_random + beam width ────────────────────────────
def fig_ablation_width():
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.4, 2.3), gridspec_kw={"width_ratios": [1.25, 1]})
    labels = ["v1\nSA + greedy", "+ beam router\n+ round trip", "+ tuning on\nrouted score", "+ 3 independent\nchains"]
    vals = [52.5, 47.0, 39.5, 36.0]
    cols = [GREY, "#8FA3BF", "#C7A25E", AMBER]
    a.bar(range(4), vals, color=cols, width=0.62)
    for i, v in enumerate(vals):
        a.text(i, v + 1.2, f"{v:g}", ha="center", fontsize=8.5, weight="bold", color=INK)
        if i:
            a.text(i, v / 2, f"−{vals[i-1]-v:g}", ha="center", fontsize=8, color="white", weight="bold")
    a.set_xticks(range(4), labels, fontsize=7.5)
    a.set_ylim(0, 60)
    a.set_ylabel("dense_random score")
    a.set_title("(a) What each idea bought on dense_random")

    widths = [1, 8, 64, 512]
    runs = [[97, 74, 71.5, 68.5], [91.5, 82.5, 72.5, 72], [91.5, 92.5, 82.5, 75.5], [82, 74.5, 70.5, 65.5], [78.5, 77, 70.5, 66]]
    greedy = [85, 103, 109, 80, 97.5]
    for r in runs:
        b.plot(widths, r, color=GREY, lw=0.8, alpha=0.7)
    avg = [sum(r[i] for r in runs) / len(runs) for i in range(4)]
    b.plot(widths, avg, color=AMBER, lw=2.2, marker="o", ms=4, label="beam router (mean of 5)")
    b.axhline(sum(greedy) / len(greedy), color=RED, ls="--", lw=1.2, label="greedy router (mean)")
    b.axvline(256, color=TEAL, lw=1, ls=":")
    b.text(256, 108, " we use 256", color=TEAL, fontsize=7.5, va="top")
    b.set_xscale("log", base=2)
    b.set_xticks(widths, [str(w) for w in widths])
    b.set_xlabel("beam width")
    b.set_ylabel("score")
    b.set_ylim(60, 110)
    b.legend(frameon=False, fontsize=7.5, loc="lower left")
    b.set_title("(b) Wider beam, better routes (random layouts)")
    fig.tight_layout(w_pad=2.0)
    return save(fig, "fig4_ablation_width.png")


# ── PDF ─────────────────────────────────────────────────────────────────────
def build_pdf(figs):
    for name, file in (("Segoe", "segoeui.ttf"), ("Segoe-Bold", "segoeuib.ttf"), ("Segoe-Italic", "segoeuii.ttf")):
        pdfmetrics.registerFont(TTFont(name, os.path.join(r"C:\Windows\Fonts", file)))
    pdfmetrics.registerFontFamily("Segoe", normal="Segoe", bold="Segoe-Bold", italic="Segoe-Italic")

    body = ParagraphStyle("body", fontName="Segoe", fontSize=9.2, leading=12.4, textColor=colors.HexColor(INK))
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10.4, textColor=colors.HexColor(MUTED))
    h1 = ParagraphStyle("h1", parent=body, fontName="Segoe-Bold", fontSize=17, leading=21, textColor=colors.HexColor(NAVY))
    sub = ParagraphStyle("sub", parent=body, fontSize=9.5, textColor=colors.HexColor(MUTED))
    h2 = ParagraphStyle("h2", parent=body, fontName="Segoe-Bold", fontSize=11, leading=14, spaceBefore=6, spaceAfter=3, textColor=colors.HexColor(NAVY))
    cap = ParagraphStyle("cap", parent=small, fontName="Segoe-Italic")
    kpi_n = ParagraphStyle("kpin", parent=body, fontName="Segoe-Bold", fontSize=18, leading=21, alignment=TA_CENTER, textColor=colors.HexColor(NAVY))
    kpi_l = ParagraphStyle("kpil", parent=small, alignment=TA_CENTER)
    cell = ParagraphStyle("cell", parent=body, fontSize=8.4, leading=10.8)
    cellb = ParagraphStyle("cellb", parent=cell, fontName="Segoe-Bold")

    W = A4[0] - 3.2 * cm

    def img(path, width=W):
        from PIL import Image as PImage
        w, h = PImage.open(path).size
        return Image(path, width=width, height=width * h / w)

    def kpi(n, l, color=NAVY):
        return [Paragraph(f'<font color="{color}">{n}</font>', kpi_n), Paragraph(l, kpi_l)]

    kpis = Table([[kpi("283.5", "baseline score"), kpi("68.5", "our score (−76%)", AMBER),
                   kpi("3 / 6", "benchmarks provably optimal", TEAL), kpi("6 / 6", "valid under the official scorer")]],
                 colWidths=[W / 4] * 4)
    kpis.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(PAPER)),
                              ("LINEAFTER", (0, 0), (-2, -1), 0.6, colors.HexColor("#DDD6C8")),
                              ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))

    method_rows = [
        ["Step", "What it does", "Why"],
        ["1. SA placement", "150 annealing runs minimise Σ hardware distance over all 2Q pairs; moves swap two qubits or jump to a free physical qubit", "puts partners close; free-qubit moves explore the whole chip"],
        ["2. Round trip", "route forward, route the reversed program from the final layout, restart from where qubits ended (SABRE-style, 4 rounds)", "layouts adapt to where the program actually needs qubits"],
        ["3. Greedy rank", "look-ahead router: SWAP minimising current + decayed distance of the next 20 gates", "~1 ms per route, scores every candidate cheaply"],
        ["4. Tune on real score", "SA whose cost is the routed score (width-8 beam, cached); 3 independent chains, best kept", "distance is only a proxy; one chain often stalls"],
        ["5. Beam routing", "keeps up to 256 partial routings, tracks each qubit's last layer (exactly as the scorer schedules), ranks by swaps + 0.5·depth + look-ahead", "chooses which qubit moves and along which path, so SWAPs run in parallel"],
    ]
    method = Table([[Paragraph(c, cellb if r == 0 or j == 0 else cell) for j, c in enumerate(row)] for r, row in enumerate(method_rows)],
                   colWidths=[W * 0.17, W * 0.53, W * 0.30])
    method.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PAPER)),
                                ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#E3E0D8")),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

    story = [
        Paragraph("Placing and Routing Qubits on a 20-Qubit Heavy-Hex Chip", h1),
        Paragraph("QSITE 2026 · Computational Track · Team telequantum · Authored by Aziz Chebil", sub),
        Spacer(1, 8), kpis, Spacer(1, 6),
        Paragraph("Problem", h2),
        Paragraph("Map each program's logical qubits onto a 20-qubit heavy-hex graph (1–3 neighbours per qubit) and insert SWAPs so every "
                  "two-qubit gate acts on an edge. Program order is fixed (stripping SWAPs must recover the exact program). "
                  "<b>Score = SWAPs + 0.5 × depth</b>, where depth comes from ASAP layer packing; lower is better.", body),
        Paragraph("Approach", h2),
        img(figs[0]),
        Paragraph("<b>Figure 1.</b> Pipeline. Steps 1–3 search placements broadly and cheaply; steps 4–5 spend compute on the true objective.", cap),
        Spacer(1, 5), method,
        Paragraph("Results", h2),
        img(figs[1]),
        Paragraph("<b>Figure 2.</b> Score per benchmark. Dashed ticks are lower bounds: 0.5 × the program's own dependency depth "
                  "(zero SWAPs), and for ghz_star a hand proof (below). Deterministic (fixed seed); reproduce with <b>python evaluate.py</b>.", cap),
        PageBreak(),
        Paragraph("Why a depth-aware router matters", h2),
        img(figs[2]),
        Paragraph("<b>Figure 3.</b> Operations per time step on dense_random (14 qubits, 40 gates), real routings. The v1 router picked "
                  "the SWAP that most reduced distance and ignored <i>when</i> it could run, so SWAPs queued on busy qubits. The beam "
                  "router scores depth exactly and packs more work into each step: 14 fewer SWAPs and 5 fewer steps.", cap),
        Paragraph("What each idea bought", h2),
        img(figs[3]),
        Paragraph("<b>Figure 4.</b> (a) Cumulative gains on dense_random, measured as each component was added. The largest single gain "
                  "came from tuning placement on the routed score rather than on the distance proxy. (b) Beam width vs score on 5 random "
                  "layouts of dense_random (grey: each layout; amber: mean). Returns diminish past a few hundred; 256 costs ~150 ms per "
                  "route, so we use it only for the final pass and width 8 inside the tuning loop.", cap),
        Paragraph("How close to optimal?", h2),
        Paragraph("• <b>chain_trotter, vqe_layers</b>: zero SWAPs at the program's own depth, so no solution can score lower.<br/>"
                  "• <b>ghz_star</b>: the hub must interact with 7 qubits but has at most 3 neighbours, so it must move at least twice; its gates and "
                  "moves are serial, so depth ≥ 7 + 2 = 9 and score ≥ 2 + 4.5 = <b>6.5</b>, which we achieve.<br/>"
                  "• <b>ladder, qaoa, dense</b>: the gap to the bound is structural (the chip has no 4-cycles; random circuits touch every qubit), "
                  "but the bound is loose, so some headroom likely remains.", body),
        Paragraph("What didn't work, and robustness", h2),
        Paragraph("• <b>Sideways SWAPs</b> (moves that don't shorten the current gate but help the next 3) won 10 / lost 9 on random layouts; "
                  "inside the tuning loop they made results worse and ~2.5× slower. Kept only as an extra final-pass option.<br/>"
                  "• <b>Seed choice</b>: another seed scores 68.0; we kept a fixed seed rather than tune to the test set.<br/>"
                  "• <b>Unseen programs</b>: 1-qubit, single-gate, mixed 1Q/2Q and random 16–20-qubit programs all validate; "
                  "runtime 1–23 s per benchmark with a 60 s safety cap. Stretch goals were not attempted (no scored baseline was provided).", body),
    ]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Segoe", 7.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawRightString(A4[0] - 1.6 * cm, 0.9 * cm, f"{doc.page} / 2")
        canvas.drawString(1.6 * cm, 0.9 * cm, "Code: Computational Track/solver.py · evaluate.py")
        canvas.restoreState()

    doc = SimpleDocTemplate(os.path.join(HERE, "writeup.pdf"), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                            topMargin=1.3 * cm, bottomMargin=1.4 * cm, title="Placing and Routing Qubits — Technical Write-up")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    figs = [fig_pipeline(), fig_results(), fig_time_profile(), fig_ablation_width()]
    build_pdf(figs)
    print("wrote", os.path.join(HERE, "writeup.pdf"))
