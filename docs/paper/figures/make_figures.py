"""논문 초안 그림 (2026-10-06) — 결과 파일·초안 표에서만 그린다. 결과 파일은 읽기만 한다.

    pip install matplotlib   # 실험 환경 의존성이 아니다(그림 전용)
    python docs/paper/figures/make_figures.py

그림
- fig_baselines.png   : 표 6 — 자 8개에서 AIDA 두 순서와 전체 라벨 기준선 세 가지의 상위 k 정밀도 (초안 6.5절)
- fig_k_sensitivity.png: 표 8 — k에 따른 current - ObjectLab 짝지은 차이, KITTI→COCO 강조 (부록 C)
- fig_prelim1_depth.png: prelim1 — 검수량별 고유 오류 수, v1 대 1-IoU (초안 7절, 사후 깊이 진단)

색: dataviz 기본 범주 팔레트 앞 5칸(validate_palette.js light 통과, 대비 WARN → 범례·표로 보완).
"""
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVID = ROOT / "experiment" / "planning_evidence"
DRAFT = HERE.parent / "draft_ko.md"

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"

plt.rcParams.update({
    "font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 10,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.axisbelow": True, "axes.titlecolor": INK, "axes.titleweight": "bold",
    "legend.frameon": False,
})


def num(cell: str) -> tuple[float, float]:
    """'0.933 ± 0.025 (0.1~0.2)' → (0.933, 0.025); '0.291' → (0.291, 0)."""
    cell = re.sub(r"\(.*?\)", "", cell).replace("**", "").strip()
    m = re.match(r"([0-9.]+)(?:\s*±\s*([0-9.]+))?", cell)
    return float(m.group(1)), float(m.group(2) or 0)


