"""재검수 시뮬레이션 결과 집계 — 정렬 방식이 실제로 mAP를 더 회복시키는가.

R에서 클래스 가중 정렬이 recovered@k를 17.3% → 43.1%로 올렸다. 그런데 그 지표의
가중치가 곧 클래스 취약도라, 취약도로 만든 순서를 취약도로 만든 지표로 평가한
셈이었다. mAP는 그 순환 밖에 있는 잣대다.

**실행 간 산포가 크다는 걸 먼저 확인했다.** 같은 데이터셋(clean)을 워커 수만
바꿔 학습했더니 mAP50이 0.599 vs 0.554로 7.5% 벌어졌다. 그래서 조건마다 학습
시드를 바꿔 3회씩 돌리고, 정렬 간 차이가 그 산포보다 큰지를 본다. 크지 않으면
"모른다"가 정답이다.

사용법:
  python analyze_review_sim.py
"""
import sys

import pandas as pd

import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ORDERS = ("severity", "class_weighted", "random")
FRACTIONS = (25, 50)
BASE, TOP = "scale_m30_asis", "clean_asis"


def runs_of(df: pd.DataFrame, name: str) -> list[float]:
    """같은 조건의 반복 실행들. 꼬리표(_s43 등)가 붙은 행을 함께 모은다."""
    hit = df[(df.condition == name) | df.condition.str.startswith(name + "_s")]
    return sorted(hit["map50"].tolist())


def line(label: str, vals: list[float], base_mean: float | None = None) -> str:
    if not vals:
        return f"{label:<18}(없음)"
    mean = sum(vals) / len(vals)
    std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5 if len(vals) > 1 else 0.0
    out = f"{label:<18}{mean:.4f} ± {std:.4f}  (n={len(vals)}) "
    out += " ".join(f"{v:.3f}" for v in vals)
    if base_mean is not None:
        out += f"   기준선 대비 {mean - base_mean:+.4f}"
    return out


def main() -> None:
    df = pd.read_csv(config.METRICS_CSV)
    base = runs_of(df, BASE)
    top = runs_of(df, TOP)
    if not base:
        raise SystemExit(f"{BASE} 결과가 없습니다")
    bm = sum(base) / len(base)
    tm = sum(top) / len(top) if top else float("nan")

    print("같은 데이터셋을 학습 시드만 바꿔 반복한 결과\n")
    print(line("상한(clean)", top))
    print(line("기준선(미수정)", base))
    print()

    # 잡음 바닥은 **모든 조건의 반복 산포를 합쳐** 추정한다(합동 표준편차).
    # 기준선 하나로만 재면 안 된다 — 실제로 기준선은 ±0.002로 조용한데
    # class_weighted는 같은 데이터셋에서 ±0.027로 흔들렸다. 조건 하나의 산포를
    # 잡음으로 삼으면 그 조건이 조용했다는 이유만으로 "읽을 만하다"가 나온다.
    groups = [base, top] + [runs_of(df, f"scale_m30_fix_{o}_{f}")
                            for f in FRACTIONS for o in ORDERS]
    ss = n_free = 0
    for vals in groups:
        if len(vals) > 1:
            m = sum(vals) / len(vals)
            ss += sum((v - m) ** 2 for v in vals)
            n_free += len(vals) - 1
    noise = (ss / n_free) ** 0.5 if n_free else 0.0
    print(f"잡음 바닥(전 조건 합동 표준편차, 자유도 {n_free}): ±{noise:.4f}")
    print(f"회복 여지(상한 - 기준선): {tm - bm:+.4f}\n")

    for frac in FRACTIONS:
        print(f"--- 큐 상위 {frac}% 수정 ---")
        means = {}
        for order in ORDERS:
            vals = runs_of(df, f"scale_m30_fix_{order}_{frac}")
            print("  " + line(order, vals, bm))
            if vals:
                means[order] = sum(vals) / len(vals)
        if len(means) > 1:
            spread = max(means.values()) - min(means.values())
            verdict = "잡음보다 큼 — 읽을 만함" if spread > 2 * noise else "잡음에 묻힘 — 판단 불가"
            print(f"  정렬 간 최대 차이 {spread:.4f}  (잡음 ±{noise:.4f}의 "
                  f"{spread / noise:.1f}배) → {verdict}")
        print()


if __name__ == "__main__":
    main()
