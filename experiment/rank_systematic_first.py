"""계통적 유형을 먼저 보여주면 어떻게 되나 (docs/21 AN).

합의 실험(계획 1번)을 하다가 더 큰 것을 찾았다. **어긋난 자에서는 재검수
목록의 맨 위가 아래보다 나쁘다.**

    어긋난 자   @5 0.276  @10 0.455  @20 0.628
    맞는 자     @5 0.952  @10 0.969  @20 0.971

우선순위 목록인데 위에서부터 볼수록 손해다. 맞는 자에서는 안 그렇다.

## 왜

심각도는 `유형 신뢰도 × 신호 세기`이고, 유형 신뢰도는 "이 유형이 계통적으로
있을 때(present)"와 "없을 때(noise)" 두 벌이 있다. 그런데 **두 벌이 겹친다** —
`class_mismatch`의 noise 값이 0.990인데 `width`의 present 값은 0.820이다.
그래서 진단이 "계통적이지 않다"고 판정한 유형이 "계통적이다"라고 판정한 유형을
누르고 목록 맨 위에 앉는다. 실제로 상위 10위의 61%가 그런 유형이고, 조건 29개
중 26개에서 1위가 그렇다.

**그 상수는 맞는 자로 잰 값이다**(docs/21 L). 자가 어긋나면 유형별로 다르게
무너지는데(AI), 상수는 그대로라 순서가 뒤집힌다.

## 처방

계통적이라고 판정한 유형을 먼저, 그 안에서 심각도 순. 추론이 더 들지 않는다.

사용법:

  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" AIDA_FRAME_SELECT=cyclist_rich \\
    ./venv/Scripts/python.exe rank_systematic_first.py --seed 42 --out rank_fix.json
"""
import argparse
import json
import statistics
import sys
from dataclasses import replace
from pathlib import Path

import config
import evaluate_box_accuracy as E
import label_diagnosis as L
from compare_rulers_seeded import RULERS, ruler_path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KINDS = ["matched", "bpoor", "bmid", "brich", "shifted", "broad"]
KS = [5, 10, 20, 50]


def rank_by_systematic_then_severity(findings: list, summary: dict) -> list:
    """계통적 유형을 먼저, 그 안에서 심각도 순.

    심각도에 1.0을 더해 앞으로 보낸다 — 심각도는 0~1이므로 유형 안의 순서는
    그대로 유지된다. 값 자체가 아니라 **순서**만 바꾸는 게 목적이다.
    """
    present = L.present_types(summary)
    return [replace(f, severity=f.severity + (1.0 if f.suspicion in present else 0.0))
            for f in findings]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from diagnose_labels import run

    names = [c.name for c in config.conditions_in_run_order() if c.name != "clean"]
    print(f"조건 {len(names)}개 · 자 {len(KINDS)}종 · 시드 {args.seed}")
    print("추론은 자·조건마다 한 번만 하고, 그 결과를 두 방식으로 채점한다.\n")

    rows = []
    for kind in KINDS:
        w = ruler_path(kind, args.seed)
        if not w.exists():
            print(f"  [{kind}] 자 없음 — 건너뜀")
            continue
        E.RULER_PATH = w
        before = {k: [] for k in KS}
        after = {k: [] for k in KS}
        top10_nonsystematic = worst_first = n_cond = 0

        for name in names:
            cond = config._BY_NAME[name]
            root = config.CONDITIONS_DIR / cond.name
            findings, total_labels, _fit = run(root / "images" / "train",
                                               root / "labels" / "train",
                                               args.limit, weights=w)
            summary = L.summarize(findings, total_labels)
            present = L.present_types(summary)

            # 지금 방식
            v = E.score_findings(cond, findings, total_labels, args.limit)["verdicts_by_rank"]
            if not v:
                continue
            n_cond += 1
            for k in KS:
                before[k].append(E.precision_at_k(v, k))

            # 처방. rescore를 감싸 순서만 바꾼다 — score_findings가 안에서
            # rescore를 부르므로 미리 바꿔봐야 덮어쓰인다(한 번 그렇게 틀렸다).
            orig = L.rescore
            try:
                L.rescore = E.rescore = (
                    lambda f, s: rank_by_systematic_then_severity(orig(f, s), s))
                v2 = E.score_findings(cond, findings, total_labels,
                                      args.limit)["verdicts_by_rank"]
            finally:
                L.rescore = E.rescore = orig
            for k in KS:
                after[k].append(E.precision_at_k(v2, k))

            ranked = sorted(orig(findings, summary), key=lambda f: -f.severity)
            top10_nonsystematic += sum(1 for f in ranked[:10] if f.suspicion not in present)
            worst_first += (bool(ranked) and ranked[0].suspicion not in present)

        row = {
            "kind": kind, "label": RULERS[kind][0], "n_conditions": n_cond,
            "before": {str(k): statistics.mean(before[k]) for k in KS},
            "after": {str(k): statistics.mean(after[k]) for k in KS},
            "top10_nonsystematic_pct": top10_nonsystematic / (n_cond * 10) if n_cond else 0,
            "rank1_nonsystematic": worst_first,
        }
        rows.append(row)
        b, a = row["before"], row["after"]
        print(f"  {row['label']:<16} @5 {b['5']:.3f}→{a['5']:.3f}  "
              f"@10 {b['10']:.3f}→{a['10']:.3f}  @20 {b['20']:.3f}→{a['20']:.3f}  "
              f"(상위10위 중 비계통 {row['top10_nonsystematic_pct']*100:.0f}%)")

    Path(args.out).write_text(json.dumps(
        {"seed": args.seed, "limit": args.limit, "ks": KS, "rows": rows},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장 → {args.out}")
    report(rows)


def report(rows: list) -> None:
    print("\n" + "=" * 72)
    print("계통적 유형을 먼저 보여주면 (정밀도, 조건 평균)")
    print("=" * 72)
    print(f"{'자':<16}{'@5':>16}{'@10':>16}{'@20':>16}")
    for r in rows:
        b, a = r["before"], r["after"]
        print(f"{r['label']:<16}"
              f"{b['5']:.3f}→{a['5']:.3f}{'':>4}"
              f"{b['10']:.3f}→{a['10']:.3f}{'':>4}"
              f"{b['20']:.3f}→{a['20']:.3f}")

    mismatched = [r for r in rows if r["kind"] != "matched"]
    matched = [r for r in rows if r["kind"] == "matched"]
    if mismatched:
        for k in ("5", "10", "20"):
            gains = [r["after"][k] - r["before"][k] for r in mismatched]
            print(f"\n어긋난 자 {len(mismatched)}대 @{k}: "
                  f"평균 {statistics.mean(gains):+.3f}  "
                  f"최저 {min(gains):+.3f}  최고 {max(gains):+.3f}")
    if matched:
        m = matched[0]
        print(f"\n맞는 자 @10: {m['before']['10']:.3f} → {m['after']['10']:.3f} "
              f"({m['after']['10'] - m['before']['10']:+.3f}) — 손해가 없어야 쓸 수 있다")


if __name__ == "__main__":
    main()
