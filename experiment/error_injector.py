"""조건별 에러 바운딩박스 생성기.

`labels_gt/train`(참값)을 읽어 조건별로 라벨의 30%만 무작위로 변형하고
`conditions/<name>/`에 YOLO 학습용 데이터셋(심볼릭 링크 이미지 + 변형 라벨)을
만든다. 평가셋(`labels_gt/val`)은 어떤 조건에서도 변형하지 않고 그대로
공유한다 — 그래야 "같은 잣대"로 조건별 성능을 비교할 수 있다.

- 크기 오류: `w, h *= (1 + magnitude/100)`, 중심 고정
- 회전 오류: 박스 네 꼭짓점을 중심 기준 `magnitude`도(度)만큼 회전 →
  회전된 꼭짓점을 감싸는 축정렬 사각형으로 재계산 (KITTI/YOLO는 회전 박스 미지원)
"""
import math
import os
import random
from pathlib import Path

import yaml
from PIL import Image

import config
from config import Condition

Box = tuple[float, float, float, float]  # left, top, right, bottom (pixel)


def yolo_to_pixel(line: str, img_w: int, img_h: int) -> Box:
    _, cx, cy, w, h = line.split()
    cx, cy, w, h = float(cx) * img_w, float(cy) * img_h, float(w) * img_w, float(h) * img_h
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def pixel_to_yolo_line(box: Box, img_w: int, img_h: int) -> str:
    left, top, right, bottom = box
    cx = (left + right) / 2 / img_w
    cy = (top + bottom) / 2 / img_h
    w = (right - left) / img_w
    h = (bottom - top) / img_h
    cx, cy = min(max(cx, 0.0), 1.0), min(max(cy, 0.0), 1.0)
    w, h = min(max(w, 0.0), 1.0), min(max(h, 0.0), 1.0)
    return f"{config.CLASS_ID} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def apply_width(box: Box, magnitude_pct: float) -> Box:
    left, top, right, bottom = box
    cx = (left + right) / 2
    new_w = (right - left) * (1 + magnitude_pct / 100)
    return cx - new_w / 2, top, cx + new_w / 2, bottom


def apply_height(box: Box, magnitude_pct: float) -> Box:
    left, top, right, bottom = box
    cy = (top + bottom) / 2
    new_h = (bottom - top) * (1 + magnitude_pct / 100)
    return left, cy - new_h / 2, right, cy + new_h / 2


def apply_rotation(box: Box, angle_deg: float) -> Box:
    left, top, right, bottom = box
    cx, cy = (left + right) / 2, (top + bottom) / 2
    corners = [(left, top), (right, top), (right, bottom), (left, bottom)]
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    rotated = []
    for x, y in corners:
        dx, dy = x - cx, y - cy
        rx = dx * cos_t - dy * sin_t
        ry = dx * sin_t + dy * cos_t
        rotated.append((cx + rx, cy + ry))
    xs = [p[0] for p in rotated]
    ys = [p[1] for p in rotated]
    return min(xs), min(ys), max(xs), max(ys)


def transform_box(box: Box, condition: Condition) -> Box:
    if condition.type == "none":
        return box
    if condition.type == "width":
        return apply_width(box, condition.magnitude)
    if condition.type == "height":
        return apply_height(box, condition.magnitude)
    if condition.type == "rotation":
        return apply_rotation(box, condition.magnitude)
    raise ValueError(f"unknown condition type: {condition.type}")


def build_condition_labels(condition: Condition, image_dir: Path, gt_label_dir: Path, out_label_dir: Path) -> None:
    out_label_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(f"{config.SEED}:{condition.name}")

    for gt_path in sorted(gt_label_dir.glob("*.txt")):
        lines = [l for l in gt_path.read_text().splitlines() if l.strip()]
        if not lines:
            (out_label_dir / gt_path.name).write_text("")
            continue

        img = Image.open(image_dir / f"{gt_path.stem}.png")
        out_lines = []
        for line in lines:
            box = yolo_to_pixel(line, img.width, img.height)
            if condition.type != "none" and rng.random() < config.ERROR_RATIO:
                box = transform_box(box, condition)
            out_lines.append(pixel_to_yolo_line(box, img.width, img.height))
        (out_label_dir / gt_path.name).write_text("\n".join(out_lines) + "\n")


def symlink_files(src_dir: Path, dst_dir: Path) -> None:
    """dst_dir 자체는 실제 디렉토리로 만들고, 그 안의 파일들만 심볼릭 링크한다.

    dst_dir을 통째로 심볼릭 링크하면 ultralytics가 data.yaml 경로를 resolve()할 때
    실제 원본 디렉토리로 역참조되어 조건별 labels 디렉토리를 못 찾는 문제가 생긴다
    (예: conditions/clean/images/train → resolve → data/processed/images/train,
    거기서 "images"→"labels" 치환하면 conditions/clean이 아닌 엉뚱한 경로가 됨).
    파일 단위 심볼릭 링크는 이 문제 없이 실제 이미지 복사 없이 디스크를 절약한다.

    Windows는 심볼릭 링크 생성에 관리자 권한/개발자 모드가 필요하다
    (`WinError 1314`). 권한이 없으면 하드 링크(`os.link`)로 대체한다 — 같은
    볼륨 안에서는 하드 링크도 디스크 복제 없이 동일한 효과를 낸다.
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    for src_file in src_dir.iterdir():
        dst_file = dst_dir / src_file.name
        if dst_file.exists() or dst_file.is_symlink():
            continue
        try:
            dst_file.symlink_to(src_file.resolve())
        except OSError:
            os.link(src_file.resolve(), dst_file)


def write_data_yaml(condition_root: Path) -> Path:
    data = {
        "path": str(condition_root.resolve()),
        "train": "images/train",
        "val": "images/val",
        "names": {config.CLASS_ID: config.TARGET_CLASS},
    }
    yaml_path = config.DATA_YAML_DIR / f"{condition_root.name}.yaml"
    config.DATA_YAML_DIR.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return yaml_path


def build_condition(condition: Condition) -> Path:
    root = config.CONDITIONS_DIR / condition.name
    symlink_files(config.IMAGES_TRAIN_DIR, root / "images" / "train")
    symlink_files(config.IMAGES_VAL_DIR, root / "images" / "val")
    symlink_files(config.LABELS_GT_VAL_DIR, root / "labels" / "val")

    build_condition_labels(
        condition,
        image_dir=config.IMAGES_TRAIN_DIR,
        gt_label_dir=config.LABELS_GT_TRAIN_DIR,
        out_label_dir=root / "labels" / "train",
    )
    yaml_path = write_data_yaml(root)
    print(f"[{condition.name}] 라벨/데이터셋 생성 완료 → {root} (data.yaml: {yaml_path})")
    return yaml_path


def main():
    for condition in config.conditions_in_run_order():
        build_condition(condition)


if __name__ == "__main__":
    main()
