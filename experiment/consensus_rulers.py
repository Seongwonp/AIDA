"""어긋난 자 여러 대가 둘 다 의심한 박스만 올리면 정밀도가 오르나 (docs/22 계획 1번).

AM이 **후보가 전부 어긋난 자면 고르는 것으로는 답이 안 난다**를 쟀다. 남은 길은
고르는 게 아니라 고치는 것이고, 그중 제일 싼 것이 합의다 — 학습이 없고 추론만
여러 번 하면 된다.

기대와 반론이 둘 다 있다. 자마다 틀리는 방식이 다르면 오탐은 안 겹치고 진짜
오류는 겹친다. 반대로 자들이 **같은 이유로** 틀리면 오탐도 그대로 겹친다.

성공 기준은 PREDICTION_consensus.md에 먼저 적어뒀다.

## 어떻게 재나

**자기 도메인 자는 일부러 뺀다.** 맞는 자가 있으면 그걸 쓰면 되지 합의가 필요
없다. 여기서 보는 것은 "맞는 자가 하나도 없을 때"다.

**목록 길이를 맞춘다.** 합의는 지목을 줄이므로, 줄어든 목록의 "상위 10%"를
원래의 "상위 10%"와 견주면 공정하지 않다. 검수자에게 맞는 질문은 "박스 k개를
본다면 그중 몇 개가 진짜인가"라 **k 고정**으로 잰다.

**조합을 전부 낸다.** 정밀도가 높은 둘을 골라 합의시키면 그건 이미 정답을 본
것이다. 2대·3대 조합을 모두 내고 분포를 본다.

사용법:

  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" AIDA_FRAME_SELECT=cyclist_rich \\
    ./venv/Scripts/python.exe consensus_rulers.py --seed 42 --limit 80 \\
      --out consensus_seed42.json
"""
import argparse
import itertools
import json
import statistics
import sys
from pathlib import Path

import config
import evaluate_box_accuracy as E
from compare_rulers_seeded import RULERS, ruler_path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 전부 어긋난 4클래스 자들 (AM). 자기 도메인 자는 없다.
KINDS = ["bpoor", "bmid", "brich", "shifted", "broad"]
KS = [5, 10, 20]          # 검수 예산. 결론은 k=10으로 미리 정했다.
DECIDE_K = 10


def finding_key(f) -> tuple:
    """자가 달라도 같은 지목이면 같은 키.

    좌표가 아니라 (이미지, 라벨 번호, 의심 유형)으로 묶는다. 자마다 예측 박스는
    다르지만 **가리키는 라벨은 같아야** 합의라고 부를 수 있다. 누락 의심은
    가리킬 라벨이 없어 이미지 단위로만 겹친다 — 그건 아래에서 따로 센다.
    """
    return (Path(f.image).stem, f.label_index, f.suspicion)


def collect(kind: str, seed: int, condition, limit: int):
    """자 한 대의 지목을 그대로 받아온다. 채점은 아직 안 한다."""
    from diagnose_labels import run

    w = ruler_path(kind, seed)
    if not w.exists():
        return None
    root = config.CONDITIONS_DIR / condition.name
    findings, total_labels, _fit = run(root / "images" / "train",
                                       root / "labels" / "train", limit, weights=w)
    return findings, total_labels


