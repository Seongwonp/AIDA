"""KITTI 원본 라벨 → YOLO 포맷 변환 + train/val 고정 분할.

- config.CLASS_NAMES에 있는 클래스만 추출한다 (기본값은 Car 하나. DontCare 등
  나머지는 라벨에서 아예 제외 — YOLO 학습에 negative/ignore로 관여하지 않도록 함).
  CLASS_NAMES 순서가 곧 YOLO 클래스 인덱스다.
- train/val 분할은 SEED로 고정하며, 이후 모든 오류 조건(error_injector.py)과
  학습(train.py)에서 동일한 분할을 재사용한다. 그래야 조건 간 성능 차이가
  순수하게 라벨 오류 때문이라고 말할 수 있다.
- 여기서 생성하는 labels_gt/*는 "참값(GT)"이다. error_injector.py가 이를
  읽어 조건별로 변형한 라벨을 conditions/<name>/labels/train/에 별도로 만든다.
  labels_gt/val은 모든 조건에서 그대로 평가셋으로 재사용된다 (변형하지 않음).
"""
import random
import shutil
from pathlib import Path

from PIL import Image

import config

KITTI_LABEL_COLUMNS = [
    "type", "truncated", "occluded", "alpha",
    "bbox_left", "bbox_top", "bbox_right", "bbox_bottom",
    "dim_h", "dim_w", "dim_l", "loc_x", "loc_y", "loc_z", "rotation_y",
]


def parse_kitti_label(label_path: Path) -> list[dict]:
    boxes = []
    for line in label_path.read_text().splitlines():
        if not line.strip():
            continue
        fields = line.split(" ")
        row = dict(zip(KITTI_LABEL_COLUMNS, fields))
        if row["type"] not in config.CLASS_IDS:
            continue
        boxes.append({
            "class_id": config.CLASS_IDS[row["type"]],
            "class_name": row["type"],
            "left": float(row["bbox_left"]),
            "top": float(row["bbox_top"]),
            "right": float(row["bbox_right"]),
            "bottom": float(row["bbox_bottom"]),
        })
    return boxes


def to_yolo_line(box: dict, img_w: int, img_h: int) -> str:
    cx = (box["left"] + box["right"]) / 2 / img_w
    cy = (box["top"] + box["bottom"]) / 2 / img_h
    w = (box["right"] - box["left"]) / img_w
    h = (box["bottom"] - box["top"]) / img_h
    return f"{box['class_id']} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def split_frames(frame_ids: list[str]) -> tuple[list[str], list[str]]:
    rng = random.Random(config.SEED)
    shuffled = frame_ids.copy()
    rng.shuffle(shuffled)
    train = sorted(shuffled[: config.N_TRAIN])
    val = sorted(shuffled[config.N_TRAIN: config.N_TRAIN + config.N_VAL])
    return train, val


