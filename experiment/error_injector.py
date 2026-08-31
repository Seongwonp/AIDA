"""조건별 에러 바운딩박스 생성기.

`labels_gt/train`(참값)을 읽어 조건별로 라벨의 30%만 무작위로 변형하고
`conditions/<name>/`에 YOLO 학습용 데이터셋(심볼릭 링크 이미지 + 변형 라벨)을
만든다. 평가셋(`labels_gt/val`)은 어떤 조건에서도 변형하지 않고 그대로
공유한다 — 그래야 "같은 잣대"로 조건별 성능을 비교할 수 있다.

- 크기 오류: `w, h *= (1 + magnitude/100)`, 중심 고정
- 중심점 이동 오류: 박스 크기는 유지하고 중심만 가로/세로 길이의 `magnitude%`만큼 이동
- 스케일 오류: 가로·세로를 같은 비율로 확대/축소
- 회전 오류: 박스 네 꼭짓점을 중심 기준 `magnitude`도(度)만큼 회전 →
  회전된 꼭짓점을 감싸는 축정렬 사각형으로 재계산 (KITTI/YOLO는 회전 박스 미지원)
"""
import json
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


def class_of(line: str) -> int:
    """라벨 줄의 클래스 인덱스. 다중 클래스에서는 오류를 주입해도 보존해야 한다 —
    안 그러면 기하 오류를 넣는 김에 클래스까지 바꿔버려 조건이 오염된다."""
    return int(line.split()[0])


def pixel_to_yolo_line(box: Box, img_w: int, img_h: int, class_id: int | None = None) -> str:
    left, top, right, bottom = box
    cx = (left + right) / 2 / img_w
    cy = (top + bottom) / 2 / img_h
    w = (right - left) / img_w
    h = (bottom - top) / img_h
    cx, cy = min(max(cx, 0.0), 1.0), min(max(cy, 0.0), 1.0)
    w, h = min(max(w, 0.0), 1.0), min(max(h, 0.0), 1.0)
    cid = config.CLASS_ID if class_id is None else class_id
    return f"{cid} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


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


def apply_translation_x(box: Box, magnitude_pct: float) -> Box:
    left, top, right, bottom = box
    dx = (right - left) * magnitude_pct / 100
    return left + dx, top, right + dx, bottom


def apply_translation_y(box: Box, magnitude_pct: float) -> Box:
    left, top, right, bottom = box
    dy = (bottom - top) * magnitude_pct / 100
    return left, top + dy, right, bottom + dy


def apply_scale(box: Box, magnitude_pct: float) -> Box:
    left, top, right, bottom = box
    cx, cy = (left + right) / 2, (top + bottom) / 2
    factor = 1 + magnitude_pct / 100
    new_w = (right - left) * factor
    new_h = (bottom - top) * factor
    return cx - new_w / 2, cy - new_h / 2, cx + new_w / 2, cy + new_h / 2


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


def apply_duplicate_offset(box: Box) -> Box:
    """중복 박스용: 원본을 폭·높이의 8%만큼 살짝 어긋나게 옮긴 복제본을 만든다.

    완전히 동일한 좌표로 중복시키면 YOLO가 사실상 같은 라벨 두 번으로 보고
    학습에 영향이 거의 없다 — 실무에서 라벨러가 같은 객체를 두 번 클릭했을 때
    나오는 "비슷하지만 완전히 겹치진 않는" 중복 박스를 흉내낸다.
    """
    left, top, right, bottom = box
    w, h = right - left, bottom - top
    dx, dy = w * 0.08, h * 0.08
    return left + dx, top + dy, right + dx, bottom + dy


def transform_box(box: Box, condition: Condition) -> Box:
    if condition.type == "none":
        return box
    if condition.type == "width":
        return apply_width(box, condition.magnitude)
    if condition.type == "height":
        return apply_height(box, condition.magnitude)
    if condition.type == "translation_x":
        return apply_translation_x(box, condition.magnitude)
    if condition.type == "translation_y":
        return apply_translation_y(box, condition.magnitude)
    if condition.type == "scale":
        return apply_scale(box, condition.magnitude)
    if condition.type == "rotation":
        return apply_rotation(box, condition.magnitude)
    raise ValueError(f"unknown condition type: {condition.type}")


