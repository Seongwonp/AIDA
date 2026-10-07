"""AI 비용 드라이런용 **합성** 그림 — 도로와 차를 코드로 그린다. 실제 데이터셋 그림을 한 장도 쓰지 않는다.

목적은 **비용과 API 계약 점검뿐**이다(사용자 결정 2026-10-07). 이 그림으로 낸 어떤 수치도 정확도·난이도·모델
성능·일치도의 근거가 아니다. 산출물에는 출처 표시 `synthetic_dryrun`이 붙고, 분석 경로(`analyze_qa.py`·AI 일치도)는
그 표시를 거부한다(`evaluation/provenance.py`).

전송 형식은 nuImages 본 실행과 같게 맞춘다 — 원본 크기 **1600×900**, 후보마다 `render_adjudication_images.py`가
그리는 **전체 장면 + 크롭 PNG 한 쌍**(같은 함수 `render_queue`를 그대로 부른다), 같은 색 표시.

    python make_synthetic_ai_dryrun.py --out runs_ai_dryrun/synthetic_v1 [--scenes 10] [--seed 20261007]

출력(전부 로컬, `experiment/runs_*/`는 gitignore):
  source/images/synth_###.png, source/labels/synth_###.txt   합성 원본과 YOLO 라벨
  queue.json                                                가림 AI 목록(점수·순위·판정 없음)
  rendered/<후보 id>.png, <후보 id>.full.png, manifest.json  렌더러 출력
  rendered/provenance.json                                  합성 표시와 파일별 SHA-256
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluation.provenance import (PROVENANCE_FILE, SYNTHETIC_DRYRUN, SYNTHETIC_GENERATOR,  # noqa: E402
                                   nuimages_path_hits, sha256_file)
from render_adjudication_images import render_queue  # noqa: E402

WIDTH, HEIGHT = 1600, 900          # nuImages 카메라 원본 크기와 같다
MAX_SCENES = 20                    # 합성 원본 그림 상한(사용자 결정: 최대 20장)
MAX_CANDIDATES = 20                # 드라이런 호출 상한과 같다
DEFAULT_SEED = 20261007
CLASS_NAME = "Car"
PURPOSE = ("AI 보조 판정자 비용·API 계약 점검 전용 합성 그림. 정확도·난이도·모델 성능·일치도의 근거로 쓰지 않는다.")
CAR_COLOURS = [(200, 50, 50), (50, 90, 190), (235, 235, 235), (40, 40, 40), (90, 150, 90), (220, 180, 60)]


def _draw_car(draw: ImageDraw.ImageDraw, x1: int, y1: int, w: int, h: int, colour) -> tuple[int, int, int, int]:
    """옆모습 승용차. 돌려주는 값은 차 전체(바퀴 포함) 상자."""
    body_top = y1 + int(h * 0.38)
    draw.rounded_rectangle([x1, body_top, x1 + w, y1 + int(h * 0.82)], radius=max(2, h // 8), fill=colour,
                           outline=(30, 30, 30), width=2)
    roof = [(x1 + int(w * 0.22), body_top), (x1 + int(w * 0.32), y1), (x1 + int(w * 0.68), y1),
            (x1 + int(w * 0.80), body_top)]
    draw.polygon(roof, fill=colour, outline=(30, 30, 30))
    draw.polygon([(x1 + int(w * 0.30), body_top - 2), (x1 + int(w * 0.36), y1 + int(h * 0.08)),
                  (x1 + int(w * 0.49), y1 + int(h * 0.08)), (x1 + int(w * 0.49), body_top - 2)], fill=(170, 200, 225))
    draw.polygon([(x1 + int(w * 0.52), body_top - 2), (x1 + int(w * 0.52), y1 + int(h * 0.08)),
                  (x1 + int(w * 0.65), y1 + int(h * 0.08)), (x1 + int(w * 0.74), body_top - 2)], fill=(170, 200, 225))
    r = max(3, int(h * 0.18))
    for cx in (x1 + int(w * 0.22), x1 + int(w * 0.78)):
        cy = y1 + h - r
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(25, 25, 25))
        draw.ellipse([cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2], fill=(150, 150, 150))
    return x1, y1, x1 + w, y1 + h


def _scene(rng: random.Random) -> tuple[Image.Image, list[tuple[int, int, int, int]]]:
    img = Image.new("RGB", (WIDTH, HEIGHT), (150, 190, 230))
    draw = ImageDraw.Draw(img)
    horizon = 430
    for i in range(horizon):                                  # 하늘 그라데이션
        t = i / horizon
        draw.line([(0, i), (WIDTH, i)], fill=(int(120 + 60 * t), int(170 + 40 * t), int(225 + 20 * t)))
    x = 0
    while x < WIDTH:                                          # 건물
        bw, bh = rng.randint(60, 160), rng.randint(80, 260)
        g = rng.randint(110, 170)
        draw.rectangle([x, horizon - bh, x + bw, horizon], fill=(g, g, g + 5))
        x += bw + rng.randint(0, 20)
    draw.rectangle([0, horizon, WIDTH, horizon + 25], fill=(90, 130, 80))
    draw.rectangle([0, horizon + 25, WIDTH, HEIGHT], fill=(80, 80, 85))      # 도로
    for lane_y in (620, 760):
        for lx in range(0, WIDTH, 120):
            draw.rectangle([lx, lane_y, lx + 60, lane_y + 6], fill=(235, 225, 160))
    cars = []
    lanes = [(500, 0.55), (650, 0.8), (790, 1.0)]
    for base_y, scale in lanes:
        n = rng.randint(1, 3)
        slots = sorted(rng.sample(range(0, 6), n))
        for s in slots:
            w = int(rng.randint(200, 260) * scale)
            h = int(w * rng.uniform(0.40, 0.48))
            x1 = 40 + s * 260 + rng.randint(0, 30)
            if x1 + w > WIDTH - 10:
                continue
            cars.append(_draw_car(draw, x1, base_y - h, w, h, rng.choice(CAR_COLOURS)))
    return img, cars


def _yolo_line(box) -> str:
    x1, y1, x2, y2 = box
    return (f"0 {(x1 + x2) / 2 / WIDTH!r} {(y1 + y2) / 2 / HEIGHT!r} "
            f"{(x2 - x1) / WIDTH!r} {(y2 - y1) / HEIGHT!r}")


def _box_from_yolo(line: str) -> list[float]:
    """render_adjudication_images.read_labels와 같은 변환 — 기존 라벨 후보의 상자가 라벨과 정확히 겹치게."""
    cx, cy, bw, bh = (float(v) for v in line.split()[1:5])
    return [(cx - bw / 2) * WIDTH, (cy - bh / 2) * HEIGHT, (cx + bw / 2) * WIDTH, (cy + bh / 2) * HEIGHT]


def generate(out: Path, scenes: int = 10, seed: int = DEFAULT_SEED, candidates: int = MAX_CANDIDATES) -> dict:
    if not 1 <= scenes <= MAX_SCENES:
        raise ValueError(f"합성 원본은 1~{MAX_SCENES}장: {scenes}")
    if not 1 <= candidates <= MAX_CANDIDATES:
        raise ValueError(f"후보는 1~{MAX_CANDIDATES}건: {candidates}")
    out = Path(out)
    hits = nuimages_path_hits(out.resolve())
    if hits:
        raise ValueError(f"출력 경로가 nuImages 자료 위치로 보인다({hits}) — 합성 그림을 섞지 않는다: {out}")
    rendered = out / "rendered"
    if rendered.exists() and any(rendered.iterdir()):
        raise ValueError(f"이미 산출물이 있다 — 덮어쓰지 않는다: {rendered}")
    images_dir, labels_dir = out / "source" / "images", out / "source" / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    queue_rows = []
    for k in range(scenes):
        img, cars = _scene(rng)
        while len(cars) < 2:                                  # 후보 두 개(기존 라벨·누락)를 만들 만큼
            img, cars = _scene(rng)
        name = f"synth_{k:03d}.png"
        img.save(images_dir / name)
        missing_idx = rng.randrange(len(cars))                # 이 차에는 라벨을 달지 않는다(누락 후보)
        lines = []
        for i, car in enumerate(cars):
            if i == missing_idx:
                continue
            box = list(car)
            if rng.random() < 0.4:                            # 일부 라벨은 일부러 어긋나게(기존 라벨 오류 모양)
                dx = int((box[2] - box[0]) * rng.uniform(0.15, 0.35))
                box = [box[0] + dx, box[1], min(WIDTH, box[2] + dx), box[3]]
            lines.append(_yolo_line(box))
        (labels_dir / f"synth_{k:03d}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        label_index = rng.randrange(len(lines))
        queue_rows.append({"canonical_candidate_id": f"S{k:03d}L", "image": name, "label_index": label_index,
                           "box": _box_from_yolo(lines[label_index]), "class_name": CLASS_NAME,
                           "verdict": None, "unique_error_id": None})
        queue_rows.append({"canonical_candidate_id": f"S{k:03d}M", "image": name, "label_index": None,
                           "box": [float(v) for v in cars[missing_idx]], "class_name": CLASS_NAME,
                           "verdict": None, "unique_error_id": None})
    queue_rows = queue_rows[:candidates]
    ids = [r["canonical_candidate_id"] for r in queue_rows]
    queue = {"evaluation_id": "synthetic_dryrun", "dataset_id": "synthetic_dryrun",
             "provenance": SYNTHETIC_DRYRUN,
             "candidate_set_hash": hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest(),
             "candidates": queue_rows}
    (out / "queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")

    manifest = render_queue(queue, images_dir, labels_dir, rendered)
    files = {}
    for meta in manifest:
        for key in ("full_file", "file"):
            files[meta[key]] = sha256_file(rendered / meta[key])
    generator_path = Path(__file__).resolve()
    provenance = {
        "provenance": SYNTHETIC_DRYRUN,
        "generator": SYNTHETIC_GENERATOR,
        "generator_sha256": sha256_file(generator_path),
        "renderer": "experiment/render_adjudication_images.py",
        "renderer_sha256": sha256_file(generator_path.parent / "render_adjudication_images.py"),
        "seed": seed, "scenes": scenes, "candidates": len(manifest),
        "source_size_px": [WIDTH, HEIGHT], "format": "PNG (full scene + crop per candidate)",
        "purpose": PURPOSE,
        "not_evidence_for": ["accuracy", "difficulty", "model_performance", "agreement"],
        "contains_real_dataset_images": False,
        "files": files,
    }
    (rendered / PROVENANCE_FILE).write_text(json.dumps(provenance, ensure_ascii=False, indent=1), encoding="utf-8")
    return provenance


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI 비용 드라이런용 합성 그림(실제 데이터 없음)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scenes", type=int, default=10)
    ap.add_argument("--candidates", type=int, default=MAX_CANDIDATES)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    a = ap.parse_args(argv)
    prov = generate(Path(a.out), a.scenes, a.seed, a.candidates)
    print(f"합성 원본 {prov['scenes']}장, 후보 {prov['candidates']}건(그림 {len(prov['files'])}개) → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
