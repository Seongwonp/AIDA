"""자를 다시 학습하면 예측이 얼마나 달라지는가 — AG 설명의 직접 검사.

AG에서 자 4종의 안정성 순서가 정확도 순서와 거의 같은 걸 보고 "잘 맞는
자는 예측이 결정 경계에서 멀어 시드가 바뀌어도 판정이 잘 안 뒤집힌다"고
설명했다.

check_confidence_margin.py로 "문턱에서 먼가"를 재봤더니 자기 도메인 자만
맞고 나머지 셋은 구별이 안 됐다(24.9 / 25.0 / 28.5%). 먼 이동 자는 문턱
근처가 가장 많은데도 두 번째로 안정적이라 반례다.

그래서 한 단계 앞을 본다: **같은 이미지에 대해 시드만 다른 자들의 예측이
서로 얼마나 다른가.** 진단이 흔들리는 직접적인 원인은 예측이 흔들리는
것이므로, 이게 맞는 층위다.

세 가지로 잰다:
  - 박스 개수 변동: 시드마다 몇 개를 예측하는가
  - 짝지어진 박스의 신뢰도 차이: 같은 물체에 대해 얼마나 다르게 확신하는가
  - 짝이 없는 박스 비율: 한 시드에만 있고 다른 시드엔 없는 예측

사용법:
  AIDA_CLASSES=... AIDA_FRAME_SELECT=cyclist_rich python check_prediction_drift.py
"""
import itertools
import json
import statistics
import sys
from pathlib import Path

import config
from label_diagnosis import iou

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RULERS = [
    ("자기 도메인", "runs_mc_cyclist_rich"),
    ("먼 이동(1C)", "runs"),
    ("약한 이동", "runs_mc"),
    ("넓은 자(800)", "runs_mc_broad_n800"),
]
SEEDS = [42, 123, 2024, 7]
MATCH_IOU = 0.5          # 같은 물체를 가리키는 예측으로 볼 최소 겹침


def run_dir(base: str, seed: int) -> Path:
    return config.EXPERIMENT_ROOT / base / ("clean" if seed == 42 else f"clean_ts{seed}")


def predict(weights: Path, paths: list[Path]) -> list[list[tuple]]:
    """이미지마다 [(x1,y1,x2,y2,conf,cls), ...]."""
    from ultralytics import YOLO
    model = YOLO(str(weights))
    out = []
    for path in paths:
        r = model.predict(str(path), verbose=False)[0]
        out.append([tuple(b.xyxy[0].tolist()) + (float(b.conf[0]), int(b.cls[0]))
                    for b in r.boxes])
    return out


def compare(a: list[list[tuple]], b: list[list[tuple]]) -> dict:
    """두 시드의 예측을 이미지마다 짝지어 비교한다."""
    conf_diffs, unmatched, counts_a, counts_b = [], 0, 0, 0
    for boxes_a, boxes_b in zip(a, b):
        counts_a += len(boxes_a)
        counts_b += len(boxes_b)
        used = set()
        for box_a in boxes_a:
            best, best_iou = None, MATCH_IOU
            for j, box_b in enumerate(boxes_b):
                if j in used:
                    continue
                v = iou(box_a[:4], box_b[:4])
                if v >= best_iou:
                    best, best_iou = j, v
            if best is None:
                unmatched += 1
            else:
                used.add(best)
                conf_diffs.append(abs(box_a[4] - boxes_b[best][4]))
    total = max(counts_a, 1)
    return {
        "count_diff_ratio": abs(counts_a - counts_b) / total,
        "unmatched_ratio": unmatched / total,
        "mean_conf_diff": statistics.mean(conf_diffs) if conf_diffs else 0.0,
    }


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="시드가 바뀌면 예측이 얼마나 달라지나")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    images_dir = config.CONDITIONS_DIR / "clean" / "images" / "train"
    paths = sorted(p for p in images_dir.iterdir()
                   if p.suffix.lower() in {".png", ".jpg", ".jpeg"})[:args.limit]
    print(f"이미지 {len(paths)}장 · 시드 {SEEDS} · 짝짓기 IoU {MATCH_IOU}\n")

    ag_sd = {"자기 도메인": 2.20, "먼 이동(1C)": 2.59, "넓은 자(800)": 3.27,
             "약한 이동": 5.45}
    results = {}
    for label, base in RULERS:
        preds = {}
        for seed in SEEDS:
            w = run_dir(base, seed) / "weights" / "best.pt"
            if w.exists():
                preds[seed] = predict(w, paths)
        if len(preds) < 2:
            print(f"  {label}: 시드가 부족하다 — 건너뜀")
            continue
        pairs = [compare(preds[x], preds[y])
                 for x, y in itertools.combinations(sorted(preds), 2)]
        results[label] = {
            "n_seeds": len(preds),
            "unmatched_ratio": statistics.mean(p["unmatched_ratio"] for p in pairs),
            "mean_conf_diff": statistics.mean(p["mean_conf_diff"] for p in pairs),
            "count_diff_ratio": statistics.mean(p["count_diff_ratio"] for p in pairs),
        }
        r = results[label]
        print(f"■ {label} (시드 {r['n_seeds']}개, 쌍 {len(pairs)}개)")
        print(f"    짝 없는 예측 {r['unmatched_ratio']*100:5.1f}%  "
              f"신뢰도 차이 {r['mean_conf_diff']:.3f}  "
              f"개수 차이 {r['count_diff_ratio']*100:4.1f}%")

    print(f"\nAG의 안정성 순서와 대조")
    print(f"  {'자':<14}{'AG 표준편차':>12}{'짝없음':>9}{'신뢰도차':>10}")
    for label in sorted(results, key=lambda l: ag_sd[l]):
        r = results[label]
        print(f"  {label:<14}{ag_sd[label]:>11.2f}{r['unmatched_ratio']*100:>8.1f}%"
              f"{r['mean_conf_diff']:>10.3f}")

    if args.out:
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"\n저장 → {args.out}")


if __name__ == "__main__":
    main()
