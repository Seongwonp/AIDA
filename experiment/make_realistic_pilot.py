"""실제 진단 후보로 시간 파일럿 무대를 만든다 (docs/timing4-realistic-protocol.md).

`make_timing_pilot.py`는 실제 라벨에 **오류를 주입해** 후보를 만든다. 그 후보는
크고 종류도 셋뿐이라 실제보다 빨리 판단되고, 거기서 나온 시간은 **하한**이다.

여기서는 **자를 실제로 돌려** 나온 후보를 쓴다. 난이도가 실제와 같다.

**학습하지 않는다.** 이미 있는 가중치로 추론만 하고, 최종 평가 데이터와 사용자
데이터셋은 건드리지 않는다.

품질 가드레일로 **정답이 알려진 anchor**를 섞는다 — 실제 후보에는 정답이 없어
"빨라진 것이 숙련인지 무성의인지"를 가릴 수 없기 때문이다. anchor 정확도는
AIDA의 효능이 아니다.
"""
import argparse
import hashlib
import json
import random
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
from error_injector import apply_scale, apply_width, pixel_to_yolo_line, yolo_to_pixel
from label_diagnosis import diagnose_image
from diagnose_labels import PREDICT_CONFIDENCE_FLOOR
from make_timing_pilot import (JUDGING_MODES, MIN_BOX_PIXELS, PILOT_META_FILE,
                               _read_size, used_images)

# anchor 주입 세기. **눈에 띄게** 만든다 — 가드레일은 "명백한 것을 놓치는가"를
# 보는 것이지 시력 검사가 아니다.
ANCHOR_INJECTIONS = [("width", apply_width, 45.0), ("scale", apply_scale, -40.0)]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace",
                             cwd=str(config.EXPERIMENT_ROOT), timeout=20)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def predict(weights: Path, images: list[Path], conf: float):
    """자를 돌려 이미지마다 (박스, 확신도, 클래스)를 얻는다.

    **여기서만 GPU를 쓴다.** 학습하지 않고 추론만 한다.
    """
    from ultralytics import YOLO

    model = YOLO(str(weights))
    out = []
    for image in images:
        result = model.predict(str(image), conf=conf, verbose=False,
                               device=config.resolve_device())[0]
        boxes = [tuple(float(v) for v in b) for b in result.boxes.xyxy.tolist()]
        scores = [float(v) for v in result.boxes.conf.tolist()]
        classes = [int(v) for v in result.boxes.cls.tolist()]
        out.append((boxes, scores, classes))
    return out


def real_candidates(images: list[Path], labels_dir: Path, weights: Path,
                    conf: float) -> list[dict]:
    """자가 실제로 낸 후보들. **주입하지 않는다.**"""
    predictions = predict(weights, images, conf)
    rows = []
    for image, (boxes, scores, classes) in zip(images, predictions):
        size = _read_size(image)
        if size is None:
            continue
        width, height = size
        lines = [l for l in (labels_dir / f"{image.stem}.txt")
                 .read_text(encoding="utf-8").splitlines() if l.strip()]
        label_boxes = [yolo_to_pixel(l, width, height) for l in lines]
        label_classes = [int(float(l.split()[0])) for l in lines]

        for finding in diagnose_image(image.name, boxes, scores, label_boxes,
                                      pred_classes=classes,
                                      label_classes=label_classes):
            rows.append({
                "image": image.name,
                "label_index": finding.label_index,
                "suspicion": finding.suspicion,
                "severity": finding.severity,
                "detail": finding.detail,
                "box": [round(v, 1) for v in finding.box],
                "label_iou": finding.label_iou,
                "class_name": (config.CLASS_NAMES[finding.class_id]
                               if finding.class_id is not None
                               and finding.class_id < len(config.CLASS_NAMES)
                               else None),
                "origin": "actual_diagnosis",
            })
    return rows


