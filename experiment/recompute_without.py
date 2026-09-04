"""저장된 조건별 점수에서 특정 조건군을 빼고 다시 집계한다.

`clean` 조건은 오류를 주입하지 않으므로 지목이 전부 오탐이고, 상위 10%
정밀도가 **구조적으로 항상 0%**다. 자의 품질을 재는 값이 아니라 상수인데,
평균에 섞이면 절대값을 끌어내린다. 두 자에 똑같이 적용되므로 비교 자체는
성립하지만, "이 자의 상위 10%는 63.6%"라고 말할 때 그 63.6%가 자의 실력이
아니라는 게 문제다.

compare_rulers_seeded.py --out 이 남긴 JSON만 있으면 GPU 없이 다시 잰다.

사용법:
  python recompute_without.py seeded_ruler_7seeds.json clean
  python recompute_without.py seeded_ruler_7seeds.json clean class_swap
"""
import itertools
import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def aggregate(data: dict, drop: list[str]) -> dict[str, tuple[float, float, list[float]]]:
    """자별 (평균, 표준편차, 시드별 값). drop에 있는 접두사의 조건은 뺀다."""
    out = {}
    for label, rows in data["rulers"].items():
        if not rows:
            continue
        per_seed = []
        for row in rows:
            kept = [v * 100 for cond, v in row["per_condition"].items()
                    if not any(cond.startswith(d) for d in drop)]
            if kept:
                per_seed.append(statistics.mean(kept))
        if per_seed:
            sd = statistics.stdev(per_seed) if len(per_seed) > 1 else float("nan")
            out[label] = (statistics.mean(per_seed), sd, per_seed)
    return out


def report(data: dict, drop: list[str]) -> None:
    n_all = len(data["conditions"])
    kept = [c for c in data["conditions"] if not any(c.startswith(d) for d in drop)]
    title = f"뺀 조건: {', '.join(drop)}" if drop else "전체 조건"
    print(f"[{title}]  {len(kept)}/{n_all}개 사용")

    stats = aggregate(data, drop)
    for label, (m, sd, vals) in stats.items():
        print(f"  {label:<14}{m:5.1f}% ± {sd:.2f}   "
              + " / ".join(f"{v:.1f}" for v in vals))

    for a, b in itertools.combinations(stats, 2):
        ma, sa, _ = stats[a]
        mb, sb, _ = stats[b]
        gap = ma - mb
        pooled = ((sa ** 2 + sb ** 2) / 2) ** 0.5
        n = abs(gap) / pooled if pooled > 0 else float("inf")
        # 2σ 기준은 AB부터 계속 쓰던 것과 같다
        print(f"    {a} vs {b}: {gap:+.1f}%p  ±{pooled:.2f}  = {n:.1f}σ  "
              f"{'넘는다' if n >= 2 else '묻힌다'}")
    print()


def main() -> None:
    path = Path(sys.argv[1])
    drops = sys.argv[2:]
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"{path.name} — 시드 {len(data['seeds'])}개, 조건 {len(data['conditions'])}개\n")
    report(data, [])
    for i in range(1, len(drops) + 1):
        report(data, drops[:i])


if __name__ == "__main__":
    main()
