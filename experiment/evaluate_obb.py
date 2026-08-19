"""OBB 조건별 평가 및 metrics_obb.csv 갱신.

evaluate.py(AABB)와 구조가 동일하지만, OBB 모델은 metrics.obb.*로 결과를 반환한다.
"""
import argparse

import pandas as pd
from ultralytics import YOLO

import config

METRICS_COLUMNS = ["condition", "type", "magnitude", "map50", "map50_95", "precision", "recall"]


def evaluate_obb_condition(condition: config.Condition) -> dict:
    yaml_path = config.OBB_DATA_YAML_DIR / f"{condition.name}.yaml"
    weights = config.OBB_RUNS_DIR / condition.name / "weights" / "best.pt"
    if not weights.exists():
        raise RuntimeError(f"{weights} 없음 — train_obb.py로 먼저 학습하세요")

    model = YOLO(str(weights))
    metrics = model.val(
        data=str(yaml_path),
        imgsz=config.IMG_SIZE,
        device=config.resolve_device(),
        split="val",
        verbose=False,
        project=str(config.OBB_RUNS_DIR),
        name=f"{condition.name}_val",
        exist_ok=True,
    )
    # OBB 모델은 metrics.obb.*로 결과를 제공한다
    obb = metrics.obb
    return {
        "condition": condition.name,
        "type": condition.type,
        "magnitude": condition.magnitude,
        "map50": round(float(obb.map50), 3),
        "map50_95": round(float(obb.map), 3),
        "precision": round(float(obb.mp), 3),
        "recall": round(float(obb.mr), 3),
    }


def append_obb_metrics(row: dict, csv_path=config.OBB_METRICS_CSV) -> None:
    if csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        df = pd.DataFrame(columns=METRICS_COLUMNS)

    df = df[df["condition"] != row["condition"]]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    order = {c.name: i for i, c in enumerate(config.OBB_CONDITIONS)}
    df["_order"] = df["condition"].map(order)
    df = df.sort_values("_order").drop(columns="_order")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    print(f"[OBB {row['condition']}] metrics_obb.csv 갱신 → {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="OBB 조건별 평가 및 metrics_obb.csv 갱신")
    parser.add_argument("--condition", help="특정 조건 하나만 평가 (예: obb_clean)")
    args = parser.parse_args()

    conditions = (
        [config._OBB_BY_NAME[args.condition]] if args.condition
        else config.OBB_CONDITIONS
    )
    for condition in conditions:
        row = evaluate_obb_condition(condition)
        append_obb_metrics(row)


if __name__ == "__main__":
    main()
