"""재검수를 실제로 수행해 재학습하는 실험 — recovered@k가 자기 채점인 문제를 푼다.

R에서 클래스 가중 정렬이 recovered@k를 17.3% → 43.1%로 올렸다. 그런데 그
지표의 가중치가 곧 클래스 취약도라, **취약도로 만든 순서를 취약도로 만든
지표로 평가한** 셈이다. 유리하게 나올 수밖에 없다.

여기서는 지표를 우회한다. 큐 상위 k건을 실제로 고친 라벨셋을 만들어 재학습하고,
mAP가 얼마나 회복되는지 본다. 이건 순서가 무엇이든 같은 잣대다.

"고친다"는 완벽한 검수자를 가정한다 — 지목된 박스를 GT로 되돌린다:
  기하 오류    가장 잘 맞는 GT 박스로 교체
  누락        해당 GT 박스를 추가
  중복        그 줄을 삭제
  클래스 불일치  클래스를 GT 값으로 교정
  오탐        이미 맞는 라벨이라 GT로 되돌려도 사실상 무변화 (검수자가 헛본 것)

**어느 박스를 고칠지는 큐만 정한다.** injection_record는 쓰지 않는다 — 그걸
쓰면 정답을 보고 고르는 게 되어 순서 비교가 무의미해진다. GT는 "고르기"가
아니라 "고치기"에만 쓴다.

사용법:
  python simulate_review.py --condition scale_m30 --order class_weighted --fraction 0.25
"""
import argparse
import random
import sys
from pathlib import Path

from PIL import Image

import config
from diagnose_labels import (CLEAN_WEIGHTS, IMAGE_SUFFIXES, PREDICT_CONFIDENCE_FLOOR,
                             load_yolo_labels_with_classes)
from error_injector import pixel_to_yolo_line, symlink_files, write_data_yaml
from label_diagnosis import Box, diagnose_image, iou, rescore, review_value, summarize

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ORDERS = ("severity", "class_weighted", "random")
# 지목된 박스를 GT의 어느 박스로 되돌릴지 정할 최소 겹침.
# 이보다 안 겹치면 대응하는 GT가 없다고 보고 그 줄을 지운다(허위 라벨 제거).
FIX_MATCH_IOU = 0.3


def diagnose(condition_root: Path) -> tuple[list, dict]:
    """조건 데이터셋 전체를 진단해 순위 매기기 전 findings를 돌려준다."""
    from ultralytics import YOLO

    images_dir = condition_root / "images" / "train"
    labels_dir = condition_root / "labels" / "train"
    paths = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    model = YOLO(str(CLEAN_WEIGHTS))
    findings, total_labels = [], 0

    for start in range(0, len(paths), 16):
        batch = paths[start:start + 16]
        results = model.predict([str(p) for p in batch], imgsz=config.IMG_SIZE,
                                device=config.resolve_device(),
                                conf=PREDICT_CONFIDENCE_FLOOR, verbose=False)
        for path, res in zip(batch, results):
            with Image.open(path) as img:
                w, h = img.width, img.height
            labels, label_classes = load_yolo_labels_with_classes(
                labels_dir / f"{path.stem}.txt", w, h)
            total_labels += len(labels)
            xyxy = res.boxes.xyxy.tolist() if res.boxes is not None else []
            confs = res.boxes.conf.tolist() if res.boxes is not None else []
            pred_classes = ([int(c) for c in res.boxes.cls.tolist()]
                            if res.boxes is not None else [])
            findings += diagnose_image(
                path.name, [tuple(b) for b in xyxy], confs, labels,
                pred_classes=pred_classes if config.MULTICLASS else None,
                label_classes=label_classes if config.MULTICLASS else None,
                class_names=config.CLASS_NAMES if config.MULTICLASS else None,
            )
    summary = summarize(findings, total_labels)
    return rescore(findings, summary), summary


def rank(findings: list, order: str, seed: int) -> list:
    if order == "severity":
        return sorted(findings, key=lambda f: -f.severity)
    if order == "class_weighted":
        return sorted(findings, key=lambda f: -review_value(f))
    shuffled = list(findings)
    random.Random(seed).shuffle(shuffled)
    return shuffled


