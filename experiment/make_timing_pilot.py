"""수동 시간 측정 파일럿의 무대를 만든다 (docs/manual-timing-pilot.md).

**판정하지 않는다.** 임시 데이터셋과 후보 목록을 만들고 **사람이 열 주소**를
찍어 줄 뿐이다.

## 왜 실제 이미지여야 하는가

처음 판은 1픽셀 회색 PNG를 늘려 쓰고 박스도 난수로 만들었다. 주석에는 "미리보기가
무엇을 그리는지는 이 파일럿의 관심이 아니다"라고 적었는데 **그게 틀렸다.**
판정 시간은 곧 **이미지를 보는 시간**이다. 볼 것이 없으면 전부 "모르겠다"가
되고, 그렇게 나온 시간은 판정 시간이 아니라 버튼 클릭 시간이다.

## 후보를 어떻게 만드는가 — **모델을 돌리지 않는다**

실제 라벨에 **오류를 주입해서** 만든다(`error_injector.py`, 조건 실험과 같은
도구).

| 후보 | 만드는 법 | 판정자가 봐야 할 것 |
|---|---|---|
| 틀린 기존 라벨 | 라벨 박스를 늘리거나 옮긴다 | 박스가 객체를 못 감싼다 |
| 멀쩡한 기존 라벨 | 원래 라벨 그대로 | 잘 감싸고 있다 |
| 누락 | 라벨을 **빼고** 그 자리를 가리킨다 | 객체가 있는데 라벨이 없다 |

**이건 AIDA의 예측이 아니다.** 자를 돌리지 않으므로 GPU도 필요 없고, 여기서
나오는 것은 **판정에 걸리는 시간**뿐이다. AIDA가 기준선보다 나은지와는 아무
관계가 없다.

멀쩡한 라벨을 섞는 이유는 **"오류 아니었다"가 실제로 나올 수 있어야** 하기
때문이다. 전부 진짜 오류면 판정이 아니라 확인 작업이 된다.
"""
import argparse
import json
import random
import shutil
import sys
from pathlib import Path

import config
from error_injector import (apply_scale, apply_translation_x, apply_width,
                            pixel_to_yolo_line, yolo_to_pixel)

# 임시 파일럿 전용 id 대역. **사용자가 올린 데이터셋과 겹치지 않는 자리다.**
DEFAULT_DATASET = "ffffffffff01"
# 파일럿 실행마다 남기는 메타. **판정 방식은 밖에서 적는다** — 기록만 보고
# 도움을 받았는지 알 수 없다(docs/manual-timing-pilot.md).
PILOT_META_FILE = "pilot_meta.json"
JUDGING_MODES = ("unaided_human", "assisted_rehearsal")

# 판정할 수 있을 만큼 큰 객체만 쓴다. 너무 작으면 "모르겠다"밖에 답이 없고,
# 그건 도구가 아니라 자료의 문제다.
MIN_BOX_PIXELS = 40.0

# 주입 세기. **눈으로 보이는 크기**여야 한다 — 5%를 틀리게 만들고 "찾아 보라"고
# 하면 그건 판정이 아니라 시력 검사다.
INJECTIONS = [
    ("width", apply_width, 40.0),
    ("scale", apply_scale, -35.0),
    ("translation_x", apply_translation_x, 30.0),
]


def _read_size(path: Path) -> tuple[int, int] | None:
    """PNG·JPEG 머리에서 크기만 읽는다.

    이미지 라이브러리를 새로 들이지 않으려는 것이다 — 이 스크립트가 필요한
    것은 픽셀 좌표 환산뿐이다.
    """
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                return (int.from_bytes(data[i + 7:i + 9], "big"),
                        int.from_bytes(data[i + 5:i + 7], "big"))
            i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    return None


def used_images(dataset_id: str) -> set[str]:
    """그 파일럿이 이미 쓴 이미지 이름들. 없으면 빈 집합.

    **정답을 본 이미지는 다시 쓰지 않는다.** 한 번 본 이미지는 두 번째에
    빨라지고, 그 시간은 판정 시간이 아니라 기억이다.
    """
    path = config.uploads_dir() / dataset_id / "label_diagnosis.json"
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {row.get("image") for row in data.get("review_queue", [])
            if row.get("image")}


def pick_images(images_dir: Path, labels_dir: Path, count: int, seed: int,
                exclude: set[str] | None = None,
                ) -> list[tuple[Path, Path, int, int]]:
    """라벨이 충분히 있는 이미지를 고른다. `exclude`에 있는 것은 건너뛴다."""
    rng = random.Random(seed)
    skip = exclude or set()
    pool = sorted(p for p in images_dir.iterdir()
                  if p.suffix.lower() in (".png", ".jpg", ".jpeg")
                  and p.name not in skip)
    rng.shuffle(pool)

    chosen = []
    for image in pool:
        label = labels_dir / f"{image.stem}.txt"
        if not label.is_file():
            continue
        lines = [l for l in label.read_text(encoding="utf-8").splitlines() if l.strip()]
        if len(lines) < 2:
            continue                       # 문맥이 있어야 판정할 수 있다
        size = _read_size(image)
        if size is None:
            continue
        chosen.append((image, label, size[0], size[1]))
        if len(chosen) >= count:
            break
    return chosen


