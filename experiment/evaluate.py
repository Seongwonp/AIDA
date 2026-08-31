"""조건별 학습된 모델(best.pt)을 공통 평가셋(val)으로 평가하고 metrics.csv를 갱신.

backend/app/data/metrics.csv와 동일한 스키마로 기록하므로, 대시보드 백엔드는
코드 수정 없이 실제 실험 결과를 그대로 반영한다 (docs/04-api-reference.md 참고).
"""
import argparse

import pandas as pd
from ultralytics import YOLO

import config

METRICS_COLUMNS = ["condition", "type", "magnitude", "map50", "map50_95", "precision", "recall"]


def evaluate_condition(condition: config.Condition) -> dict:
    yaml_path = config.DATA_YAML_DIR / f"{condition.name}.yaml"
    weights = config.RUNS_DIR / condition.name / "weights" / "best.pt"
    if not weights.exists():
        raise RuntimeError(f"{weights} 없음 — 먼저 train.py로 '{condition.name}' 조건을 학습하세요")

    model = YOLO(str(weights))
    metrics = model.val(
        data=str(yaml_path),
        imgsz=config.IMG_SIZE,
        device=config.resolve_device(),
        split="val",
        verbose=False,
        project=str(config.RUNS_DIR),
        name=f"{condition.name}_val",
        exist_ok=True,
    )
    return {
        "condition": condition.name,
        "type": condition.type,
        "magnitude": condition.magnitude,
        "map50": round(float(metrics.box.map50), 3),
        "map50_95": round(float(metrics.box.map), 3),
        "precision": round(float(metrics.box.mp), 3),
        "recall": round(float(metrics.box.mr), 3),
    }


def append_metrics(row: dict, csv_path=config.METRICS_CSV) -> None:
    if csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        df = pd.DataFrame(columns=METRICS_COLUMNS)

    df = df[df["condition"] != row["condition"]]  # 재실행 시 같은 조건 갱신(중복 방지)
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    # CLASS_SWAP_CONDITIONS는 CONDITIONS에 없다 — 빠뜨리면 그 행들의 정렬 키가
    # NaN이 되어 순서가 무너진다.
    order = {c.name: i for i, c in
             enumerate(config.CONDITIONS + config.CLASS_SWAP_CONDITIONS)}
    df["_order"] = df["condition"].map(order)
    df = df.sort_values("_order").drop(columns="_order")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    print(f"[{row['condition']}] metrics.csv 갱신 → {csv_path}")


def append_multi_seed_metrics(row: dict, csv_path=config.MULTI_SEED_CSV) -> None:
    """error_seed 컬럼을 포함해 누적 CSV에 저장한다 (기존 행은 덮어쓰지 않음)."""
    cols = ["error_seed"] + METRICS_COLUMNS
    if csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        df = pd.DataFrame(columns=cols)

    # 같은 (error_seed, condition) 조합은 덮어쓴다 (재실행 안전)
    mask = (df["error_seed"] == row["error_seed"]) & (df["condition"] == row["condition"])
    df = df[~mask]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df = df.sort_values(["error_seed", "condition"])

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)


def main():
    parser = argparse.ArgumentParser(description="조건별 평가 및 metrics.csv 갱신")
    parser.add_argument("--priority", choices=["1", "2", "all"], default="all")
    parser.add_argument("--condition", help="특정 조건 이름 하나만 평가 (예: clean)")
    args = parser.parse_args()

    by_name = {c.name: c for c in config.CONDITIONS}
    if args.condition:
        names = [args.condition]
    elif args.priority == "1":
        names = config.PRIORITY_1_NAMES
    elif args.priority == "2":
        names = config.PRIORITY_2_NAMES
    else:
        names = config.PRIORITY_1_NAMES + config.PRIORITY_2_NAMES

    for name in names:
        row = evaluate_condition(by_name[name])
        append_metrics(row)


if __name__ == "__main__":
    main()