def build_split(frame_ids: list[str], image_src_dir: Path, label_src_dir: Path,
                 image_dst_dir: Path, label_dst_dir: Path) -> int:
    image_dst_dir.mkdir(parents=True, exist_ok=True)
    label_dst_dir.mkdir(parents=True, exist_ok=True)
    n_objects = 0
    for fid in frame_ids:
        src_img = image_src_dir / f"{fid}.png"
        img = Image.open(src_img)
        boxes = parse_kitti_label(label_src_dir / f"{fid}.txt")
        n_objects += len(boxes)
        lines = [to_yolo_line(b, img.width, img.height) for b in boxes]
        (label_dst_dir / f"{fid}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        shutil.copy(src_img, image_dst_dir / f"{fid}.png")
    return n_objects


def to_yolo_obb_line(box: dict, img_w: int, img_h: int) -> str:
    """KITTI AABB → YOLO OBB polygon 포맷 (angle=0, TL→TR→BR→BL 순서).

    KITTI 정면 카메라 특성상 차량은 거의 수평이므로 angle=0이 참값이다.
    OBB 오류 주입 시에는 이 polygon을 회전시켜 오류 각도를 표현한다.
    """
    left, top, right, bottom = box["left"], box["top"], box["right"], box["bottom"]
    # 4 꼭짓점 정규화 (TL, TR, BR, BL)
    pts = [
        (left / img_w, top / img_h),
        (right / img_w, top / img_h),
        (right / img_w, bottom / img_h),
        (left / img_w, bottom / img_h),
    ]
    coords = " ".join(f"{x:.6f} {y:.6f}" for x, y in pts)
    return f"{config.CLASS_ID} {coords}"


def build_obb_split(frame_ids: list[str], image_src_dir: Path, label_src_dir: Path,
                    image_dst_dir: Path, label_dst_dir: Path) -> int:
    """KITTI 라벨을 OBB polygon 포맷(angle=0)으로 변환해 저장한다."""
    image_dst_dir.mkdir(parents=True, exist_ok=True)
    label_dst_dir.mkdir(parents=True, exist_ok=True)
    n_objects = 0
    for fid in frame_ids:
        src_img = image_src_dir / f"{fid}.png"
        img = Image.open(src_img)
        boxes = parse_kitti_label(label_src_dir / f"{fid}.txt")
        n_objects += len(boxes)
        lines = [to_yolo_obb_line(b, img.width, img.height) for b in boxes]
        (label_dst_dir / f"{fid}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        # 이미지는 AABB 실험과 동일하므로 복사 불필요 (error_injector_obb.py가 symlink 재사용)
    return n_objects


def main():
    selection_file = config.RAW_DIR / "selected_frames.txt"
    if not selection_file.exists():
        raise RuntimeError("download_kitti.py를 먼저 실행하세요 (selected_frames.txt 없음)")
    frame_ids = selection_file.read_text().split()

    train_ids, val_ids = split_frames(frame_ids)
    print(f"분할: train {len(train_ids)}장 / val {len(val_ids)}장 (시드={config.SEED})")

    image_src_dir = config.RAW_DIR / "training" / "image_2"
    label_src_dir = config.RAW_DIR / "training" / "label_2"

    n_train_obj = build_split(train_ids, image_src_dir, label_src_dir,
                               config.IMAGES_TRAIN_DIR, config.LABELS_GT_TRAIN_DIR)
    n_val_obj = build_split(val_ids, image_src_dir, label_src_dir,
                             config.IMAGES_VAL_DIR, config.LABELS_GT_VAL_DIR)

    print(f"{'/'.join(config.CLASS_NAMES)} 객체 수: train {n_train_obj}개 / val {n_val_obj}개")
    print(f"완료 → {config.PROCESSED_DIR}")


def main_obb():
    """OBB 실험용 GT 라벨(polygon 포맷)을 생성한다.

    AABB 실험의 data_loader.main()이 이미 완료된 상태를 전제한다
    (selected_frames.txt와 이미지가 있어야 함).
    """
    selection_file = config.RAW_DIR / "selected_frames.txt"
    if not selection_file.exists():
        raise RuntimeError("download_kitti.py → data_loader.py 순서로 먼저 실행하세요")

    frame_ids = selection_file.read_text().split()
    train_ids, val_ids = split_frames(frame_ids)

    image_src_dir = config.RAW_DIR / "training" / "image_2"
    label_src_dir = config.RAW_DIR / "training" / "label_2"

    n_train = build_obb_split(train_ids, image_src_dir, label_src_dir,
                               config.IMAGES_TRAIN_DIR, config.OBB_LABELS_GT_TRAIN_DIR)
    n_val = build_obb_split(val_ids, image_src_dir, label_src_dir,
                             config.IMAGES_VAL_DIR, config.OBB_LABELS_GT_VAL_DIR)
    print(f"OBB GT 라벨 생성 완료: train {n_train}개 / val {n_val}개 → {config.PROCESSED_DIR}")


if __name__ == "__main__":
    main()
