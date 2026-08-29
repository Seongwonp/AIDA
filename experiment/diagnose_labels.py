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
from label_diagnosis import Box, BoxFinding, diagnose_image, summarize

UPLOADS_DIR = config.EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "uploads"
CLEAN_WEIGHTS = config.RUNS_DIR / "clean" / "weights" / "best.pt"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
# 이 아래 확신도의 예측은 아예 무시한다 — 모델 오탐이 진단 노이즈로 들어오는 걸
# 막는다. label_diagnosis.MISSING_CONFIDENCE_THRESHOLD(누락 판정 기준)보다
# 낮게 잡아, 크기/이동 대조에는 쓰되 누락 판정에는 안 쓰이는 구간을 남긴다.
PREDICT_CONFIDENCE_FLOOR = 0.25


def load_yolo_labels(label_path: Path, img_w: int, img_h: int) -> list[Box]:
    """YOLO 정규화 라벨(class cx cy w h)을 픽셀 Box로 바꾼다."""
    if not label_path.exists():
        return []
    boxes: list[Box] = []
    for line in label_path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cx, cy, w, h = (float(v) for v in parts[1:5])
        cx, cy, w, h = cx * img_w, cy * img_h, w * img_w, h * img_h
        boxes.append((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
    return boxes


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
            labels = load_yolo_labels(labels_dir / f"{path.stem}.txt", img_w, img_h)
            total_labels += len(labels)

            xyxy = result.boxes.xyxy.tolist() if result.boxes is not None else []
            confs = result.boxes.conf.tolist() if result.boxes is not None else []
            predictions: list[Box] = [tuple(b) for b in xyxy]  # type: ignore[misc]

            findings.extend(diagnose_image(path.name, predictions, confs, labels))

    return findings, total_labels


def build_result(name: str, findings: list[BoxFinding], total_labels: int, top_n: int) -> dict:
    # 심각도 높은 순 = 재검수 우선순위. 이게 AIDA가 원래 약속한 산출물이다.
    ranked = sorted(findings, key=lambda f: -f.severity)
    return {
        "dataset": name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summarize(findings, total_labels),
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
