"""조건별 YOLOv8n 파인튜닝.

13개 조건을 순차 실행하되, 시간 리스크 관리를 위해 핵심 7개
(clean, width±30, height±30, rot±15)를 먼저 실행한다 (--priority 1).
세분화 6개(width±15, height±15, rot±7.5)는 --priority 2로 이어서 실행한다.
중간에 시간이 부족해 멈추더라도 핵심 실험은 이미 끝나있도록 하는 구조다
(docs/03-experiment-design.md 4절 "실행 순서" 참고).
"""
import argparse

from ultralytics import YOLO

import config
from evaluate import append_metrics, evaluate_condition


def train_condition(condition: config.Condition, epochs: int | None = None) -> None:
    yaml_path = config.DATA_YAML_DIR / f"{condition.name}.yaml"
    if not yaml_path.exists():
        raise RuntimeError(f"{yaml_path} 없음 — error_injector.py를 먼저 실행하세요")

    model = YOLO("yolov8n.pt")
    model.train(
        data=str(yaml_path),
        epochs=epochs or config.EPOCHS,
        batch=config.BATCH_SIZE,
        workers=config.WORKERS,
        imgsz=config.IMG_SIZE,
        device=config.resolve_device(),
        seed=config.TRAIN_SEED,
        project=str(config.RUNS_DIR),
        name=condition.name + config.RUN_SUFFIX,
        exist_ok=True,
        verbose=False,
    )
    weights = (config.RUNS_DIR / (condition.name + config.RUN_SUFFIX)
               / "weights" / "best.pt")
    print(f"[{condition.name}{config.RUN_SUFFIX}] 학습 완료 → {weights}")


def main():
    parser = argparse.ArgumentParser(description="조건별 YOLOv8n 파인튜닝 (핵심 7개 우선)")
    parser.add_argument("--priority", choices=["1", "2", "all"], default="all")
    parser.add_argument("--condition", help="특정 조건 이름 하나만 학습 (예: clean)")
    parser.add_argument("--epochs", type=int, default=None, help="config.EPOCHS 대신 사용 (스모크 테스트용)")
    parser.add_argument("--evaluate", action="store_true", help="조건마다 학습 직후 평가까지 실행해 metrics.csv 갱신")
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
        condition = by_name[name]
        train_condition(condition, epochs=args.epochs)
        if args.evaluate:
            append_metrics(evaluate_condition(condition))


if __name__ == "__main__":
    main()
