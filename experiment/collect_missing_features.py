"""누락 의심 박스의 맥락 특성을 모아 CSV로 떨군다 — 오탐 필터 설계용.

누락 판정은 지금 "짝 없는 예측의 확신도 >= 0.5" 하나로만 한다. 그런데 유형별
정밀도가 존재할 때 71~83%로 8개 유형 중 꼴찌다. 원인은 KITTI가 원거리·가려진
차를 Car로 라벨링하지 않는 데 있다 — 모델은 그걸 정상 탐지하지만 정답 라벨이
없으니 "누락"으로 오인된다.

확신도 말고 어떤 맥락 신호가 진짜 누락(주입해서 지운 박스)과 KITTI 관행에서
오는 오탐을 가르는지 실측한다. 여기서는 판단하지 않고 특성만 모은다.

사용법:
  python collect_missing_features.py --limit 80
  → missing_features.csv
"""
import argparse
import csv
import json
from pathlib import Path

from PIL import Image

import config
from diagnose_labels import IMAGE_SUFFIXES, PREDICT_CONFIDENCE_FLOOR, load_yolo_labels
from label_diagnosis import (
    MATCH_IOU_THRESHOLD, MISSING_CONFIDENCE_THRESHOLD, Box,
    center_size, iou, match_boxes,
)
from evaluate_box_accuracy import MISSING_MATCH_IOU, load_injection_record

OUT_CSV = config.EXPERIMENT_ROOT / "missing_features.csv"

# 누락이 실제로 주입된 조건 + 안 된 조건을 섞어야, 오탐만 걸러내고 진짜는
# 남기는 필터를 만들 수 있다. 안 된 조건에서 나온 누락 의심은 전부 오탐이다.
DEFAULT_CONDITIONS = [
    "missing_10", "missing_20", "missing_30",
    "clean", "scale_m30", "width_m30", "trans_x_p15", "duplicate_20",
]
DEFAULT_MIXED = ["mix_scale_missing", "mix_missing_scale", "mix_missing_duplicate"]


def covered_ratio(box: Box, others: list[Box]) -> float:
    """box가 다른 박스들에 얼마나 가려져 있는가 (교집합/자기면적의 최대값).

    IoU와 다르다 — 작은 박스가 큰 박스 안에 완전히 들어가면 IoU는 낮지만
    이 값은 1.0이다. KITTI에서 가려진 차가 라벨에서 빠지는 경우를 잡는다.
    """
    l, t, r, b = box
    area = max(r - l, 0) * max(b - t, 0)
    if area <= 0:
        return 0.0
    best = 0.0
    for o in others:
        ol, ot, orr, ob = o
        iw = max(min(r, orr) - max(l, ol), 0)
        ih = max(min(b, ob) - max(t, ot), 0)
        best = max(best, iw * ih / area)
    return best


