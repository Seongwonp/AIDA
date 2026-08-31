"""라벨 단위 진단 실행기 — clean 모델을 돌려 박스별 의심 목록을 만든다.

diagnose_upload.py(데이터셋 단위 성능 비교)와 달리, 여기서는 예측 박스와
고객 라벨을 1:1로 대조해 "몇 번 이미지의 몇 번 박스가 왜 의심스러운지"까지
내려간다. 판정 로직은 label_diagnosis.py에 순수 함수로 분리돼 있다.

사용법:
  python diagnose_labels.py --dataset-dir <경로>          # 임의 폴더 진단
  python diagnose_labels.py --upload-id <dataset_id>      # 업로드된 데이터셋
  python diagnose_labels.py --condition scale_m30         # 실험 조건 데이터셋
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from ultralytics import YOLO

import config
from label_diagnosis import (Box, BoxFinding, diagnose_image, rescore,
                             review_value, summarize)

UPLOADS_DIR = config.EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "uploads"
CLEAN_WEIGHTS = config.RUNS_DIR / "clean" / "weights" / "best.pt"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
# 이 아래 확신도의 예측은 아예 무시한다 — 모델 오탐이 진단 노이즈로 들어오는 걸
# 막는다. label_diagnosis.MISSING_CONFIDENCE_THRESHOLD(누락 판정 기준)보다
# 낮게 잡아, 크기/이동 대조에는 쓰되 누락 판정에는 안 쓰이는 구간을 남긴다.
PREDICT_CONFIDENCE_FLOOR = 0.25


def load_yolo_labels(label_path: Path, img_w: int, img_h: int) -> list[Box]:
    """YOLO 정규화 라벨(class cx cy w h)을 픽셀 Box로 바꾼다."""
    return load_yolo_labels_with_classes(label_path, img_w, img_h)[0]


def load_yolo_labels_with_classes(
    label_path: Path, img_w: int, img_h: int
) -> tuple[list[Box], list[int]]:
    """위와 같되 클래스 인덱스도 함께 돌려준다.

    예전에는 클래스를 그냥 버렸다. 단일 클래스에서는 문제가 없었지만
    다중 클래스에서는 사람 라벨에 자동차 예측이 붙는 짝이 생겨서, 없는
    기하 오류를 만들어냈다(docs/21 L 참고).
    """
    if not label_path.exists():
        return [], []
    boxes: list[Box] = []
    classes: list[int] = []
    for line in label_path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cx, cy, w, h = (float(v) for v in parts[1:5])
        cx, cy, w, h = cx * img_w, cy * img_h, w * img_w, h * img_h
        boxes.append((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
        classes.append(int(float(parts[0])))
    return boxes, classes


def resolve_dataset(args) -> tuple[Path, Path, str]:
    """(이미지 폴더, 라벨 폴더, 진단 이름)을 정한다.

    업로드 데이터셋(images/labels)과 실험 조건 데이터셋(images/train,
    labels/train)의 폴더 구조가 달라서 여기서 흡수한다.
    """
    if args.upload_id:
        root = UPLOADS_DIR / args.upload_id
        return root / "images", root / "labels", args.upload_id
    if args.condition:
        root = config.CONDITIONS_DIR / args.condition
        return root / "images" / "train", root / "labels" / "train", args.condition
    root = Path(args.dataset_dir).resolve()
    images = root / "images"
    # 조건 데이터셋 구조도 --dataset-dir로 받을 수 있게 허용
    if (images / "train").is_dir():
        return images / "train", root / "labels" / "train", root.name
    return images, root / "labels", root.name


def run(images_dir: Path, labels_dir: Path, limit: int | None = None) -> tuple[list[BoxFinding], int]:
    if not CLEAN_WEIGHTS.exists():
        raise RuntimeError(f"{CLEAN_WEIGHTS} 없음 — clean 조건을 먼저 학습하세요")
    if not images_dir.is_dir():
        raise RuntimeError(f"{images_dir} 없음")

    image_paths = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if limit:
        image_paths = image_paths[:limit]
    if not image_paths:
        raise RuntimeError(f"{images_dir}에 이미지가 없습니다")

    model = YOLO(str(CLEAN_WEIGHTS))
    findings: list[BoxFinding] = []
    total_labels = 0

    # 이미지를 한 장씩 넘기면 GPU 호출 오버헤드가 커서, 배치로 끊어 예측한다.
    batch_size = 16
    for start in range(0, len(image_paths), batch_size):
        batch = image_paths[start:start + batch_size]
        results = model.predict(
            [str(p) for p in batch],
            imgsz=config.IMG_SIZE,
            device=config.resolve_device(),
            conf=PREDICT_CONFIDENCE_FLOOR,
            verbose=False,
        )
        for path, result in zip(batch, results):
            with Image.open(path) as img:
                img_w, img_h = img.width, img.height
            labels, label_classes = load_yolo_labels_with_classes(
                labels_dir / f"{path.stem}.txt", img_w, img_h)
            total_labels += len(labels)

            xyxy = result.boxes.xyxy.tolist() if result.boxes is not None else []
            confs = result.boxes.conf.tolist() if result.boxes is not None else []
            pred_classes = ([int(c) for c in result.boxes.cls.tolist()]
                            if result.boxes is not None else [])
            predictions: list[Box] = [tuple(b) for b in xyxy]  # type: ignore[misc]

            # 클래스가 하나뿐이면 클래스 대조는 아무 의미가 없으므로 넘기지
            # 않는다 — 예전 동작(Car 단일 결과 A~K)을 그대로 재현하기 위함이다.
            findings.extend(diagnose_image(
                path.name, predictions, confs, labels,
                pred_classes=pred_classes if config.MULTICLASS else None,
                label_classes=label_classes if config.MULTICLASS else None,
                class_names=config.CLASS_NAMES if config.MULTICLASS else None,
            ))

    return findings, total_labels


def build_result(name: str, findings: list[BoxFinding], total_labels: int, top_n: int) -> dict:
    # 2패스 구조: 이미지별 진단은 데이터셋 전체를 못 보므로 보수적인 신뢰도로
    # 점수를 매겨두고, summarize()가 대표 오류 유형을 확정한 뒤 rescore()가
    # 그 유형의 severity를 올린다. 그래야 "이 데이터셋의 문제는 누락"이라는
    # 판정과 재검수 목록의 순서가 어긋나지 않는다.
    summary = summarize(findings, total_labels)
    findings = rescore(findings, summary)

    # 재검수 우선순위. 이게 AIDA가 원래 약속한 산출물이다.
    #
    # 심각도(진짜 오류일 확률) 순으로 정렬한다.
    #
    # R에서 한때 재검수 가치(심각도 × 클래스 취약도)로 바꿨었다. 근거는
    # recovered@k가 17.3% → 43.1%로 올랐다는 것이었는데, **그 지표의 가중치가
    # 곧 클래스 취약도라 자기 채점이었다.** T에서 상위 k건을 실제로 고쳐
    # 재학습해 mAP로 재보니 두 정렬이 구분되지 않았다(상위 25%에서 +0.0543 vs
    # +0.0553, 상위 50%에서 +0.0477 vs +0.0377, 잡음 ±0.0185).
    #
    # 반면 클래스 가중은 상위 10% 정밀도를 97.2% → 89.1%로 확실히 깎는다.
    # 확인된 비용은 있고 확인된 이득은 없으므로 되돌린다. review_value는
    # 남겨둔다 — 표본을 늘리면 판단이 달라질 수 있다.
    ranked = sorted(findings, key=lambda f: -f.severity)
    return {
        "dataset": name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "review_queue": [
            {
                "rank": i + 1,
                "image": f.image,
                "label_index": f.label_index,
                "suspicion": f.suspicion,
                "severity": f.severity,
                "detail": f.detail,
            }
            for i, f in enumerate(ranked[:top_n])
        ],
        "total_in_queue": len(ranked),
        "caveat": (
            "기준 모델(clean)의 예측과 라벨을 대조한 결과입니다. 모델 예측 자체도 "
            "완벽하지 않으므로 확정 오류가 아니라 재검수 우선순위로 활용하세요."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="라벨 단위 진단")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset-dir", help="images/ labels/ 를 담은 폴더")
    source.add_argument("--upload-id", help="업로드된 dataset_id")
    source.add_argument("--condition", help="실험 조건 이름 (예: scale_m30)")
    parser.add_argument("--limit", type=int, help="이미지 수 제한 (빠른 확인용)")
    parser.add_argument("--top-n", type=int, default=100, help="재검수 목록 길이")
    parser.add_argument("--out", help="결과 JSON 저장 경로")
    args = parser.parse_args()

    images_dir, labels_dir, name = resolve_dataset(args)
    findings, total_labels = run(images_dir, labels_dir, args.limit)
    result = build_result(name, findings, total_labels, args.top_n)

    out_path = Path(args.out) if args.out else None
    if out_path is None and args.upload_id:
        out_path = UPLOADS_DIR / args.upload_id / "label_diagnosis.json"
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = result["summary"]
    print(f"[{name}] 라벨 {summary['total_labels']}개 중 {summary['total_findings']}개 의심 "
          f"({summary['suspicion_ratio'] * 100:.1f}%)")
    for row in summary["by_type"]:
        print(f"  {row['suspicion']:<14} {row['count']:>5}건 ({row['ratio'] * 100:.1f}%)")
    if out_path:
        print(f"저장 → {out_path}")


if __name__ == "__main__":
    main()