def anchor_candidates(images: list[Path], labels_dir: Path, out: Path,
                      count: int, rng: random.Random) -> tuple[list[dict], list[dict]]:
    """정답이 알려진 후보. 절반은 멀쩡하고 절반은 명백히 틀리다.

    **품질 가드레일이지 정확도 증거가 아니다.**
    """
    rows, answers = [], []
    # **채울 때까지 뽑는다.** 큰 박스가 없는 이미지를 건너뛰면서 그냥 줄어들면
    # 사전 등록한 anchor 수를 못 채운다.
    for i, image in enumerate(images):
        if len(rows) >= count:
            break
        size = _read_size(image)
        if size is None:
            continue
        width, height = size
        label_path = labels_dir / f"{image.stem}.txt"
        lines = [l for l in label_path.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        boxes = [yolo_to_pixel(l, width, height) for l in lines]
        classes = [int(float(l.split()[0])) for l in lines]
        big = [j for j, b in enumerate(boxes)
               if b[2] - b[0] >= MIN_BOX_PIXELS and b[3] - b[1] >= MIN_BOX_PIXELS]
        if not big:
            continue
        target = rng.choice(big)

        out_lines = list(lines)
        if len(rows) % 2 == 0:               # 멀쩡한 anchor
            box, truth = boxes[target], "clean"
        else:                                # 명백히 틀린 anchor
            _, transform, magnitude = rng.choice(ANCHOR_INJECTIONS)
            box = transform(boxes[target], magnitude)
            out_lines[target] = pixel_to_yolo_line(box, width, height,
                                                   classes[target])
            truth = "error"

        (out / "labels" / f"{image.stem}.txt").write_text(
            "\n".join(out_lines) + "\n", encoding="utf-8")
        shutil.copy2(image, out / "images" / image.name)

        rows.append({
            "image": image.name, "label_index": target, "suspicion": "width",
            "severity": 0.5, "detail": "", "box": [round(v, 1) for v in box],
            "label_iou": 0.5,
            "class_name": (config.CLASS_NAMES[classes[target]]
                           if classes[target] < len(config.CLASS_NAMES) else None),
            "origin": "anchor",
        })
        answers.append({"image": image.name, "kind": truth,
                        "truth": truth, "origin": "anchor"})
    return rows, answers


def composition(rows: list[dict]) -> dict:
    """후보 구성. **표집 전후를 둘 다 적는다** — 표집이 구성을 바꿨는지 보려고."""
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row["suspicion"]] = kinds.get(row["suspicion"], 0) + 1
    return {
        "total": len(rows),
        "labelled": sum(1 for r in rows if r["label_index"] is not None),
        "missing": sum(1 for r in rows if r["label_index"] is None),
        "by_suspicion": dict(sorted(kinds.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="실제 진단 후보로 파일럿 만들기")
    parser.add_argument("--dataset-id", default="ffffffffff06")
    parser.add_argument("--evaluation-id", default="timing4")
    parser.add_argument("--real", type=int, default=40, help="실제 후보 수")
    parser.add_argument("--anchors", type=int, default=8, help="anchor 수")
    parser.add_argument("--pool", type=int, default=120,
                        help="진단을 돌릴 이미지 수 (여기서 후보를 표집한다)")
    parser.add_argument("--seed", type=int, default=4107)
    parser.add_argument("--split", default="val", choices=("train", "val"))
    parser.add_argument("--labels", default="labels_gt_nested",
                        help="어느 정답 라벨 세트를 쓸지. 기본은 "
                             "800장짜리 nested (labels_gt는 120장뿐이라 "
                             "timing1~3 제외 후 모자란다)")
    parser.add_argument("--conf", type=float, default=PREDICT_CONFIDENCE_FLOOR)
    parser.add_argument("--weights", default=str(config.EXPERIMENT_ROOT
                                                 / "runs" / "clean" / "weights"
                                                 / "best.pt"))
    parser.add_argument("--exclude-from", action="append", default=[])
    parser.add_argument("--judging-mode", choices=JUDGING_MODES,
                        default="unaided_human")
    parser.add_argument("--frontend", default="http://localhost:5173")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    weights = Path(args.weights)
    if not weights.is_file():
        raise SystemExit(f"가중치가 없습니다: {weights}")

    images_dir = config.PROCESSED_DIR / "images" / args.split
    labels_dir = config.PROCESSED_DIR / args.labels / args.split
    if not images_dir.is_dir() or not labels_dir.is_dir():
        raise SystemExit(f"개발 데이터가 없습니다: {images_dir} / {labels_dir}")

    # **자가 본 적 없는 이미지만 쓴다.** 학습에 쓴 프레임은 모델이 유난히 잘
    # 맞혀 후보가 적게·다르게 나온다 — 그걸로 잰 시간은 실제와 다르다.
    #
    # 두 가지를 뺀다: 자의 학습 라벨(`labels_gt/train`)에 있는 stem과,
    # `images/train`에도 사본이 있는 것. **논리적 분할과 파일이 놓인 자리가
    # 달라서** 둘 다 봐야 한다(docs/25 2단계에서 겪은 것과 같은 함정).
    seen = {p.stem for p in (config.PROCESSED_DIR / "labels_gt" / "train").iterdir()}
    seen |= {p.stem for p in (config.PROCESSED_DIR / "images" / "train").iterdir()}

    root = config.uploads_dir() / args.dataset_id
    if root.exists():
        if not args.replace:
            print(f"이미 있습니다: {root}\n다시 만들려면 --replace 를 붙이세요.")
            return 1
        shutil.rmtree(root)

    exclude: set[str] = set()
    for other in args.exclude_from:
        exclude |= used_images(other)

    rng = random.Random(args.seed)
    pool = sorted(p for p in images_dir.iterdir()
                  if p.suffix.lower() in (".png", ".jpg", ".jpeg")
                  and p.name not in exclude
                  and p.stem not in seen
                  and (labels_dir / f"{p.stem}.txt").is_file())
    if not pool:
        raise SystemExit("쓸 이미지가 없습니다. 제외 조건을 확인하세요.")
    rng.shuffle(pool)
    diagnosed = pool[:args.pool]
    anchor_pool = pool[args.pool:args.pool + args.anchors * 3]

    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    (root / "classes.txt").write_text("\n".join(config.CLASS_NAMES) + "\n",
                                      encoding="utf-8")

    print(f"자를 돌립니다: 이미지 {len(diagnosed)}장 (추론만, 학습 없음)")
    everything = real_candidates(diagnosed, labels_dir, weights, args.conf)
    before = composition(everything)
    print(f"  실제 후보 {before['total']}건 "
          f"(기존 라벨 {before['labelled']} / 누락 {before['missing']})")
    if before["total"] < args.real:
        raise SystemExit(f"실제 후보가 모자랍니다: {before['total']}/{args.real}. "
                         "--pool 을 늘리세요.")

    # **구성 비율을 보존한다.** 유형별로 고르게 뽑으면 그건 이미 실제 큐가 아니다.
    picked = rng.sample(everything, args.real)
    after = composition(picked)

    # 실제 후보가 쓰는 이미지는 라벨을 **원본 그대로** 둔다.
    for row in picked:
        name = row["image"]
        source = images_dir / name
        shutil.copy2(source, root / "images" / name)
        shutil.copy2(labels_dir / f"{Path(name).stem}.txt",
                     root / "labels" / f"{Path(name).stem}.txt")

    anchors, answers = anchor_candidates(anchor_pool, labels_dir, root,
                                         args.anchors, rng)
    queue = picked + anchors
    rng.shuffle(queue)                       # anchor가 어디 있는지 모르게
    for rank, row in enumerate(queue, start=1):
        row["rank"] = rank

    (root / "label_diagnosis.json").write_text(json.dumps({
        "dataset_id": args.dataset_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {},
        "caveat": ("실제 진단 후보 + 품질 가드레일 anchor입니다. anchor 정확도는 "
                   "AIDA의 효능이 아닙니다."),
        # **origin은 화면에 안 간다** — 가림 목록은 이 항목을 싣지 않는다.
        "review_queue": queue,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (root / "pilot_answer_key.json").write_text(json.dumps({
        "warning": "판정 전에 열지 마세요.",
        "note": ("anchor에만 정답이 있습니다. 실제 후보에는 정답이 없어 "
                 "정확도를 계산하지 않습니다."),
        "answers": answers,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (root / PILOT_META_FILE).write_text(json.dumps({
        "dataset_id": args.dataset_id, "evaluation_id": args.evaluation_id,
        "seed": args.seed, "split": args.split,
        "judging_mode": args.judging_mode,
        "candidate_source": "actual_diagnosis",
        "real_candidates": args.real, "anchors": len(anchors),
        "excluded_from": args.exclude_from,
        "note": ("실제 후보에는 정답이 없다. anchor는 과속·무성의 판정을 잡는 "
                 "가드레일이고 AIDA의 효능 증거가 아니다."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (root / "pilot_manifest.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_commit": code_commit(),
        "weights": {"path": str(weights.relative_to(config.EXPERIMENT_ROOT)),
                    "sha256": sha256(weights)},
        "settings": {"conf": args.conf, "seed": args.seed, "split": args.split,
                     "labels": args.labels, "pool": args.pool,
                     "classes": config.CLASS_NAMES},
        "excluded_seen_by_ruler": sorted(seen)[:0] or "labels_gt/train + images/train",
        "usable_pool": len(pool),
        "diagnosed_images": sorted(p.name for p in diagnosed),
        "composition_before_sampling": before,
        "composition_after_sampling": after,
        "anchor_images": sorted(r["image"] for r in anchors),
        "excluded_from": args.exclude_from,
        "note": "학습하지 않았다. 기존 가중치로 추론만 했다.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  표집 {after['total']}건 "
          f"(기존 라벨 {after['labelled']} / 누락 {after['missing']}) "
          f"+ anchor {len(anchors)}건 = 전체 {len(queue)}건")
    print(f"  유형 구성: 표집 전 {before['by_suspicion']}")
    print(f"             표집 후 {after['by_suspicion']}")
    print()
    print(f"만들었습니다: {root}")
    print(f"  {args.frontend}/?evaluate={args.dataset_id}:{args.evaluation_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