# missing/duplicate는 박스 모양이 아니라 "박스가 몇 개 있는가" 자체를 바꾸는
# 오류라 나머지 타입들의 transform_box 경로(1줄 입력 → 1줄 출력)로는 표현할
# 수 없다. build_condition_labels 안에서 별도 분기로 처리한다.
LINE_COUNT_CHANGING_TYPES = {"missing", "duplicate"}


def build_condition_labels(condition: Condition, image_dir: Path, gt_label_dir: Path,
                            out_label_dir: Path) -> dict[str, dict]:
    """조건별 오류 라벨을 만들고, "어느 박스에 오류를 넣었는지" 기록을 함께 반환한다.

    기록은 진단 정확도를 박스 단위로 재기 위한 정답지다
    (evaluate_box_accuracy.py). 이미지 stem별로:
      errored: 오류가 들어간 **출력 파일 기준** 라벨 인덱스
      dropped: 누락시킨 박스의 정규화 좌표 [cx, cy, w, h]

    출력 기준 인덱스인 게 중요하다 — missing은 줄을 지우고 duplicate는 줄을
    끼워 넣으므로, 입력(GT) 인덱스와 출력 인덱스가 어긋난다. 진단은 출력
    파일을 보고 "몇 번째 라벨"이라고 말하므로 정답지도 출력 기준이어야 한다.
    missing만은 가리킬 출력 줄이 아예 없어서 좌표로 기록한다.
    """
    out_label_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(f"{config.ERROR_SEED}:{condition.name}")
    record: dict[str, dict] = {}

    for gt_path in sorted(gt_label_dir.glob("*.txt")):
        lines = [l for l in gt_path.read_text().splitlines() if l.strip()]
        if not lines:
            (out_label_dir / gt_path.name).write_text("")
            continue

        img = Image.open(image_dir / f"{gt_path.stem}.png")
        out_lines = []
        errored: list[int] = []
        dropped: list[list[float]] = []
        for line in lines:
            box = yolo_to_pixel(line, img.width, img.height)
            cid = class_of(line)

            if condition.type == "missing":
                # magnitude% 확률로 이 라벨 자체를 통째로 누락시킨다 (줄을 아예 안 씀).
                if rng.random() < condition.magnitude / 100:
                    cx, cy, w, h = center_size_normalized(box, img.width, img.height)
                    dropped.append([cx, cy, w, h])
                    continue
                out_lines.append(pixel_to_yolo_line(box, img.width, img.height, cid))
            elif condition.type == "class_swap":
                # magnitude% 확률로 클래스만 다른 값으로 바꾼다. 박스 좌표는
                # 그대로 — 라벨링 현장에서 가장 흔한 오류가 좌표는 맞는데
                # 클래스를 잘못 고르는 경우다.
                if len(config.CLASS_NAMES) > 1 and rng.random() < condition.magnitude / 100:
                    others = [i for i in range(len(config.CLASS_NAMES)) if i != cid]
                    cid = rng.choice(others)
                    errored.append(len(out_lines))
                out_lines.append(pixel_to_yolo_line(box, img.width, img.height, cid))
            elif condition.type == "duplicate":
                # 원본은 그대로 두고, magnitude% 확률로 살짝 어긋난 복제 박스를 추가한다.
                out_lines.append(pixel_to_yolo_line(box, img.width, img.height, cid))
                if rng.random() < condition.magnitude / 100:
                    dup_box = apply_duplicate_offset(box)
                    # 새로 끼워 넣은 줄이 곧 오류 박스다
                    errored.append(len(out_lines))
                    out_lines.append(pixel_to_yolo_line(dup_box, img.width, img.height, cid))
            else:
                if condition.type != "none" and rng.random() < config.ERROR_RATIO:
                    box = transform_box(box, condition)
                    errored.append(len(out_lines))
                out_lines.append(pixel_to_yolo_line(box, img.width, img.height, cid))

        (out_label_dir / gt_path.name).write_text("\n".join(out_lines) + "\n")
        if errored or dropped:
            record[gt_path.stem] = {"errored": errored, "dropped": dropped}

    return record


