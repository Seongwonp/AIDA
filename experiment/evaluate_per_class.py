"""조건별 클래스별 mAP — 저하가 어느 클래스에서 오는지 본다.

전체 mAP만 보면 교란이 하나 남는다. 다중 클래스 clean 모델은 mAP50 0.599로
Car 단일(0.876)보다 훨씬 약한데, 같은 라벨 오류에서 저하율이 더 크게 나온다.
이게 **클래스가 많아서**인지 **약한 모델이라 흔들릴 여지가 커서**인지 전체
숫자로는 못 가른다.

클래스별로 보면 갈린다:
- 오류를 주입한 클래스만 떨어지면 → 라벨 오류의 직접 효과
- 안 건드린 클래스까지 같이 떨어지면 → 학습이 통째로 불안정해진 것

학습을 다시 하지 않는다. 이미 저장된 best.pt로 검증셋만 다시 돌리므로
조건당 몇 초면 끝난다.

사용법:
  python evaluate_per_class.py                 # 학습 끝난 조건 전부
  python evaluate_per_class.py --conditions clean width_m30
"""
import argparse
import csv

import config

OUT_CSV = config.EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / \
    f"metrics_per_class{config._csuffix}.csv"


def trained_conditions() -> list:
    """가중치가 있는 조건만. 학습이 진행 중이어도 끝난 것까지는 잴 수 있다."""
    all_conditions = list(config.conditions_in_run_order())
    return [c for c in all_conditions
            if (config.RUNS_DIR / c.name / "weights" / "best.pt").exists()]


def main() -> None:
    parser = argparse.ArgumentParser(description="조건별 클래스별 mAP")
    parser.add_argument("--conditions", nargs="+")
    args = parser.parse_args()

    from ultralytics import YOLO

    conditions = trained_conditions()
    if args.conditions:
        wanted = set(args.conditions)
        conditions = [c for c in conditions if c.name in wanted]
    if not conditions:
        raise SystemExit("가중치가 있는 조건이 없습니다 — 학습을 먼저 하세요")

    rows = []
    for i, c in enumerate(conditions, 1):
        weights = config.RUNS_DIR / c.name / "weights" / "best.pt"
        yaml_path = config.DATA_YAML_DIR / f"{c.name}.yaml"
        print(f"[{i}/{len(conditions)}] {c.name} ...", flush=True)
        metrics = YOLO(str(weights)).val(
            data=str(yaml_path), imgsz=config.IMG_SIZE,
            device=config.resolve_device(), verbose=False, plots=False,
        )
        row = {"condition": c.name, "type": c.type, "magnitude": c.magnitude,
               "map50": round(float(metrics.box.map50), 4)}
        # ap50는 "검증셋에 등장한 클래스" 순서다. 클래스 인덱스로 되짚지 않으면
        # 한 클래스라도 검증셋에서 빠졌을 때 이름이 통째로 밀린다.
        present = list(metrics.box.ap_class_index)
        for idx, cls_id in enumerate(present):
            name = config.CLASS_NAMES[int(cls_id)]
            row[f"map50_{name}"] = round(float(metrics.box.ap50[idx]), 4)
        rows.append(row)

    fields = ["condition", "type", "magnitude", "map50"] + \
        [f"map50_{n}" for n in config.CLASS_NAMES]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)}개 조건 → {OUT_CSV}")


if __name__ == "__main__":
    main()
