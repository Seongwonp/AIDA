"""무너진 자에게 신뢰도 바닥이 너무 높은가 (docs/23 계획 A).

AI에서 자가 어긋나면 상위 10% 정밀도가 94% → 26%로 떨어졌다. 그런데 무너지는
것은 정밀도가 아니라 **재현율**이다(−18% 대 −43%). BB의 식으로 옮기면 "잡음이
늘어서"가 아니라 **"신호가 바닥 아래로 내려가서"**이고, 그 바닥은 우리가 정한
상수다.

`PREDICT_CONFIDENCE_FLOOR`(0.25)는 KITTI 자기 도메인에서 정해졌고 **어긋난
자에서 다시 본 적이 없다.** 두 자의 예측 분포가 크게 다른데도 같은 값을 쓴다.

성공 기준은 `PREDICTION_conf_floor.md`에 먼저 적었다.

사용법:
  AIDA_DATASET=coco python confidence_floor.py --seed 42 \
      --kinds coco_self kitti_on_coco --matched-kind coco_self \
      --floors 0.10 0.15 0.25 0.40 --out conf_42.json
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config                                    # noqa: E402
import diagnose_labels as D                      # noqa: E402
import evaluate_box_accuracy as E                # noqa: E402
import label_diagnosis as L                      # noqa: E402
from compare_rulers_seeded import RULERS, ruler_path  # noqa: E402

KS = [5, 10, 20]


def main() -> None:
    ap = argparse.ArgumentParser(description="신뢰도 바닥을 바꾸면")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--kinds", nargs="+", required=True)
    ap.add_argument("--matched-kind", required=True)
    ap.add_argument("--floors", type=float, nargs="+",
                    default=[0.10, 0.15, 0.25, 0.40])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    names = [c.name for c in config.conditions_in_run_order() if c.name != "clean"]
    print(f"조건 {len(names)}개 · 자 {len(args.kinds)}종 · 시드 {args.seed}")
    print(f"바닥 {args.floors} (현행 {D.PREDICT_CONFIDENCE_FLOOR})\n")

    baseline = D.PREDICT_CONFIDENCE_FLOOR
    rows = []
    try:
        for kind in args.kinds:
            w = ruler_path(kind, args.seed)
            if not w.exists():
                print(f"  [{kind}] 자 없음 — 건너뜀")
                continue
            for floor in args.floors:
                # 제품 상수를 갈아끼운다. 기준선을 코드에서 물려받지 않도록
                # 매번 명시적으로 넣는다 (docs/21 AT·AU에서 낸 사고).
                D.PREDICT_CONFIDENCE_FLOOR = floor
                prec = {k: [] for k in KS}
                true_ratios, medians, promoted_hits, n_pred = [], [], 0, []
                n_cond = 0
                for name in names:
                    cond = config._BY_NAME[name]
                    root = config.CONDITIONS_DIR / cond.name
                    findings, total_labels, fit = D.run(
                        root / "images" / "train", root / "labels" / "train",
                        args.limit, weights=w)
                    v = E.score_findings(cond, findings, total_labels,
                                         args.limit)["verdicts_by_rank"]
                    if not v:
                        continue
                    n_cond += 1
                    for k in KS:
                        prec[k].append(E.precision_at_k(v, k))
                    summary = L.summarize(findings, total_labels)
                    by = {t["suspicion"]: t["ratio"] for t in summary["by_type"]}
                    true_ratios.append(max(
                        (r for s, r in by.items() if E._type_matches(cond.type, s)),
                        default=0.0))
                    medians.append(statistics.median(by.values()) if by else 0.0)
                    promoted_hits += any(E._type_matches(cond.type, t)
                                         for t in L.present_types(summary))
                    n_pred.append(fit["predictions"])
                row = {
                    "kind": kind, "label": RULERS[kind][0], "floor": floor,
                    "n_conditions": n_cond,
                    "precision": {str(k): statistics.mean(prec[k]) for k in KS},
                    "true_ratio": statistics.mean(true_ratios),
                    "median_ratio": statistics.mean(medians),
                    "promoted": promoted_hits,
                    "predictions": statistics.mean(n_pred),
                }
                rows.append(row)
                p = row["precision"]
                print(f"  {row['label']:<16} 바닥 {floor:.2f}  "
                      f"@5 {p['5']:.3f}  @10 {p['10']:.3f}  @20 {p['20']:.3f}  "
                      f"진짜비율 {row['true_ratio']:.3f}  승격 {promoted_hits}/{n_cond}")
    finally:
        D.PREDICT_CONFIDENCE_FLOOR = baseline

    Path(args.out).write_text(json.dumps(
        {"seed": args.seed, "matched_kind": args.matched_kind, "ks": KS, "rows": rows},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {args.out}")


if __name__ == "__main__":
    main()