def build(images_dir: Path, labels_dir: Path, out: Path, candidates: int,
          seed: int, class_names: list[str],
          exclude: set[str] | None = None,
          ) -> tuple[list[dict], list[dict]]:
    """후보 목록과 **정답 열쇠**를 만든다.

    정답 열쇠는 진단 결과와 **다른 파일**에 쓴다. 가림 판정 화면은 진단 결과만
    읽으므로 열쇠가 새지 않는다. **판정 전에 열지 않는다.**
    """
    rng = random.Random(seed)
    images = pick_images(images_dir, labels_dir, candidates, seed, exclude)
    if len(images) < candidates:
        raise SystemExit(
            f"쓸 만한 이미지가 모자랍니다: {len(images)}/{candidates}\n"
            f"{images_dir}를 확인하세요.")

    # **겹치면 만들지 않는다.** 제외 목록을 넘겼는데도 겹쳤다면 거르는 쪽이
    # 고장 난 것이고, 그대로 두면 기억으로 빨라진 시간을 판정 시간으로 센다.
    overlap = {i[0].name for i in images} & (exclude or set())
    if overlap:
        raise SystemExit(
            f"제외해야 할 이미지가 들어왔습니다: {sorted(overlap)[:5]}")

    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    (out / "classes.txt").write_text("\n".join(class_names) + "\n", encoding="utf-8")

    queue: list[dict] = []
    answers: list[dict] = []
    # 후보 유형을 고루 섞는다: 틀린 라벨 / 멀쩡한 라벨 / 누락.
    plan = (["wrong"] * (candidates // 2)
            + ["clean"] * (candidates - candidates // 2 - candidates // 5)
            + ["missing"] * (candidates // 5))
    rng.shuffle(plan)

    for rank, ((image, label, width, height), kind) in enumerate(
            zip(images, plan), start=1):
        lines = [l for l in label.read_text(encoding="utf-8").splitlines() if l.strip()]
        boxes = [yolo_to_pixel(l, width, height) for l in lines]
        classes = [int(float(l.split()[0])) for l in lines]
        # 판정할 수 있을 만큼 큰 것 중에서 고른다.
        big = [i for i, b in enumerate(boxes)
               if b[2] - b[0] >= MIN_BOX_PIXELS and b[3] - b[1] >= MIN_BOX_PIXELS]
        target = rng.choice(big) if big else rng.randrange(len(boxes))

        shutil.copy2(image, out / "images" / image.name)
        out_lines = list(lines)
        name = class_names[classes[target]] if classes[target] < len(class_names) else None

        if kind == "wrong":
            label_name, transform, magnitude = rng.choice(INJECTIONS)
            broken = transform(boxes[target], magnitude)
            out_lines[target] = pixel_to_yolo_line(broken, width, height,
                                                   classes[target])
            candidate_box, label_index, truth = broken, target, "error"
        elif kind == "clean":
            candidate_box, label_index, truth = boxes[target], target, "clean"
            label_name_unused = None            # 원래 라벨 그대로 둔다
        else:
            # 라벨을 빼고 그 자리를 가리킨다. **객체는 그대로 있다.**
            out_lines.pop(target)
            candidate_box, label_index, truth = boxes[target], None, "error"

        (out / "labels" / f"{image.stem}.txt").write_text(
            "\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")

        queue.append({
            "rank": rank,
            "image": image.name,
            "label_index": label_index,
            # **의심 유형은 화면에 안 간다**(가림). 기록에는 남는다.
            "suspicion": "missing" if label_index is None else "width",
            "severity": round(0.95 - rank * 0.01, 3),
            "detail": "",
            "box": [round(v, 1) for v in candidate_box],
            "class_name": name,
            **({} if label_index is None else {"label_iou": 0.5}),
        })
        answers.append({"rank": rank, "image": image.name, "kind": kind,
                        "truth": truth})

    return queue, answers


def main() -> int:
    parser = argparse.ArgumentParser(description="수동 파일럿 무대 만들기")
    parser.add_argument("--candidates", type=int, default=24,
                        help="후보 수 (권장 20~30)")
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET,
                        help="파일럿 데이터셋 id (12자리 16진수)")
    parser.add_argument("--evaluation-id", default="timing1")
    parser.add_argument("--exclude-from", action="append", default=[],
                        metavar="DATASET_ID",
                        help="그 파일럿이 쓴 이미지를 뺀다. 여러 번 줄 수 있다")
    parser.add_argument("--judging-mode", choices=JUDGING_MODES,
                        default="unaided_human",
                        help="도움 없이 할 것인가, 연습인가. 기록만 보고는 "
                             "알 수 없어 여기서 적는다")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--split", default="val", choices=("train", "val"),
                        help="개발 데이터의 어느 분할에서 뽑을지")
    parser.add_argument("--frontend", default="http://localhost:5173")
    parser.add_argument("--replace", action="store_true",
                        help="같은 임시 데이터셋이 있으면 지우고 다시 만든다")
    args = parser.parse_args()

    images_dir = config.PROCESSED_DIR / "images" / args.split
    labels_dir = config.PROCESSED_DIR / "labels_gt" / args.split
    if not images_dir.is_dir() or not labels_dir.is_dir():
        raise SystemExit(
            f"개발 데이터가 없습니다: {images_dir}\n"
            "이 스크립트는 이미 내려받아 둔 개발 데이터만 씁니다 — "
            "새로 내려받지 않습니다.")

    if not __import__("re").fullmatch(r"[0-9a-f]{12}", args.dataset_id):
        raise SystemExit(f"데이터셋 id 형식이 아닙니다: {args.dataset_id}")

    # **이미 쓴 이미지를 뺀다.** 정답을 본 이미지는 두 번째에 빨라지고,
    # 그 시간은 판정 시간이 아니라 기억이다.
    exclude: set[str] = set()
    for other in args.exclude_from:
        exclude |= used_images(other)

    root = config.uploads_dir() / args.dataset_id
    if root.exists():
        if not args.replace:
            print(f"이미 있습니다: {root}\n"
                  "다시 만들려면 --replace 를 붙이세요. "
                  "(이 자리는 파일럿 전용이라 사용자 데이터셋이 아닙니다)")
            return 1
        shutil.rmtree(root)

    queue, answers = build(images_dir, labels_dir, root, args.candidates,
                           args.seed, config.CLASS_NAMES, exclude)

    (root / "label_diagnosis.json").write_text(json.dumps({
        "dataset_id": args.dataset_id,
        "generated_at": "2026-09-09T00:00:00+00:00",
        "summary": {},
        "caveat": ("수동 시간 측정 파일럿용입니다. 후보는 개발 데이터의 실제 "
                   "라벨에 오류를 주입해 만든 것이고 AIDA의 예측이 아닙니다. "
                   "효능 근거로 쓰지 마세요."),
        "review_queue": queue,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # **정답 열쇠는 진단 결과와 다른 파일에 둔다.** 가림 판정 화면은 진단
    # 결과만 읽는다. 판정 전에 열지 않는다.
    (root / "pilot_answer_key.json").write_text(json.dumps({
        "warning": "판정 전에 열지 마세요. 보고 나면 그 판정은 가림이 아닙니다.",
        "source_split": args.split,
        "answers": answers,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # **판정 방식을 파일에 적는다.** 나중에 보고서가 이걸 보고 계획값을
    # 낼지 정한다 — 속도나 보류 비율로는 도움 여부를 알 수 없다.
    (root / PILOT_META_FILE).write_text(json.dumps({
        "dataset_id": args.dataset_id,
        "evaluation_id": args.evaluation_id,
        "seed": args.seed,
        "split": args.split,
        "judging_mode": args.judging_mode,
        "excluded_from": args.exclude_from,
        "excluded_images": sorted(exclude),
        "images": sorted({row["image"] for row in queue}),
        "note": ("judging_mode는 사람이 적는 값이다. 도움을 받았는지는 "
                 "기록만 보고 알 수 없다 — 다른 도구에서 들여다본 시간은 "
                 "판정 탭의 활동 시간에 안 들어간다."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    kinds = {k: sum(1 for a in answers if a["kind"] == k)
             for k in ("wrong", "clean", "missing")}
    print(f"임시 데이터셋을 만들었습니다: {root}")
    print(f"  개발 데이터 {args.split} 분할의 실제 이미지 {len(queue)}장")
    print(f"  틀린 라벨 {kinds['wrong']} / 멀쩡한 라벨 {kinds['clean']} "
          f"/ 누락 {kinds['missing']}")
    print(f"  클래스: {', '.join(config.CLASS_NAMES)}")
    print(f"  판정 방식: {args.judging_mode}")
    if exclude:
        print(f"  제외한 이미지 {len(exclude)}장 "
              f"({', '.join(args.exclude_from)}에서 쓴 것)")
    print()
    print("다음 두 단계는 사람이 합니다.")
    print()
    print("1) 평가 묶음을 만든다 (서버가 떠 있어야 합니다):")
    print(f'   curl -s -X POST http://localhost:8000/api/datasets/{args.dataset_id}'
          f'/evaluations -H "Content-Type: application/json" '
          f'-d \'{{"evaluation_id":"{args.evaluation_id}","shuffle_seed":{args.seed}}}\'')
    print()
    print("2) 브라우저에서 열고 **평소 속도로** 판정한다:")
    print(f"   {args.frontend}/?evaluate={args.dataset_id}:{args.evaluation_id}")
    print()
    print("   판정 기준은 docs/manual-timing-pilot.md에 있습니다.")
    print("   최소 두 세션으로 나누세요 — 중간에 창을 닫았다가 다시 엽니다.")
    print()
    print("끝나면:")
    print(f"   python experiment/timing_report.py --dataset {args.dataset_id} "
          f"--evaluation {args.evaluation_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