def center_size_normalized(box: Box, img_w: int, img_h: int) -> tuple[float, float, float, float]:
    left, top, right, bottom = box
    return (
        round((left + right) / 2 / img_w, 6),
        round((top + bottom) / 2 / img_h, 6),
        round((right - left) / img_w, 6),
        round((bottom - top) / img_h, 6),
    )


def build_mixed_condition_labels(mixed: config.MixedCondition, image_dir: Path,
                                  gt_label_dir: Path, out_label_dir: Path) -> dict[str, dict]:
    """두 유형이 섞인 라벨을 만든다 (docs/21 F 재보정용).

    박스 하나에는 최대 한 유형만 주입한다 — primary에 걸리지 않은 박스만
    secondary 추첨을 받는다. 그래야 "어느 박스가 어느 유형 오류인지"가
    명확해져 2차 유형 신뢰도를 깨끗하게 잴 수 있다.

    기록에는 유형까지 남긴다(errored_types) — 단일 유형 조건과 달리 조건
    이름만으로는 그 박스가 무슨 오류인지 알 수 없기 때문이다.
    """
    out_label_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(f"{config.ERROR_SEED}:{mixed.name}")
    record: dict[str, dict] = {}

    def as_condition(kind: str, magnitude: float) -> Condition:
        return Condition(f"{mixed.name}:{kind}", kind, magnitude)

    for gt_path in sorted(gt_label_dir.glob("*.txt")):
        lines = [l for l in gt_path.read_text().splitlines() if l.strip()]
        if not lines:
            (out_label_dir / gt_path.name).write_text("")
            continue

        img = Image.open(image_dir / f"{gt_path.stem}.png")
        out_lines: list[str] = []
        errored: list[int] = []
        errored_types: list[str] = []
        dropped: list[list[float]] = []

        for line in lines:
            box = yolo_to_pixel(line, img.width, img.height)
            cid = class_of(line)
            roll = rng.random()
            if roll < mixed.primary_rate:
                kind, magnitude = mixed.primary_type, mixed.primary_magnitude
            elif roll < mixed.primary_rate + mixed.secondary_rate:
                kind, magnitude = mixed.secondary_type, mixed.secondary_magnitude
            else:
                out_lines.append(pixel_to_yolo_line(box, img.width, img.height, cid))
                continue

            if kind == "missing":
                cx, cy, w, h = center_size_normalized(box, img.width, img.height)
                dropped.append([cx, cy, w, h])
            elif kind == "duplicate":
                out_lines.append(pixel_to_yolo_line(box, img.width, img.height, cid))
                errored.append(len(out_lines))
                errored_types.append("duplicate")
                out_lines.append(
                    pixel_to_yolo_line(apply_duplicate_offset(box), img.width, img.height, cid))
            else:
                errored.append(len(out_lines))
                errored_types.append(kind)
                out_lines.append(pixel_to_yolo_line(
                    transform_box(box, as_condition(kind, magnitude)),
                    img.width, img.height, cid))

        (out_label_dir / gt_path.name).write_text("\n".join(out_lines) + "\n")
        if errored or dropped:
            record[gt_path.stem] = {
                "errored": errored,
                "errored_types": errored_types,
                "dropped": dropped,
            }
    return record


def build_mixed_condition(mixed: config.MixedCondition) -> Path:
    root = config.MIXED_CONDITIONS_DIR / mixed.name
    train_stems = {p.stem for p in config.LABELS_GT_TRAIN_DIR.glob("*.txt")}
    symlink_files(config.IMAGES_TRAIN_DIR, root / "images" / "train", train_stems)

    record = build_mixed_condition_labels(
        mixed,
        image_dir=config.IMAGES_TRAIN_DIR,
        gt_label_dir=config.LABELS_GT_TRAIN_DIR,
        out_label_dir=root / "labels" / "train",
    )
    (root / "injection_record.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8")
    n_err = sum(len(v["errored"]) for v in record.values())
    n_drop = sum(len(v["dropped"]) for v in record.values())
    print(f"[{mixed.name}] {mixed.primary_type} {mixed.primary_rate:.0%} + "
          f"{mixed.secondary_type} {mixed.secondary_rate:.0%} "
          f"→ 변형 {n_err}건 / 누락 {n_drop}건")
    return root


