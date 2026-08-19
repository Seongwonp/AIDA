"""OBB 조건별 YOLOv8n-OBB 파인튜닝.

기존 train.py(AABB)와 독립적으로 동작한다. 모델만 yolov8n-obb.pt로 바뀌고
나머지 하이퍼파라미터(epochs, batch, imgsz, seed)는 config와 동일하게 유지해
AABB 실험과 공정하게 비교할 수 있다.
"""
import argparse

from ultralytics import YOLO

import config
from evaluate_obb import append_obb_metrics, evaluate_obb_condition


def train_obb_condition(condition: config.Condition, epochs: int | None = None) -> None:
    yaml_path = config.OBB_DATA_YAML_DIR / f"{condition.name}.yaml"
    if not yaml_path.exists():
        raise RuntimeError(f"{yaml_path} 없음 — run_obb.py 또는 error_injector.py를 먼저 실행하세요")

    model = YOLO("yolov8n-obb.pt")
    model.train(
        data=str(yaml_path),
        epochs=epochs or config.EPOCHS,
        batch=config.BATCH_SIZE,
        imgsz=config.IMG_SIZE,
        device=config.resolve_device(),
        seed=config.SEED,
        project=str(config.OBB_RUNS_DIR),
        name=condition.name,
        exist_ok=True,
        verbose=False,
    )
    weights = config.OBB_RUNS_DIR / condition.name / "weights" / "best.pt"
    print(f"[OBB {condition.name}] 학습 완료 → {weights}")


def main():
    parser = argparse.ArgumentParser(description="OBB 조건별 YOLOv8n-OBB 파인튜닝")
    parser.add_argument("--condition", help="특정 조건 이름 하나만 학습 (예: obb_clean)")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--evaluate", action="store_true", help="학습 직후 평가까지 실행")
    args = parser.parse_args()

    conditions = (
        [config._OBB_BY_NAME[args.condition]] if args.condition
        else config.OBB_CONDITIONS
    )
    for condition in conditions:
        train_obb_condition(condition, epochs=args.epochs)
        if args.evaluate:
            append_obb_metrics(evaluate_obb_condition(condition))


if __name__ == "__main__":
    main()
