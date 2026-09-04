"""COCO 검증셋 하나로 자들의 실력을 같은 잣대로 잰다.

AA에서 배운 것: 자마다 자기 검증셋 점수를 말하면 비교가 안 된다. COCO 자는
0.449, KITTI 자는 0.876인데 서로 다른 데이터에서 잰 값이라 "KITTI 자가 두 배
낫다"는 뜻이 전혀 아니다.

여기서는 **COCO 평가셋 하나**로 둘을 잰다. 그게 이 실험에서 자가 실제로
상대할 데이터다.

사용법:
  AIDA_DATASET=coco python bench_rulers_on_coco.py
"""
import json
import sys
from pathlib import Path

import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RULERS = [
    ("COCO 자기(1C)", "runs_coco"),
    ("KITTI→COCO(1C)", "runs"),
]
SEEDS = [42, 123, 2024]


def weights(base: str, seed: int) -> Path:
    run = "clean" if seed == 42 else f"clean_ts{seed}"
    return config.EXPERIMENT_ROOT / base / run / "weights" / "best.pt"


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="COCO 평가셋으로 자들을 같은 잣대로")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if config.DATASET != "coco":
        raise SystemExit("AIDA_DATASET=coco 로 실행할 것")

    from ultralytics import YOLO

    # clean 조건의 data.yaml이 COCO 평가셋을 가리킨다 — 오류를 주입하지 않은
    # 라벨이라 자의 실력을 재는 데 맞다.
    data_yaml = config.DATA_YAML_DIR / "clean.yaml"
    if not data_yaml.exists():
        raise SystemExit(f"{data_yaml} 없음 — error_injector.py를 먼저 돌릴 것")
    print(f"평가셋: {data_yaml}\n")

    results = {}
    for label, base in RULERS:
        rows = []
        for seed in SEEDS:
            w = weights(base, seed)
            if not w.exists():
                print(f"  [{label} seed={seed}] {w} 없음 — 건너뜀")
                continue
            m = YOLO(str(w)).val(data=str(data_yaml), verbose=False, plots=False)
            rows.append({"seed": seed, "map50": float(m.box.map50),
                         "map": float(m.box.map), "precision": float(m.box.mp),
                         "recall": float(m.box.mr)})
            r = rows[-1]
            print(f"  [{label} seed={seed}] mAP50 {r['map50']:.3f}  "
                  f"mAP50-95 {r['map']:.3f}  P {r['precision']:.3f}  R {r['recall']:.3f}")
        results[label] = rows

    print(f"\n{'자':<18}{'mAP50 평균':>12}{'±':>8}")
    print("-" * 40)
    import statistics
    for label, rows in results.items():
        if not rows:
            continue
        v = [r["map50"] for r in rows]
        sd = statistics.stdev(v) if len(v) > 1 else float("nan")
        print(f"{label:<18}{statistics.mean(v):>11.3f}{sd:>8.3f}")

    if args.out:
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"\n저장 → {args.out}")


if __name__ == "__main__":
    main()