def symlink_files(src_dir: Path, dst_dir: Path,
                  only_stems: set[str] | None = None) -> None:
    """dst_dir 자체는 실제 디렉토리로 만들고, 그 안의 파일들만 심볼릭 링크한다.

    dst_dir을 통째로 심볼릭 링크하면 ultralytics가 data.yaml 경로를 resolve()할 때
    실제 원본 디렉토리로 역참조되어 조건별 labels 디렉토리를 못 찾는 문제가 생긴다
    (예: conditions/clean/images/train → resolve → data/processed/images/train,
    거기서 "images"→"labels" 치환하면 conditions/clean이 아닌 엉뚱한 경로가 됨).
    파일 단위 심볼릭 링크는 이 문제 없이 실제 이미지 복사 없이 디스크를 절약한다.

    Windows는 심볼릭 링크 생성에 관리자 권한/개발자 모드가 필요하다
    (`WinError 1314`). 권한이 없으면 하드 링크(`os.link`)로 대체한다 — 같은
    볼륨 안에서는 하드 링크도 디스크 복제 없이 동일한 효과를 낸다.

    **only_stems를 반드시 넘겨야 한다.** 이미지 폴더(data/processed/images/)는
    클래스 구성·프레임 선택과 무관하게 공유되며 data_loader가 실행될 때마다
    쌓인다. 반면 라벨은 구성별로 갈린다. 그래서 폴더를 통째로 링크하면 라벨이
    없는 이미지까지 딸려 들어가고, ultralytics는 그걸 "객체 없는 배경"으로
    학습한다 — 조용히, 오류 없이. 실제로 cyclist_rich 실험이 이미지 777장에
    라벨 400개로 학습돼 결과가 통째로 무효가 됐다(docs/21 S 정정).
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    if only_stems is not None:
        # 이전에 잘못 걸린 링크가 남아 있으면 지운다
        for stale in dst_dir.iterdir():
            if stale.stem not in only_stems:
                stale.unlink()
    for src_file in src_dir.iterdir():
        if only_stems is not None and src_file.stem not in only_stems:
            continue
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
        "names": dict(enumerate(config.CLASS_NAMES)),
    }
    yaml_path = config.DATA_YAML_DIR / f"{condition_root.name}.yaml"
    config.DATA_YAML_DIR.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return yaml_path


def build_condition(condition: Condition) -> Path:
    root = config.CONDITIONS_DIR / condition.name
    train_stems = {p.stem for p in config.LABELS_GT_TRAIN_DIR.glob("*.txt")}
    val_stems = {p.stem for p in config.LABELS_GT_VAL_DIR.glob("*.txt")}
    symlink_files(config.IMAGES_TRAIN_DIR, root / "images" / "train", train_stems)
    symlink_files(config.IMAGES_VAL_DIR, root / "images" / "val", val_stems)
    symlink_files(config.LABELS_GT_VAL_DIR, root / "labels" / "val", val_stems)

    record = build_condition_labels(
        condition,
        image_dir=config.IMAGES_TRAIN_DIR,
        gt_label_dir=config.LABELS_GT_TRAIN_DIR,
        out_label_dir=root / "labels" / "train",
    )
    # 박스 단위 진단 정확도의 정답지 (evaluate_box_accuracy.py가 읽는다)
    (root / "injection_record.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8"
    )
    yaml_path = write_data_yaml(root)
    print(f"[{condition.name}] 라벨/데이터셋 생성 완료 → {root} (data.yaml: {yaml_path})")
    return yaml_path


# ── OBB 오류 주입 ──────────────────────────────────────────────────────────────
# YOLO OBB polygon 포맷: class x1 y1 x2 y2 x3 y3 x4 y4 (정규화 좌표)
# 4개 꼭짓점을 직접 회전시켜 방향성이 있는 오류를 주입한다.
# AABB와의 핵심 차이: 회전 후 외접 박스(AABB)를 쓰지 않고 rotated polygon 그대로 유지.

ObbPoly = tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]


def yolo_obb_to_pixel(line: str, img_w: int, img_h: int) -> ObbPoly:
    parts = line.split()
    coords = [float(v) for v in parts[1:9]]
    return tuple((coords[i] * img_w, coords[i + 1] * img_h) for i in range(0, 8, 2))  # type: ignore[return-value]


def pixel_obb_to_yolo_line(poly: ObbPoly, img_w: int, img_h: int) -> str:
    pts = [(min(max(x / img_w, 0.0), 1.0), min(max(y / img_h, 0.0), 1.0)) for x, y in poly]
    coords = " ".join(f"{x:.6f} {y:.6f}" for x, y in pts)
    return f"{config.CLASS_ID} {coords}"


def rotate_obb_poly(poly: ObbPoly, angle_deg: float) -> ObbPoly:
    """polygon 중심 기준으로 angle_deg만큼 회전 — 방향성 있는 라벨 오류 표현."""
    cx = sum(p[0] for p in poly) / 4
    cy = sum(p[1] for p in poly) / 4
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    rotated = []
    for x, y in poly:
        dx, dy = x - cx, y - cy
        rotated.append((cx + dx * cos_t - dy * sin_t, cy + dx * sin_t + dy * cos_t))
    return tuple(rotated)  # type: ignore[return-value]


def build_obb_condition_labels(condition: config.Condition, image_dir: Path,
                                gt_label_dir: Path, out_label_dir: Path) -> None:
    """OBB GT 라벨(polygon)을 읽어 조건별 오류를 주입한다.

    rotation 조건: rotate_obb_poly()로 polygon 자체를 회전 → 방향성 보존
    그 외 조건: 중심/크기 변환 후 새 polygon 재생성 (angle=0 유지)
    """
    out_label_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(f"{config.ERROR_SEED}:{condition.name}")

    for gt_path in sorted(gt_label_dir.glob("*.txt")):
        lines = [l for l in gt_path.read_text().splitlines() if l.strip()]
        if not lines:
            (out_label_dir / gt_path.name).write_text("")
            continue

        img = Image.open(image_dir / f"{gt_path.stem}.png")
        out_lines = []
        for line in lines:
            poly = yolo_obb_to_pixel(line, img.width, img.height)
            if condition.type != "none" and rng.random() < config.ERROR_RATIO:
                if condition.type == "rotation":
                    # 핵심: polygon을 직접 회전 → 방향성 보존 (AABB 외접 박스 X)
                    poly = rotate_obb_poly(poly, condition.magnitude)
                else:
                    # 나머지 오류 유형은 AABB 변환 후 polygon 재생성
                    xs = [p[0] for p in poly]
                    ys = [p[1] for p in poly]
                    box: Box = (min(xs), min(ys), max(xs), max(ys))
                    box = transform_box(box, condition)
                    left, top, right, bottom = box
                    poly = (
                        (left, top), (right, top),
                        (right, bottom), (left, bottom),
                    )
            out_lines.append(pixel_obb_to_yolo_line(poly, img.width, img.height))
        (out_label_dir / gt_path.name).write_text("\n".join(out_lines) + "\n")


def build_obb_condition(condition: config.Condition) -> Path:
    root = config.OBB_CONDITIONS_DIR / condition.name
    train_stems = {p.stem for p in config.LABELS_GT_TRAIN_DIR.glob("*.txt")}
    val_stems = {p.stem for p in config.LABELS_GT_VAL_DIR.glob("*.txt")}
    symlink_files(config.IMAGES_TRAIN_DIR, root / "images" / "train", train_stems)
    symlink_files(config.IMAGES_VAL_DIR, root / "images" / "val", val_stems)
    symlink_files(config.OBB_LABELS_GT_VAL_DIR, root / "labels" / "val", val_stems)

    build_obb_condition_labels(
        condition,
        image_dir=config.IMAGES_TRAIN_DIR,
        gt_label_dir=config.OBB_LABELS_GT_TRAIN_DIR,
        out_label_dir=root / "labels" / "train",
    )

    data = {
        "path": str(root.resolve()),
        "train": "images/train",
        "val": "images/val",
        "names": dict(enumerate(config.CLASS_NAMES)),
    }
    config.OBB_DATA_YAML_DIR.mkdir(parents=True, exist_ok=True)
    yaml_path = config.OBB_DATA_YAML_DIR / f"{condition.name}.yaml"
    yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    print(f"[OBB {condition.name}] 데이터셋 생성 완료 → {root}")
    return yaml_path


def main():
    for condition in config.conditions_in_run_order():
        build_condition(condition)


if __name__ == "__main__":
    main()
