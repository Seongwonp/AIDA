"""보조(AI) 판정자 입력 이미지 — 가림 판정 목록(`GET .../queue?adjudicator=<id>`)을 그림으로.

사람 화면과 같은 규칙으로 그린다(docs/manual-timing-pilot.md): 판정할 기존 라벨은 **빨강 실선**, 누락
지목 자리는 **빨강 점선**, 그 이미지의 다른 라벨은 **파랑**. 점수·순위·방법·출처·다른 판정자의 판정은
목록에 없으므로 그림에도 없다. 좌표는 그림 아래에 글로 병기한다(문헌: 좌표만 주는 것보다 그림이 낫다).

사용법:
  python render_adjudication_images.py --queue queue.json --images <데이터셋>/images --labels <데이터셋>/labels \
      --out practice_ai/ [--margin 0.5]
출력: 후보마다 `<후보 id>.png`와 `manifest.json`(후보 id·이미지·상자·클래스 이름·좌표 문구). 판정은 하지 않는다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

RED, BLUE = (220, 30, 30), (30, 90, 220)


def read_labels(path: Path, w: int, h: int) -> list[tuple[float, float, float, float]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cx, cy, bw, bh = (float(v) for v in parts[1:5])
        out.append(((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h))
    return out


def dashed_rect(draw: ImageDraw.ImageDraw, box, colour, width=3, dash=8):
    x1, y1, x2, y2 = box
    for (ax, ay, bx, by) in ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)):
        length = max(abs(bx - ax), abs(by - ay))
        steps = max(1, int(length // dash))
        for i in range(0, steps, 2):
            t0, t1 = i / steps, min(1.0, (i + 1) / steps)
            draw.line([(ax + (bx - ax) * t0, ay + (by - ay) * t0),
                       (ax + (bx - ax) * t1, ay + (by - ay) * t1)], fill=colour, width=width)


def render_one(image_path: Path, label_path: Path, candidate: dict, margin: float) -> tuple[Image.Image, dict]:
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    box = candidate["box"]
    is_label = candidate.get("label_index") is not None
    draw = ImageDraw.Draw(img)
    for other in read_labels(label_path, w, h):
        if is_label and all(abs(a - b) < 0.6 for a, b in zip(other, box)):
            continue
        draw.rectangle(other, outline=BLUE, width=2)
    if is_label:
        draw.rectangle(box, outline=RED, width=3)
    else:
        dashed_rect(draw, box, RED)
    bw, bh = box[2] - box[0], box[3] - box[1]
    pad_w, pad_h = max(40, bw * margin), max(40, bh * margin)
    crop = (max(0, int(box[0] - pad_w)), max(0, int(box[1] - pad_h)),
            min(w, int(box[2] + pad_w)), min(h, int(box[3] + pad_h)))
    view = img.crop(crop)
    meta = {"canonical_candidate_id": candidate["canonical_candidate_id"], "image": candidate["image"],
            "task": "labelled" if is_label else "missing", "class_name": candidate.get("class_name"),
            "box_xyxy_px": [round(v, 1) for v in box], "image_size": [w, h], "crop_xyxy_px": list(crop),
            "caption": (f"{'기존 라벨(빨강 실선)' if is_label else '누락 지목 자리(빨강 점선)'} "
                        f"x1={box[0]:.0f} y1={box[1]:.0f} x2={box[2]:.0f} y2={box[3]:.0f} "
                        f"(원본 {w}×{h}px, 파랑=이 이미지의 다른 라벨)")}
    return view, meta


def render_queue(queue: dict, images: Path, labels: Path, out: Path, margin: float = 0.5) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for c in queue["candidates"]:
        if not c.get("box"):
            continue
        view, meta = render_one(images / c["image"], labels / (Path(c["image"]).stem + ".txt"), c, margin)
        path = out / f"{c['canonical_candidate_id']}.png"
        view.save(path)
        meta["file"] = path.name
        manifest.append(meta)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--margin", type=float, default=0.5)
    a = ap.parse_args()
    queue = json.loads(Path(a.queue).read_text(encoding="utf-8"))
    for c in queue["candidates"]:
        for forbidden in ("scores", "aida_rank", "source", "random_sample", "suspicion"):
            if forbidden in c:
                raise SystemExit(f"목록에 가려야 할 값이 있다: {forbidden} — 가림 목록(queue)만 받는다")
    manifest = render_queue(queue, Path(a.images), Path(a.labels), Path(a.out), a.margin)
    print(f"{len(manifest)}장 → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