def consensus(per_ruler: dict, need: int) -> list:
    """`need`대 이상이 지목한 것만 남긴다. 심각도는 그 자들의 평균으로 다시 매긴다.

    한 자의 심각도를 그대로 쓰면 그 자의 눈금에 끌려간다. 평균을 쓰면 여러
    자가 세게 의심한 것이 위로 온다.
    """
    seen: dict[tuple, list] = {}
    for findings in per_ruler.values():
        for f in findings:
            seen.setdefault(finding_key(f), []).append(f)
    out = []
    for group in seen.values():
        if len(group) < need:
            continue
        best = max(group, key=lambda f: f.severity)
        # 원본을 건드리지 않고 심각도만 바꾼 사본을 만든다
        merged = best.__class__(**{**vars(best),
                                   "severity": statistics.mean(f.severity for f in group)})
        out.append(merged)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    conditions = [c.name for c in config.conditions_in_run_order() if c.name != "clean"]
    print(f"조건 {len(conditions)}개 · 자 {len(KINDS)}종 · 학습 시드 {args.seed}")
    print("자기 도메인 자는 없다 — '맞는 자가 하나도 없을 때'를 보는 실험이다.\n")

    # 조건마다 자 전부의 지목을 한 번씩만 받아둔다 (추론이 제일 비싸다)
    raw: dict[str, dict] = {}
    totals: dict[str, int] = {}
    for name in conditions:
        cond = config._BY_NAME[name]
        raw[name] = {}
        for kind in KINDS:
            got = collect(kind, args.seed, cond, args.limit)
            if got is None:
                print(f"  [{kind}] 자 없음 — 건너뜀")
                continue
            raw[name][kind], totals[name] = got
        print(f"  {name:<16} 자별 지목 "
              f"{ {k: len(v) for k, v in raw[name].items()} }")

    rows = []
    # 단일 자 (기준선) + 2대·3대 합의
    combos = [(k,) for k in KINDS]
    combos += list(itertools.combinations(KINDS, 2))
    combos += list(itertools.combinations(KINDS, 3))

    for combo in combos:
        need = len(combo)                      # 전원 합의
        per_k = {k: [] for k in KS}
        n_flags, short = [], 0
        for name in conditions:
            cond = config._BY_NAME[name]
            sub = {k: raw[name][k] for k in combo if k in raw[name]}
            if len(sub) < len(combo):
                continue
            merged = consensus(sub, need) if need > 1 else list(next(iter(sub.values())))
            scored = E.score_findings(cond, merged, totals[name], args.limit)
            v = scored["verdicts_by_rank"]
            n_flags.append(len(v))
            if len(v) < DECIDE_K:
                short += 1
            if not v:
                continue
            for k in KS:
                per_k[k].append(E.precision_at_k(v, k))
        rows.append({
            "combo": list(combo),
            "labels": [RULERS[k][0] for k in combo],
            "n_rulers": len(combo),
            "precision_at": {str(k): statistics.mean(per_k[k]) if per_k[k] else None
                             for k in KS},
            "mean_flags": statistics.mean(n_flags) if n_flags else 0,
            "conditions_short_of_k": short,
        })
        p10 = rows[-1]["precision_at"][str(DECIDE_K)]
        print(f"  {'+'.join(RULERS[k][0] for k in combo):<44} "
              f"정밀도@{DECIDE_K} {p10:.3f}  지목 평균 {rows[-1]['mean_flags']:.0f}건")

    Path(args.out).write_text(json.dumps(
        {"seed": args.seed, "limit": args.limit, "ks": KS, "decide_k": DECIDE_K,
         "conditions": conditions, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n저장 → {args.out}")
    report(rows)


def report(rows: list) -> None:
    single = [r for r in rows if r["n_rulers"] == 1]
    best_single = max(single, key=lambda r: r["precision_at"][str(DECIDE_K)])
    base = best_single["precision_at"][str(DECIDE_K)]

    print("\n" + "=" * 70)
    print(f"합의가 단일 최고를 이기나 (정밀도@{DECIDE_K})")
    print("=" * 70)
    print(f"단일 최고: {best_single['labels'][0]} {base:.3f}")
    print("성공 기준은 +5%p 이상 (AM의 시드 산포 ±4.2~5.4%p). 먼저 정해둔 값이다.\n")

    for n in (2, 3):
        group = [r for r in rows if r["n_rulers"] == n]
        if not group:
            continue
        gains = [r["precision_at"][str(DECIDE_K)] - base for r in group]
        won = sum(1 for g in gains if g >= 0.05)
        print(f"자 {n}대 합의 — 조합 {len(group)}개")
        print(f"  정밀도@{DECIDE_K}  최고 {max(r['precision_at'][str(DECIDE_K)] for r in group):.3f}"
              f"  중앙 {statistics.median(r['precision_at'][str(DECIDE_K)] for r in group):.3f}"
              f"  최저 {min(r['precision_at'][str(DECIDE_K)] for r in group):.3f}")
        print(f"  단일 최고 대비  최고 {max(gains):+.3f}  중앙 {statistics.median(gains):+.3f}")
        print(f"  +5%p 이상 오른 조합: {won}/{len(group)}")
        print(f"  지목 평균 {statistics.mean(r['mean_flags'] for r in group):.0f}건 "
              f"(단일 {best_single['mean_flags']:.0f}건)")
        short = sum(r["conditions_short_of_k"] for r in group)
        print(f"  {DECIDE_K}건을 못 채운 (조합,조건) 쌍: {short}\n")


if __name__ == "__main__":
    main()
