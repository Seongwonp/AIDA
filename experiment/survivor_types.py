"""무너진 자에서 살아남는 유형만 남기면 쓸 만한가 (docs/23 계획 1번).

AI가 "KITTI 자로 COCO를 진단하면 26%"라고 했는데, 유형별로 보면 `missing`은
0.767로 살아 있다. "전부 못 쓴다"가 아니라 "대부분 못 쓰는데 하나는 쓴다"이다.

제품에 이미 "버티는 유형만 보기" 버튼이 있는데 **그게 실제로 얼마나 나은지는
안 쟀다.** 여기서 잰다.

성공 기준은 PREDICTION_survivor_types.md에 먼저 적어뒀다.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import config
import evaluate_box_accuracy as E
from compare_rulers_seeded import RULERS, ruler_path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KS = [5, 10, 20]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--kinds", nargs="+", required=True)
    ap.add_argument("--keep", nargs="+", default=["missing"],
                    help="남길 의심 유형 (AI에서 도메인 이동에도 버틴 것)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from diagnose_labels import run

    names = [c.name for c in config.conditions_in_run_order() if c.name != "clean"]
    keep = set(args.keep)
    print(f"조건 {len(names)}개 · 자 {len(args.kinds)}종 · 시드 {args.seed}")
    print(f"남길 유형: {sorted(keep)}\n")

    rows = []
    for kind in args.kinds:
        w = ruler_path(kind, args.seed)
        if not w.exists():
            print(f"  [{kind}] 자 없음"); continue
        E.RULER_PATH = w
        allp = {k: [] for k in KS}
        keptp = {k: [] for k in KS}
        n_all, n_kept, short = [], [], 0
        # **조건 유형별로 갈라야 한다.** 26개 조건 대부분은 주입된 오류가
        # missing이 아니라서, 거기서 나온 missing 지목은 정의상 전부 오탐이다.
        # 전부 뭉쳐 평균 내면 "유형 좁히기가 해롭다"로 보이는데, 그건
        # "내 데이터의 오류가 그 유형일 때"를 안 가른 것이다.
        per_cond = []

        for name in names:
            cond = config._BY_NAME[name]
            root = config.CONDITIONS_DIR / cond.name
            findings, total, _fit = run(root / "images" / "train",
                                        root / "labels" / "train", args.limit, weights=w)
            v = E.score_findings(cond, findings, total, args.limit)["verdicts_by_rank"]
            if not v:
                continue
            n_all.append(len(v))
            for k in KS:
                allp[k].append(E.precision_at_k(v, k))

            sub = [f for f in findings if f.suspicion in keep]
            v2 = (E.score_findings(cond, sub, total, args.limit)["verdicts_by_rank"]
                  if sub else [])
            n_kept.append(len(v2))
            # 남은 게 k보다 적으면 "그 예산을 못 채운다"는 것도 결과다
            if len(v2) < 5:
                short += 1
            if v2:
                for k in KS:
                    keptp[k].append(E.precision_at_k(v2, k))
            per_cond.append({
                "condition": name, "injected_type": cond.type,
                "matches_kept": cond.type in keep or any(name.startswith(t) for t in keep),
                "all_at5": E.precision_at_k(v, 5),
                "kept_at5": E.precision_at_k(v2, 5) if v2 else None,
                "n_all": len(v), "n_kept": len(v2)})

        row = {"kind": kind, "label": RULERS[kind][0],
               "all": {str(k): statistics.mean(allp[k]) for k in KS},
               "kept": {str(k): (statistics.mean(keptp[k]) if keptp[k] else None)
                        for k in KS},
               "mean_flags_all": statistics.mean(n_all) if n_all else 0,
               "mean_flags_kept": statistics.mean(n_kept) if n_kept else 0,
               "conditions_under_5": short, "n_conditions": len(n_all),
               "per_condition": per_cond}
        rows.append(row)
        a, b = row["all"], row["kept"]
        fmt = lambda x: "—" if x is None else f"{x:.3f}"
        print(f"  {row['label']:<16} 전체 @5 {a['5']:.3f} → 유형좁힘 @5 {fmt(b['5'])}"
              f"   지목 {row['mean_flags_all']:.0f} → {row['mean_flags_kept']:.0f}건"
              f"   5건 미만인 조건 {short}/{row['n_conditions']}")

    Path(args.out).write_text(json.dumps(
        {"seed": args.seed, "keep": sorted(keep), "ks": KS, "rows": rows},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장 → {args.out}")
    print("\n성공 기준(먼저 정함): @5가 0.50 이상이면 성공, 0.35~0.50 부분, 미만 실패")


if __name__ == "__main__":
    main()
