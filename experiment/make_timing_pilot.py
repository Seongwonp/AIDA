"""수동 시간 측정 파일럿의 무대를 만든다 (docs/manual-timing-pilot.md).

**판정하지 않는다.** 임시 데이터셋과 평가 묶음을 만들고 **사람이 열 주소**를
찍어 줄 뿐이다. 자동 클릭으로 잰 시간은 사람의 검수 시간이 아니다.

기존 데이터셋은 건드리지 않는다 — 고정된 임시 id 하나만 쓰고, 이미 있으면
멈춘다.
"""
import argparse
import base64
import json
import random
import shutil
import sys
from pathlib import Path

import config

# 임시 파일럿 전용 id. **사용자가 올린 데이터셋과 겹치지 않는 자리다.**
PILOT_DATASET = "ffffffffff01"

# 1픽셀 회색 PNG. 미리보기가 무엇을 그리는지는 이 파일럿의 관심이 아니다 —
# 재려는 것은 "판단하고 누르는 데 걸리는 시간"이다.
BLANK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAIAAAD/gAIDAAAAJ0lEQVR4nO3BAQ0AAADCoPdPbQ8H"
    "FAAAAAAAAAAAAAAAAAAAAADAmwFkAAAB9O8ZAAAAAABJRU5ErkJggg==")

SUSPICIONS = ["width", "height", "scale", "translation_x", "class_mismatch"]


def build_queue(count: int, seed: int) -> list[dict]:
    """후보 목록. **난이도가 섞이게 만든다.**

    다 똑같이 쉬우면 후보당 시간의 분산이 없어져, 평균의 구간이 실제보다
    좁게 나온다.
    """
    rng = random.Random(seed)
    queue = []
    for i in range(count):
        image = f"img{i % 6}.jpg"
        missing = i % 5 == 4
        x = 10 + (i * 13) % 120
        size = 30 + (i * 7) % 60
        row = {
            "rank": i + 1,
            "image": image,
            "label_index": None if missing else i % 4,
            "suspicion": "missing" if missing else SUSPICIONS[i % len(SUSPICIONS)],
            "severity": round(0.95 - i * 0.02, 3),
            "detail": "",
            "box": [x, x, x + size, x + size],
        }
        if not missing:
            row["label_iou"] = round(rng.uniform(0.05, 0.95), 3)
        queue.append(row)
    return queue


def main() -> int:
    parser = argparse.ArgumentParser(description="수동 파일럿 무대 만들기")
    parser.add_argument("--candidates", type=int, default=24,
                        help="후보 수 (권장 20~30)")
    parser.add_argument("--evaluation-id", default="timing1")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--frontend", default="http://localhost:5173")
    parser.add_argument("--replace", action="store_true",
                        help="같은 임시 데이터셋이 있으면 지우고 다시 만든다")
    args = parser.parse_args()

    root = config.uploads_dir() / PILOT_DATASET
    if root.exists():
        if not args.replace:
            print(f"이미 있습니다: {root}\n"
                  "다시 만들려면 --replace 를 붙이세요. "
                  "(이 자리는 파일럿 전용이라 사용자 데이터셋이 아닙니다)")
            return 1
        shutil.rmtree(root)

    images = root / "images"
    images.mkdir(parents=True)
    queue = build_queue(args.candidates, args.seed)
    for name in {row["image"] for row in queue}:
        (images / name).write_bytes(BLANK_PNG)

    (root / "label_diagnosis.json").write_text(json.dumps({
        "dataset_id": PILOT_DATASET,
        "generated_at": "2026-09-09T00:00:00+00:00",
        "summary": {},
        "caveat": "수동 시간 측정 파일럿용 임시 데이터입니다. 효능 근거가 아닙니다.",
        "review_queue": queue,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    missing = sum(1 for row in queue if row["label_index"] is None)
    print(f"임시 데이터셋을 만들었습니다: {root}")
    print(f"  후보 {len(queue)}개 (누락 {missing}개, 기존 라벨 {len(queue) - missing}개)")
    print()
    print("다음 두 단계는 사람이 합니다.")
    print()
    print("1) 평가 묶음을 만든다 (서버가 떠 있어야 합니다):")
    print(f'   curl -s -X POST http://localhost:8000/api/datasets/{PILOT_DATASET}'
          f'/evaluations -H "Content-Type: application/json" '
          f'-d \'{{"evaluation_id":"{args.evaluation_id}","shuffle_seed":{args.seed}}}\'')
    print()
    print("2) 브라우저에서 열고 **평소 속도로** 판정한다:")
    print(f"   {args.frontend}/?evaluate={PILOT_DATASET}:{args.evaluation_id}")
    print()
    print("   최소 두 세션으로 나누세요 — 중간에 창을 닫았다가 다시 엽니다.")
    print("   재표집 단위가 세션이라 세션이 하나면 구간을 만들 수 없습니다.")
    print()
    print("끝나면:")
    print(f"   python experiment/timing_report.py --dataset {PILOT_DATASET} "
          f"--evaluation {args.evaluation_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
