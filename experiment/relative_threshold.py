"""계통적 판정을 절대 문턱에서 상대 문턱으로 바꾸면 (docs/22 계획 1번).

AN 처방은 "계통적이라고 판정한 유형을 먼저"인데, KITTI→COCO 자에서는 계통적
유형이 하나도 안 잡혀 no-op이었다(조건 10/10). 판정 규칙이 절대 문턱
(`ratio >= 0.12`)이고, 어긋난 자의 최대 유형 비율이 0.103~0.112라 **아슬아슬하게
못 넘는다.** 대표 유형이 없어서가 아니라 지목이 여러 유형에 흩어져 분포가
납작해져서다.

상대 문턱은 "최상위 유형이 나머지보다 뚜렷하게 크면 계통적"으로 본다.
절대 문턱을 그냥 낮추지 않는 이유는, 그러면 맞는 자에서 잡음 유형까지 승격돼
지금 잘 되는 쪽을 망칠 수 있어서다.

성공 기준은 PREDICTION_relative_threshold.md에 먼저 적어뒀다.

사용법:

  AIDA_DATASET=coco ./venv/Scripts/python.exe relative_threshold.py \\
    --seed 42 --kinds coco_self kitti_on_coco --matched-kind coco_self \\
    --out relthr_coco_42.json
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import config
import evaluate_box_accuracy as E
import label_diagnosis as L
from compare_rulers_seeded import RULERS, ruler_path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KS = [5, 10, 20]


def relative_present_types(summary: dict) -> set[str]:
    """상대 문턱으로 계통적 유형을 고른다.

    절대 문턱의 절반은 넘어야 하고(완전한 잡음까지 승격되면 안 된다), 동시에
    나머지 유형의 중앙값보다 뚜렷하게 커야 한다. 둘 중 **느슨한 쪽**을 쓰면
    맞는 자에서 잡음이 새므로 **둘 다** 요구한다.
    """
    by_type = summary.get("by_type", [])
    ratios = [t["ratio"] for t in by_type]
    if not ratios:
        return set()
    med = statistics.median(ratios)
    floor = L.SYSTEMATIC_ERROR_RATIO * 0.5
    return {t["suspicion"] for t in by_type
            if t["ratio"] >= floor and t["ratio"] >= med * 2}


_ORIG_PRESENT = None


def fallback_present_types(summary: dict) -> set[str]:
    """절대 문턱이 아무것도 못 찾을 때만 상대 문턱으로 물러난다.

    상대 문턱을 항상 쓰면 **맞는 자가 손해**다(COCO 자기 −0.038 ~ −0.092).
    맞는 자에서는 절대 문턱이 이미 잘 잡고 있으므로 건드릴 이유가 없다.
    실패하는 경우는 "하나도 못 잡는" 경우이고, 그때만 물러나면 된다.

    문턱 값을 새로 고르지 않는다는 게 요점이다 — 고르면 그 값이 이 데이터에
    맞춰진 것이라 다음 데이터셋에서 또 틀린다.
    """
    absolute = _ORIG_PRESENT(summary)
    return absolute if absolute else relative_present_types(summary)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--kinds", nargs="+", required=True)
    ap.add_argument("--matched-kind", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["always", "fallback"], default="always")
    args = ap.parse_args()

    from diagnose_labels import run

    names = [c.name for c in config.conditions_in_run_order() if c.name != "clean"]
    print(f"조건 {len(names)}개 · 자 {len(args.kinds)}종 · 시드 {args.seed}")
    print("비교는 'AN만' vs 'AN + 상대 문턱'이다 — AN 없는 상태와 견주면 안 된다.\n")

    rows = []
    for kind in args.kinds:
        w = ruler_path(kind, args.seed)
        if not w.exists():
            print(f"  [{kind}] 자 없음 — 건너뜀")
            continue
        E.RULER_PATH = w
        an_only = {k: [] for k in KS}
        with_rel = {k: [] for k in KS}
        empty_abs = empty_rel = n_cond = 0

        for name in names:
            cond = config._BY_NAME[name]
            root = config.CONDITIONS_DIR / cond.name
            findings, total_labels, _fit = run(root / "images" / "train",
                                               root / "labels" / "train",
                                               args.limit, weights=w)
            summary = L.summarize(findings, total_labels)

            v = E.score_findings(cond, findings, total_labels,
                                 args.limit)["verdicts_by_rank"]
            if not v:
                continue
            n_cond += 1
            empty_abs += (not L.present_types(summary))
            empty_rel += (not relative_present_types(summary))
            for k in KS:
                an_only[k].append(E.precision_at_k(v, k))

            saved = L.present_types
            global _ORIG_PRESENT
            _ORIG_PRESENT = saved
            try:
                L.present_types = (relative_present_types if args.mode == "always"
                                   else fallback_present_types)
                v2 = E.score_findings(cond, findings, total_labels,
                                      args.limit)["verdicts_by_rank"]
            finally:
                L.present_types = saved
            for k in KS:
                with_rel[k].append(E.precision_at_k(v2, k))

        row = {"kind": kind, "label": RULERS[kind][0], "n_conditions": n_cond,
               "an_only": {str(k): statistics.mean(an_only[k]) for k in KS},
               "with_relative": {str(k): statistics.mean(with_rel[k]) for k in KS},
               "empty_absolute": empty_abs, "empty_relative": empty_rel}
        rows.append(row)
        a, b = row["an_only"], row["with_relative"]
        print(f"  {row['label']:<16} @5 {a['5']:.3f}→{b['5']:.3f}  "
              f"@10 {a['10']:.3f}→{b['10']:.3f}  @20 {a['20']:.3f}→{b['20']:.3f}  "
              f"(계통적 유형 없는 조건 {empty_abs}→{empty_rel})")

    Path(args.out).write_text(json.dumps(
        {"seed": args.seed, "kinds": args.kinds, "matched_kind": args.matched_kind,
         "ks": KS, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장 → {args.out}")

    print("\n" + "=" * 66)
    print("성공 기준: 어긋난 자 @5 +0.05 이상, 맞는 자 −0.02 이상 유지")
    print("=" * 66)
    for r in rows:
        role = "맞는 자" if r["kind"] == args.matched_kind else "어긋난 자"
        d = r["with_relative"]["5"] - r["an_only"]["5"]
        mark = ("성공" if d >= 0.05 else "유지" if d >= -0.02 else "★손해")
        print(f"  {role:<7} {r['label']:<16} @5 {d:+.3f}  {mark}")


if __name__ == "__main__":
    main()
