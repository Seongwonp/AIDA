"""조건별 magnitude → 평균 IoU 감소율 매핑표 (사후 계산, 재학습 불필요).

김성호 교수님 피드백(docs/11-professor-feedback.md 3번): 오류 강도를 단순 길이
증감(%, 도)이 아니라 원본 참값과의 IoU 감소량으로도 제시하면 설득력이 높아진다.
이 스크립트는 이미 만들어진 labels_gt/train(참값)에 각 조건의 변형 함수를 그대로
적용해, "이 조건이 실제로 원본 박스를 얼마나 밀어내는가"를 IoU로 정량화한다.

학습 결과(metrics.csv)와 별개로 동작하므로 GPU 학습이 끝나지 않아도, data_loader.py
실행 직후(labels_gt/train 생성 후)부터 바로 실행할 수 있다.
"""
import csv
from pathlib import Path

from PIL import Image

import config
from error_injector import transform_box, yolo_to_pixel

Box = tuple[float, float, float, float]


def iou(a: Box, b: Box) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 1.0


def mean_iou_for_condition(condition: config.Condition, label_dir: Path, image_dir: Path) -> float:
    # 주의: 여기서는 GT 박스 100%에 변형을 적용한다. 실제 학습 라벨(error_injector.py의
    # build_condition_labels)은 config.ERROR_RATIO(30%)만 무작위로 변형하므로, 이 함수의
    # 결과는 "이 조건이 이론상 얼마나 세게 박스를 왜곡하는가"이지 실제 학습에 들어간
    # 라벨의 평균 IoU가 아니다. 둘을 섞어서 비교하면 안 됨 — docs/13-ppt-visuals-checklist.md
    # 3번 항목의 "주의" 참고.
    if condition.type == "none":
        return 1.0
    if condition.type == "missing":
        # 박스가 통째로 사라지므로 "형태가 왜곡됐다"는 IoU 개념 자체가 성립하지
        # 않는다. 대신 "라벨 1개를 무작위로 뽑았을 때 그 라벨이 남아있을 확률
        # 기준 기대 IoU"로 정의한다: magnitude%는 사라지고(IoU 0) 나머지는
        # 그대로 남는다(IoU 1) → 기대값은 1 - magnitude/100.
        return 1 - condition.magnitude / 100
    if condition.type == "duplicate":
        # 원본 박스 자체는 모양이 바뀌지 않는다(IoU 1.0 유지) — duplicate는
        # 기존 박스를 왜곡하는 오류가 아니라 여분의 노이즈 박스를 추가하는
        # 오류라, IoU 감소율로는 이 조건의 심각도를 드러낼 수 없다. mAP/
        # Precision 저하율 쪽 지표로 봐야 한다.
        return 1.0
    ious = []
    for label_path in sorted(label_dir.glob("*.txt")):
        lines = [l for l in label_path.read_text().splitlines() if l.strip()]
        if not lines:
            continue
        img = Image.open(image_dir / f"{label_path.stem}.png")
        for line in lines:
            box = yolo_to_pixel(line, img.width, img.height)
            transformed = transform_box(box, condition)
            ious.append(iou(box, transformed))
    return sum(ious) / len(ious) if ious else float("nan")


def main():
    label_dir = config.LABELS_GT_TRAIN_DIR
    image_dir = config.IMAGES_TRAIN_DIR
    if not label_dir.exists():
        raise RuntimeError(f"{label_dir} 없음 — 먼저 data_loader.py를 실행하세요")

    rows = []
    for condition in config.CONDITIONS:
        mean_iou = mean_iou_for_condition(condition, label_dir, image_dir)
        rows.append({
            "condition": condition.name,
            "type": condition.type,
            "magnitude": condition.magnitude,
            "mean_iou": round(mean_iou, 4),
            "mean_iou_drop_pct": round((1 - mean_iou) * 100, 2),
        })

    out_path = config.EXPERIMENT_ROOT / "iou_table.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["condition", "type", "magnitude", "mean_iou", "mean_iou_drop_pct"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"{'조건':<12} {'유형':<10} {'강도':>6} {'평균IoU':>8} {'IoU감소율':>10}")
    for r in rows:
        print(f"{r['condition']:<12} {r['type']:<10} {r['magnitude']:>6} {r['mean_iou']:>8} {r['mean_iou_drop_pct']:>9}%")
    print(f"\n저장 완료 → {out_path}")


if __name__ == "__main__":
    main()
