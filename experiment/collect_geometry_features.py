"""기하 오류 의심 박스(width/height/scale/translation)의 맥락 특성 수집.

collect_missing_features.py의 자매 스크립트다. 누락에서 통한 방법 — 규칙을
추측으로 만들지 말고 진짜/오탐을 실제로 가르는 게 뭔지 먼저 재기 — 을
기하 유형에 적용한다.

지금 가장 약한 고리는 width다(정밀도 48.9%, 891건 지목 중 절반이 헛걸음).
classify_geometry가 width를 "나머지" 바구니로 쓰는 구조라 노이즈가 몰릴
소지가 있다: 크기 편차가 임계값을 넘었는데 스케일도 이동도 아니면, 가로·세로
중 더 큰 쪽으로 부르기 때문이다.

사용법:
  python collect_geometry_features.py --limit 80
  → geometry_features.csv
"""
import argparse
import csv
import json
from pathlib import Path

from PIL import Image

import config
from diagnose_labels import IMAGE_SUFFIXES, PREDICT_CONFIDENCE_FLOOR, load_yolo_labels
from label_diagnosis import (
    CENTER_SHIFT_THRESHOLD, SIZE_DEVIATION_THRESHOLD, Box,
    center_size, covered_ratio, iou, match_boxes,
)
from evaluate_box_accuracy import _errored_index_for, _type_matches, load_injection_record

OUT_CSV = config.EXPERIMENT_ROOT / "geometry_features.csv"
GEOMETRIC = {"width", "height", "scale", "translation_x", "translation_y"}


def raw_geometry(pred: Box, label: Box) -> dict:
    """classify_geometry가 쓰는 원시 편차를 전부 남긴다 (판정 전 단계)."""
    p_cx, p_cy, p_w, p_h = center_size(pred)
    l_cx, l_cy, l_w, l_h = center_size(label)
    if p_w <= 0 or p_h <= 0:
        return {}
    dx = (l_cx - p_cx) / p_w
    dy = (l_cy - p_cy) / p_h
    w_dev = l_w / p_w - 1
    h_dev = l_h / p_h - 1
    return {"dx": dx, "dy": dy, "w_dev": w_dev, "h_dev": h_dev,
            "p_w": p_w, "p_h": p_h, "l_w": l_w, "l_h": l_h}


def classify(g: dict) -> tuple[str, float] | None:
    """label_diagnosis.classify_geometry와 같은 판정 (유형, 원시신호)."""
    shift = max(abs(g["dx"]), abs(g["dy"]))
    size_dev = max(abs(g["w_dev"]), abs(g["h_dev"]))
    if shift >= CENTER_SHIFT_THRESHOLD and shift > size_dev:
        if abs(g["dx"]) >= abs(g["dy"]):
            return "translation_x", min(abs(g["dx"]), 1.0)
        return "translation_y", min(abs(g["dy"]), 1.0)
    if size_dev < SIZE_DEVIATION_THRESHOLD:
        return None
    both = (abs(g["w_dev"]) >= SIZE_DEVIATION_THRESHOLD
            and abs(g["h_dev"]) >= SIZE_DEVIATION_THRESHOLD)
    if both and (g["w_dev"] > 0) == (g["h_dev"] > 0):
        return "scale", min(abs((g["w_dev"] + g["h_dev"]) / 2), 1.0)
    if abs(g["w_dev"]) >= abs(g["h_dev"]):
        return "width", min(abs(g["w_dev"]), 1.0)
    return "height", min(abs(g["h_dev"]), 1.0)


def collect(images_dir: Path, labels_dir: Path, record: dict,
            condition: str, cond_type: str, limit: int | None) -> list[dict]:
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

            matched, _, _ = match_boxes(predictions, labels)
            entry = record.get(path.stem, {"errored": [], "dropped": []})

            for li, pi in matched.items():
                g = raw_geometry(predictions[pi], labels[li])
                if not g:
                    continue
                verdict = classify(g)
                if verdict is None or verdict[0] not in GEOMETRIC:
                    continue
                suspicion, raw = verdict

                hit = _errored_index_for(cond_type, li, entry["errored"])
                is_tp = hit is not None
                others = [b for j, b in enumerate(labels) if j != li]

                rows.append({
                    "condition": condition,
                    "cond_type": cond_type,
                    "suspicion": suspicion,
                    # 이 조건이 이 유형의 오류를 실제로 주입했는가
                    "type_injected": int(_type_matches(cond_type, suspicion)),
                    "image": path.name,
                    "tp": int(is_tp),
                    # 판정에 쓰이는 원시 편차들
                    "raw": round(raw, 4),
                    "w_dev": round(g["w_dev"], 4),
                    "h_dev": round(g["h_dev"], 4),
                    "dx": round(g["dx"], 4),
                    "dy": round(g["dy"], 4),
                    # 결정력: 1등 신호가 2등을 얼마나 앞서는가.
                    # 작으면 유형 판정이 동전 던지기에 가깝다.
                    "margin": round(abs(g["w_dev"]) - abs(g["h_dev"]), 4),
                    "shift_vs_size": round(max(abs(g["dx"]), abs(g["dy"]))
                                           - max(abs(g["w_dev"]), abs(g["h_dev"])), 4),
                    # 매칭 품질
                    "match_iou": round(iou(predictions[pi], labels[li]), 3),
                    "conf": round(confs[pi] if pi < len(confs) else 0.0, 4),
                    # 박스 자체
                    "p_h": round(g["p_h"], 1),
                    "p_w": round(g["p_w"], 1),
                    "aspect": round(g["p_w"] / g["p_h"], 3) if g["p_h"] else -1.0,
                    "area_frac": round(g["p_w"] * g["p_h"] / (img_w * img_h), 6),
                    # 맥락
                    "n_labels": len(labels),
                    "covered_by_others": round(covered_ratio(labels[li], others), 3),
                    "touches_edge": int(labels[li][0] <= 2 or labels[li][1] <= 2
                                        or labels[li][2] >= img_w - 2
                                        or labels[li][3] >= img_h - 2),
                })
    return rows


def main():
    parser = argparse.ArgumentParser(description="기하 오류 의심 박스 특성 수집")
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--conditions", nargs="+")
    args = parser.parse_args()

    conditions = [c for c in config.conditions_in_run_order()]
    if args.conditions:
        conditions = [config._BY_NAME[n] for n in args.conditions]

    rows: list[dict] = []
    for i, cond in enumerate(conditions, 1):
        root = config.CONDITIONS_DIR / cond.name
        if not root.is_dir():
            print(f"[{cond.name}] 폴더 없음 — 건너뜀")
            continue
        try:
            record = load_injection_record(cond.name)
        except RuntimeError:
            record = {}
        print(f"[{i}/{len(conditions)}] {cond.name} 수집 중...", flush=True)
        rows += collect(root / "images" / "train", root / "labels" / "train",
                        record, cond.name, cond.type, args.limit)

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
