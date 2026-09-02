"""자를 바꿔가며 한 조건을 진단해 비교한다 — 자기 정제가 얼마나 회복하는가.

V에서 확인: clean 자가 없으면 재현율이 82% → 50%로 반토막 난다. W는 그
휘어진 자로 깨끗한 부분집합을 골라 재학습한 자("정제된 자")가 얼마나
회복하는지 본다.

조건 하나에 대해 자만 갈아끼우고 같은 채점을 돌린다. 학습은 하지 않는다.

사용법:
  python compare_rulers.py --condition scale_m30 --rulers clean self refined30 refined50 refined70
"""
import argparse
import sys

import config
import evaluate_box_accuracy as E

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description="자별 진단 성능 비교")
    parser.add_argument("--condition", required=True)
    parser.add_argument("--rulers", nargs="+", required=True)
    parser.add_argument("--limit", type=int, default=None,
                        help="이미지 수 제한 (기본: 전체)")
    args = parser.parse_args()

    cond = config._BY_NAME[args.condition]
    rows = []
    for ruler in args.rulers:
        E.RULER = ruler
        w = E.ruler_for(cond)
        if w is not None and not w.exists():
            print(f"[{ruler}] {w} 없음 — 건너뜀")
            continue
        print(f"[{ruler}] 진단 중...", flush=True)
        r = E.score_condition(cond, args.limit)
        v = r["verdicts_by_rank"]
        rows.append((ruler, r, [E.precision_at_k(v, max(1, int(len(v) * f)))
                                for f in (0.1, 0.25, 0.5)]))

    print(f"\n{args.condition} — 자를 바꿔가며 같은 데이터를 진단\n")
    print(f"{'자':<12}{'지목':>6}{'TP':>6}{'정밀도':>8}{'재현율':>8}"
          f"{'상위10%':>9}{'상위25%':>9}{'상위50%':>9}")
    print("-" * 68)
    for ruler, r, pk in rows:
        print(f"{ruler:<12}{r['flagged']:>6}{r['tp']:>6}{r['precision']*100:>7.1f}%"
              f"{r['recall']*100:>7.1f}%{pk[0]*100:>8.1f}%{pk[1]*100:>8.1f}%{pk[2]*100:>8.1f}%")


if __name__ == "__main__":
    main()
