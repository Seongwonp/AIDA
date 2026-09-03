"""자를 시드별로 바꿔가며 진단해 Y의 비교에 오차막대를 붙인다.

Y는 "자기 도메인 자 92.4% vs 약한 이동 자 65.5%"라고 했는데 둘 다 단일
관측이었다. AB에서 조건별 저하의 시드 산포가 ±6~10%p로 크다는 걸 봤으니,
자 쪽도 흔들릴 수 있다.

같은 데이터를 자만 바꿔 진단한다. 학습은 하지 않는다(자는 이미 있다).

조건은 유형별 대표 9개로 줄인다 — 29개를 6번 돌리면 두 시간이 넘고, 유형별
대표만으로도 상위권 정밀도의 비교는 성립한다. **기존 값(29개 조건)과 직접
비교하지 않도록**, 두 자 모두 같은 9개로 다시 잰다.

사용법:
  AIDA_CLASSES=... AIDA_FRAME_SELECT=cyclist_rich python compare_rulers_seeded.py
"""
import statistics
import sys
from pathlib import Path

import config
import evaluate_box_accuracy as E

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CONDITIONS = ["width_m30", "height_m30", "rot_m15", "trans_x_m15", "trans_y_m15",
              "scale_m30", "missing_30", "duplicate_30", "class_swap_30"]
SEEDS = [42, 123, 2024]


def ruler_path(kind: str, seed: int) -> Path:
    """kind: matched(자기 도메인) | shifted(약한 이동). seed 42는 접미사 없음."""
    suffix = "" if seed == 42 else f"_e{seed}"
    base = "runs_mc_cyclist_rich" if kind == "matched" else "runs_mc"
    return config.EXPERIMENT_ROOT / f"{base}{suffix}" / "clean" / "weights" / "best.pt"


def measure(kind: str, seed: int, limit: int) -> dict | None:
    w = ruler_path(kind, seed)
    if not w.exists():
        print(f"  [{kind} seed={seed}] {w} 없음 — 건너뜀")
        return None
    E.RULER_PATH = w
    tp = fp = 0
    p10 = []
    for name in CONDITIONS:
        r = E.score_condition(config._BY_NAME[name], limit)
        tp += r["tp"]; fp += r["fp"]
        v = r["verdicts_by_rank"]
        p10.append(E.precision_at_k(v, max(1, int(len(v) * 0.1))))
    return {"precision": tp / (tp + fp) if tp + fp else 0.0,
            "top10": sum(p10) / len(p10)}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="시드별 자 비교")
    ap.add_argument("--limit", type=int, default=80)
    args = ap.parse_args()

    print(f"조건 {len(CONDITIONS)}개 × 자 2종 × 시드 {SEEDS}\n")
    out: dict[str, list[dict]] = {}
    for kind, label in (("matched", "자기 도메인"), ("shifted", "약한 이동")):
        rows = []
        for seed in SEEDS:
            print(f"[{label} seed={seed}] 진단 중...", flush=True)
            m = measure(kind, seed, args.limit)
            if m:
                rows.append(m)
                print(f"    정밀도 {m['precision']*100:.1f}%  상위10% {m['top10']*100:.1f}%")
        out[label] = rows

    print(f"\n{'자':<14}{'n':>3}{'상위10% 평균':>14}{'±':>8}{'전체 정밀도':>14}")
    print("-" * 55)
    stats = {}
    for label, rows in out.items():
        if not rows:
            continue
        t = [r["top10"] * 100 for r in rows]
        p = [r["precision"] * 100 for r in rows]
        sd = statistics.stdev(t) if len(t) > 1 else float("nan")
        stats[label] = (statistics.mean(t), sd)
        print(f"{label:<14}{len(t):>3}{statistics.mean(t):>13.1f}%{sd:>8.2f}"
              f"{statistics.mean(p):>13.1f}%")

    if len(stats) == 2:
        (ma, sa), (mb, sb) = stats.values()
        gap = ma - mb
        pooled = ((sa ** 2 + sb ** 2) / 2) ** 0.5 if sa == sa and sb == sb else float("nan")
        print(f"\n두 자의 차이 {gap:+.1f}%p, 합동 표준편차 ±{pooled:.2f}")
        if pooled == pooled and pooled > 0:
            print(f"  = {abs(gap)/pooled:.1f}σ → "
                  f"{'시드 산포를 넘는다' if abs(gap)/pooled >= 2 else '시드 산포에 묻힌다'}")


if __name__ == "__main__":
    main()