def collect(images_dir: Path, labels_dir: Path, record: dict, condition: str,
            has_missing: bool, limit: int | None) -> list[dict]:
    from ultralytics import YOLO
    from diagnose_labels import CLEAN_WEIGHTS

    image_paths = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if limit:
        image_paths = image_paths[:limit]

    model = YOLO(str(CLEAN_WEIGHTS))
    rows: list[dict] = []

    for start in range(0, len(image_paths), 16):
        batch = image_paths[start:start + 16]
        results = model.predict(
            [str(p) for p in batch], imgsz=config.IMG_SIZE,
            device=config.resolve_device(), conf=PREDICT_CONFIDENCE_FLOOR, verbose=False,
        )
        for path, result in zip(batch, results):
            with Image.open(path) as img:
                img_w, img_h = img.width, img.height
            labels = load_yolo_labels(labels_dir / f"{path.stem}.txt", img_w, img_h)
            xyxy = result.boxes.xyxy.tolist() if result.boxes is not None else []
            confs = result.boxes.conf.tolist() if result.boxes is not None else []
            predictions: list[Box] = [tuple(b) for b in xyxy]  # type: ignore[misc]

            _, unmatched_preds, _ = match_boxes(predictions, labels)
            entry = record.get(path.stem, {"errored": [], "dropped": []}) if record else \
                {"errored": [], "dropped": []}

            # 라벨 박스들의 크기 분포 — "이 이미지에서 라벨링된 차들에 비해
            # 이 예측이 얼마나 작은가"를 재기 위한 기준
            label_heights = sorted(center_size(b)[3] for b in labels)
            med_h = label_heights[len(label_heights) // 2] if label_heights else 0.0
            min_h = label_heights[0] if label_heights else 0.0

            for pi in unmatched_preds:
                conf = confs[pi] if pi < len(confs) else 0.0
                if conf < MISSING_CONFIDENCE_THRESHOLD:
                    continue
                box = predictions[pi]
                cx, cy, w, h = center_size(box)

                # 정답 판정: 이 예측이 실제로 지워진 박스를 가리키는가
                is_tp = False
                for (dcx, dcy, dw, dh) in entry["dropped"]:
                    gt = ((dcx - dw / 2) * img_w, (dcy - dh / 2) * img_h,
                          (dcx + dw / 2) * img_w, (dcy + dh / 2) * img_h)
                    if iou(box, gt) >= MISSING_MATCH_IOU:
                        is_tp = True
                        break

                max_label_iou = max((iou(box, l) for l in labels), default=0.0)
                rows.append({
                    "condition": condition,
                    "has_missing": int(has_missing),
                    "image": path.name,
                    "tp": int(is_tp),
                    "conf": round(conf, 4),
                    # 절대 크기 — KITTI 난이도 기준이 박스 높이(px)다
                    "h_px": round(h, 1),
                    "w_px": round(w, 1),
                    "area_frac": round(w * h / (img_w * img_h), 6),
                    # 상대 크기 — 같은 이미지의 라벨된 차들 대비
                    "h_vs_median": round(h / med_h, 3) if med_h else -1.0,
                    "h_vs_min": round(h / min_h, 3) if min_h else -1.0,
                    # 맥락
                    "n_labels": len(labels),
                    "max_label_iou": round(max_label_iou, 3),
                    "covered_by_labels": round(covered_ratio(box, labels), 3),
                    # 화면 경계 접촉 (잘린 객체)
                    "touches_edge": int(box[0] <= 2 or box[1] <= 2
                                        or box[2] >= img_w - 2 or box[3] >= img_h - 2),
                    # 세로 위치 — 원거리 차는 소실점 근처(위쪽)에 모인다
                    "cy_frac": round(cy / img_h, 3),
                })
    return rows


def main():
    parser = argparse.ArgumentParser(description="누락 의심 박스 특성 수집")
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--conditions", nargs="+", default=DEFAULT_CONDITIONS)
    parser.add_argument("--mixed", nargs="+", default=DEFAULT_MIXED)
    args = parser.parse_args()

    rows: list[dict] = []

    for name in args.conditions:
        cond = config._BY_NAME[name]
        root = config.CONDITIONS_DIR / name
        try:
            record = load_injection_record(name)
        except RuntimeError:
            record = {}
        print(f"[{name}] 수집 중...")
        rows += collect(root / "images" / "train", root / "labels" / "train",
                        record, name, cond.type == "missing", args.limit)

    for name in args.mixed:
        root = config.MIXED_CONDITIONS_DIR / name
        if not root.is_dir():
            print(f"[{name}] 폴더 없음 — 건너뜀")
            continue
        rec_path = root / "injection_record.json"
        record = json.loads(rec_path.read_text(encoding="utf-8")) if rec_path.exists() else {}
        mixed = next((m for m in config.MIXED_CONDITIONS if m.name == name), None)
        has_missing = bool(mixed and "missing" in (mixed.primary_type, mixed.secondary_type))
        print(f"[{name}] 수집 중...")
        rows += collect(root / "images" / "train", root / "labels" / "train",
                        record, name, has_missing, args.limit)

    if not rows:
        raise SystemExit("수집된 행 없음")

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    n_tp = sum(r["tp"] for r in rows)
    print(f"\n총 {len(rows)}건 (TP {n_tp} / FP {len(rows) - n_tp}) → {OUT_CSV}")


if __name__ == "__main__":
    main()
