"""자별·유형별 시드 산포를 낸다 (docs/21 AD·AE의 남은 한계).

AD는 자 단위 표준편차만 냈다. 그런데 제품 화면이 보여주는 건 **유형별**
신뢰도라, "이 유형 수치가 얼마나 흔들리는가"를 답하려면 유형별 산포가
있어야 한다. compare_rulers_seeded.py --out 이 남긴 조건별 점수에서 뽑는다.

조건 이름에서 유형을 얻는다 — width_m30 → width. 유형마다 강도가 여러 개
있으므로(m30/m15/p15 등), 유형별 값은 그 강도들의 평균이다.

사용법:
  python analyze_ruler_spread.py seeded_ruler_7seeds.json
"""
import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 조건 이름 → 유형. 접미사(_m30, _p15 …)를 떼면 유형이 남는데, 이름에
# 밑줄이 들어간 유형이 있어서(trans_x, class_swap) 단순 split이 안 된다.
TYPE_PREFIXES = ["trans_x", "trans_y", "class_swap", "width", "height",
                 "rot", "scale", "missing", "duplicate"]


def type_of(condition: str) -> str:
    for prefix in TYPE_PREFIXES:
        if condition.startswith(prefix):
            return prefix
    return condition


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "seeded_ruler_7seeds.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    seeds = data["seeds"]
    print(f"{path.name} — 시드 {len(seeds)}개 {seeds}, 조건 {len(data['conditions'])}개\n")

    for label, rows in data["rulers"].items():
        if not rows:
            continue
        overall = [r["top10"] * 100 for r in rows]
        sd = statistics.stdev(overall) if len(overall) > 1 else float("nan")
        print(f"■ {label}  전체 {statistics.mean(overall):.1f}% ± {sd:.2f}  "
              f"(n={len(overall)})")
        print(f"    {' / '.join(f'{v:.1f}' for v in overall)}")

        # 유형별: 시드마다 그 유형 조건들의 평균을 내고, 그 값들의 산포를 본다
        by_type: dict[str, list[float]] = {}
        for row in rows:
            per_seed: dict[str, list[float]] = {}
            for cond, score in row["per_condition"].items():
                per_seed.setdefault(type_of(cond), []).append(score * 100)
            for t, vals in per_seed.items():
                by_type.setdefault(t, []).append(statistics.mean(vals))

        print(f"    {'유형':<12}{'평균':>8}{'표준편차':>10}   시드별 값")
        for t, vals in sorted(by_type.items(), key=lambda kv: -statistics.mean(kv[1])):
            tsd = statistics.stdev(vals) if len(vals) > 1 else float("nan")
            print(f"    {t:<12}{statistics.mean(vals):>7.1f}%{tsd:>10.2f}   "
                  + " / ".join(f"{v:.0f}" for v in vals))
        print()

    # 자끼리의 산포 비교 — AD의 "좁은 자가 덜 흔들린다"가 시드를 늘려도 남는가
    sds = {}
    for label, rows in data["rulers"].items():
        vals = [r["top10"] * 100 for r in rows]
        if len(vals) > 1:
            sds[label] = statistics.stdev(vals)
    if len(sds) > 1:
        print("자별 표준편차 비교 (작을수록 시드에 덜 흔들린다)")
        for label, sd in sorted(sds.items(), key=lambda kv: kv[1]):
            print(f"  {label:<14} ±{sd:.2f}")
        lo, hi = min(sds.values()), max(sds.values())
        if lo > 0:
            print(f"  → 가장 안정적인 자가 가장 불안정한 자보다 {hi / lo:.1f}배 안정적")


if __name__ == "__main__":
    main()
