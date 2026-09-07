"""조건에서 **진짜 유형의 지목 비율**이 후퇴의 바닥(0.06)을 넘는지 잰다.

AZ가 세운 식을 검증하기 위한 도구다.

    후퇴가 진짜 유형을 올린다 ⟺ 그 유형의 비율 ≥ 0.06 (그리고 중앙값의 2배)
    → 올리면 안전하고 못 올리면 손해다 (AV·AW·AX·AY)

`0.06`은 `label_diagnosis.SYSTEMATIC_ERROR_RATIO * 0.5`이고 여기서 새로 고른
값이 아니다.

사용법:
  AIDA_DATASET=coco python measure_type_ratio.py --kind coco_self \
      --conditions duplicate_5 duplicate_10 --seeds 42 123 2024
"""
import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config                                   # noqa: E402
import label_diagnosis as L                     # noqa: E402
from compare_rulers_seeded import ruler_path    # noqa: E402
from evaluate_box_accuracy import _type_matches  # noqa: E402

FLOOR = L.SYSTEMATIC_ERROR_RATIO * 0.5


def main() -> None:
    ap = argparse.ArgumentParser(description="진짜 유형의 지목 비율이 바닥을 넘는가")
    ap.add_argument("--kind", required=True)
    ap.add_argument("--conditions", nargs="+", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 123, 2024])
    ap.add_argument("--limit", type=int, default=80)
    args = ap.parse_args()

    from diagnose_labels import run

    print(f"자 {args.kind} · 바닥 {FLOOR:.3f} (= SYSTEMATIC_ERROR_RATIO × 0.5)\n")
    print(f"  {'조건':<16}{'진짜 유형 비율':>14}{'기하 최대':>11}{'중앙값':>9}  판정")
    for name in args.conditions:
        cond = config._BY_NAME[name]
        root = config.CONDITIONS_DIR / cond.name
        true_ratios, geo_ratios, medians = [], [], []
        for seed in args.seeds:
            w = ruler_path(args.kind, seed)
            if not w.exists():
                continue
            findings, total, _ = run(root / "images" / "train",
                                     root / "labels" / "train", args.limit, weights=w)
            s = L.summarize(findings, total)
            by = {t["suspicion"]: t["ratio"] for t in s["by_type"]}
            true_ratios.append(max((v for k, v in by.items()
                                    if _type_matches(cond.type, k)), default=0.0))
            geo_ratios.append(max((by.get(k, 0.0)
                                   for k in ("width", "height", "scale")), default=0.0))
            medians.append(statistics.median(by.values()) if by else 0.0)
        if not true_ratios:
            print(f"  {name:<16}자 없음")
            continue
        t, g, m = (statistics.mean(x) for x in (true_ratios, geo_ratios, medians))
        # 후퇴의 승격 조건 두 가지를 그대로 쓴다.
        verdict = "승격됨 → 안전" if (t >= FLOOR and t >= m * 2) else "못 올라감 → 손해 예상"
        print(f"  {name:<16}{t:>14.4f}{g:>11.4f}{m:>9.4f}  {verdict}")


if __name__ == "__main__":
    main()