def half_up(v: float) -> str:
    """표와 같은 사사오입(소수 3자리), 부호 포함."""
    from decimal import Decimal, ROUND_HALF_UP
    d = Decimal(str(v)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return f"{d:+}"


def table6():
    text = DRAFT.read_text(encoding="utf-8")
    start = text.index("| 자 | 시드 | legacy | current | AIDA 안 무작위")
    rows = []
    for line in text[start:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        c = [x.strip() for x in line.strip("|").split("|")]
        rows.append({"name": c[0], "legacy": num(c[2]), "current": num(c[3]),
                     "random": num(c[6]), "iou": num(c[7]), "objectlab": num(c[8])})
    return rows


def fig_baselines():
    rows = table6()
    series = [("current", "AIDA 현재 순서", BLUE), ("legacy", "AIDA 과거 순서", ORANGE),
              ("objectlab", "전체 라벨 ObjectLab", AQUA), ("iou", "전체 라벨 1-IoU", YELLOW),
              ("random", "전체 라벨 무작위", MAGENTA)]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    w, gap = 0.15, 0.012
    for i, (key, label, color) in enumerate(series):
        xs = [j + (i - 2) * (w + gap) for j in range(len(rows))]
        ys = [r[key][0] for r in rows]
        es = [r[key][1] for r in rows]
        ax.bar(xs, ys, width=w, color=color, label=label, yerr=es, error_kw={"elinewidth": 1, "ecolor": INK2,
               "capsize": 0}, zorder=2)
    ax.set_xticks(range(len(rows)), [r["name"] for r in rows], rotation=0, fontsize=8.5)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("상위 k 정밀도 (주입 오류 정답)")
    ax.set_title("같은 검수량 k에서 AIDA 순서와 전체 라벨 기준선 (표 6)", loc="left", pad=30)
    ax.legend(ncol=5, loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=8.5)
    ax.text(0, -0.2, "k = 조건마다 AIDA 지목 수 × 10%. 막대 위 선은 학습 시드 간 표준편차. 합성 주입 오류만 정답이다.",
            transform=ax.transAxes, fontsize=8, color=INK2)
    fig.tight_layout()
    fig.savefig(HERE / "fig_baselines.png", dpi=200)
    plt.close(fig)


def fig_k_sensitivity():
    d = json.loads((EVID / "controlled_baseline_followup_2026-10-06.json").read_text(encoding="utf-8"))
    B = d["B_k_sensitivity"]
    ks = ["f5", "f10", "f20", "f50", "l1", "l2", "l5"]
    labels = ["지목\n5%", "지목\n10%", "지목\n20%", "지목\n50%", "전체\n1%", "전체\n2%", "전체\n5%"]
    others = [r for r in B if r != "B/kitti_on_coco"]
    vals = {r: [B[r]["paired_unique_current_minus_baseline"][k]["all_label_objectlab"]["mean"] for k in ks] for r in B}
    lo = [min(vals[r][i] for r in others) for i in range(len(ks))]
    hi = [max(vals[r][i] for r in others) for i in range(len(ks))]
    x = list(range(len(ks)))
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.fill_between(x, lo, hi, color=BLUE, alpha=0.18, linewidth=0, label="다른 7개 자 (최소~최대)")
    kc = vals["B/kitti_on_coco"]
    ax.plot(x, kc, color=ORANGE, linewidth=2, marker="o", markersize=7, label="KITTI→COCO", zorder=3)
    for xi, yi in zip(x, kc):
        ax.annotate(half_up(yi), (xi, yi), textcoords="offset points", xytext=(0, 9), ha="center",
                    fontsize=8, color=INK)
    ax.axhline(0, color=INK2, linewidth=1)
    ax.set_xticks(x, labels, fontsize=8.5)
    ax.set_ylabel("current - ObjectLab (짝지은 차이)")
    ax.set_title("검수 예산 k를 바꿔도: KITTI→COCO만 ObjectLab과 구별되지 않는다 (표 8)", loc="left")
    ax.legend(loc="center left", bbox_to_anchor=(0.01, 0.3), fontsize=8.5)
    fig.tight_layout()
    fig.savefig(HERE / "fig_k_sensitivity.png", dpi=200)
    plt.close(fig)


def fig_prelim1_depth():
    d = json.loads((EVID / "prelim1_results.json").read_text(encoding="utf-8"))
    bb = d["labelled_layer"]["by_budget"]
    n = [b["budget"] for b in bb]
    a = [b["aida"]["unique_errors"] for b in bb]
    i = [b["iou_baseline"]["unique_errors"] for b in bb]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.plot(n, i, color=BLUE, linewidth=2, marker="o", markersize=7, label="1 - label_iou 순서")
    ax.plot(n, a, color=ORANGE, linewidth=2, marker="o", markersize=7, label="AIDA v1 순서")
    ax.annotate(f"{i[-1]}", (n[-1], i[-1]), textcoords="offset points", xytext=(8, -3), fontsize=9, color=INK)
    ax.annotate(f"{a[-1]}", (n[-1], a[-1]), textcoords="offset points", xytext=(8, -3), fontsize=9, color=INK)
    ax.axvline(90, color=INK2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(88.5, 7.5, "사전 등록한\n1차 검수량 N=90", ha="right", va="center", fontsize=8, color=INK2)
    ax.set_xlabel("검수량 N (AIDA 후보 안의 재정렬)")
    ax.set_ylabel("판정자가 오류로 본 고유 라벨 수")
    ax.set_xticks(n)
    ax.set_title("prelim1 (KITTI Car 300장, 판정자 1인): 같은 검수량에서 찾은 오류", loc="left")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.text(0, -0.2, "N=90 외의 깊이는 사후 진단이다. N=90에서 차이 -10, 95% 구간 [-18, -2].",
            transform=ax.transAxes, fontsize=8, color=INK2)
    fig.tight_layout()
    fig.savefig(HERE / "fig_prelim1_depth.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    fig_baselines()
    fig_k_sensitivity()
    fig_prelim1_depth()
    print("written:", sorted(p.name for p in HERE.glob("fig_*.png")))