def apply_fixes(condition_root: Path, out_root: Path, chosen: list) -> dict:
    """지목된 박스를 GT로 되돌린 라벨셋을 만든다. 나머지 줄은 그대로 둔다."""
    by_image: dict[str, list] = {}
    for f in chosen:
        by_image.setdefault(f.image, []).append(f)

    src_labels = condition_root / "labels" / "train"
    out_labels = out_root / "labels" / "train"
    out_labels.mkdir(parents=True, exist_ok=True)
    stats = {"replaced": 0, "inserted": 0, "deleted": 0, "reclassed": 0}

    for src in sorted(src_labels.glob("*.txt")):
        image_name = None
        for suffix in IMAGE_SUFFIXES:
            cand = condition_root / "images" / "train" / f"{src.stem}{suffix}"
            if cand.exists():
                image_name = cand.name
                break
        lines = [l for l in src.read_text().splitlines() if l.strip()]
        picked = by_image.get(image_name or "", [])
        if not picked:
            (out_labels / src.name).write_text("\n".join(lines) + ("\n" if lines else ""))
            continue

        with Image.open(condition_root / "images" / "train" / image_name) as img:
            w, h = img.width, img.height
        gt_boxes, gt_classes = load_yolo_labels_with_classes(
            config.LABELS_GT_TRAIN_DIR / src.name, w, h)

        drop: set[int] = set()
        replace: dict[int, str] = {}
        insert: list[str] = []

        for f in picked:
            if f.label_index is None:          # 누락 — GT 박스를 되살린다
                gi = _best_gt(f.box, gt_boxes)
                if gi is not None:
                    insert.append(pixel_to_yolo_line(gt_boxes[gi], w, h, gt_classes[gi]))
                    stats["inserted"] += 1
                continue
            if f.suspicion == "duplicate":     # 중복 — 그 줄을 지운다
                drop.add(f.label_index)
                stats["deleted"] += 1
                continue
            gi = _best_gt(f.box, gt_boxes)
            if gi is None:                     # 대응 GT 없음 = 허위 라벨
                drop.add(f.label_index)
                stats["deleted"] += 1
                continue
            replace[f.label_index] = pixel_to_yolo_line(gt_boxes[gi], w, h, gt_classes[gi])
            stats["reclassed" if f.suspicion == "class_mismatch" else "replaced"] += 1

        out = [replace.get(i, l) for i, l in enumerate(lines) if i not in drop] + insert
        (out_labels / src.name).write_text("\n".join(out) + ("\n" if out else ""))

    return stats


def _best_gt(box: Box, gt_boxes: list[Box]) -> int | None:
    best, best_i = FIX_MATCH_IOU, None
    for i, g in enumerate(gt_boxes):
        v = iou(box, g)
        if v >= best:
            best, best_i = v, i
    return best_i


def main() -> None:
    parser = argparse.ArgumentParser(description="재검수 시뮬레이션 + 라벨셋 생성")
    parser.add_argument("--condition", required=True)
    parser.add_argument("--order", choices=ORDERS, required=True)
    parser.add_argument("--fraction", type=float, required=True,
                        help="큐 상위 몇 %%를 고칠지 (0.25 = 상위 25%%)")
    parser.add_argument("--seed", type=int, default=config.SEED,
                        help="random 순서용 시드")
    args = parser.parse_args()

    root = config.CONDITIONS_DIR / args.condition
    if not root.is_dir():
        raise SystemExit(f"{root} 없음")

    findings, summary = diagnose(root)
    ranked = rank(findings, args.order, args.seed)
    # fraction 0은 "아무것도 안 고친 사본". 기존 조건은 workers=8로 학습돼
    # 있어서, 같은 워커 설정의 기준선을 따로 만들어야 비교가 성립한다.
    k = 0 if args.fraction <= 0 else max(1, int(len(ranked) * args.fraction))
    chosen = ranked[:k]

    tag = (f"{args.condition}_asis" if k == 0 else
           f"{args.condition}_fix_{args.order}_{int(args.fraction * 100)}")
    out_root = config.CONDITIONS_DIR / tag
    # 라벨이 있는 프레임만 링크한다 — 이미지 폴더는 구성 간 공유라서 그냥
    # 통째로 링크하면 라벨 없는 이미지가 배경으로 학습된다
    train_stems = {p.stem for p in config.LABELS_GT_TRAIN_DIR.glob("*.txt")}
    val_stems = {p.stem for p in config.LABELS_GT_VAL_DIR.glob("*.txt")}
    symlink_files(config.IMAGES_TRAIN_DIR, out_root / "images" / "train", train_stems)
    symlink_files(config.IMAGES_VAL_DIR, out_root / "images" / "val", val_stems)
    symlink_files(config.LABELS_GT_VAL_DIR, out_root / "labels" / "val", val_stems)
    stats = apply_fixes(root, out_root, chosen)
    yaml_path = write_data_yaml(out_root)

    print(f"[{tag}] 진단 {len(findings)}건 중 상위 {k}건 수정")
    print(f"  교체 {stats['replaced']} / 추가 {stats['inserted']} / "
          f"삭제 {stats['deleted']} / 클래스교정 {stats['reclassed']}")
    print(f"  → {out_root}\n  → {yaml_path}")


if __name__ == "__main__":
    main()
