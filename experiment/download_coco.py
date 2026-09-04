"""COCO val2017에서 자동차가 있는 프레임만 내려받는다 (docs/21 다음 할 일 5번).

Y~AH의 자 비교는 **전부 KITTI 안에서** 만든 자들끼리였다. "도메인이
어긋나면"이라고 말할 때의 어긋남이 같은 데이터셋 안에서의 프레임 선택
차이였다는 뜻이다. 진짜 다른 데이터에서도 성립하는지는 안 봤다.

COCO를 고른 이유:
  - 등록 없이 직접 받힌다. BDD100K·Cityscapes·nuScenes는 전부 계정이 필요하다.
  - Range 요청을 지원해서 필요한 이미지만 받을 수 있다(KITTI와 같은 방식).
  - `car` 클래스가 KITTI `Car`와 의미가 정확히 겹친다.

**Car 한 클래스만 쓴다.** COCO `bicycle`은 자전거 자체를 가리키고 KITTI
`Cyclist`는 자전거 탄 사람을 가리켜서 의미가 다르다. 매핑이 애매한 클래스를
넣으면 "도메인이 달라서 무너진 것"과 "라벨 정의가 달라서 무너진 것"을
구분할 수 없게 된다.

사용법:
  python download_coco.py --annotations-only     # 분포만 보고 멈춘다
  python download_coco.py --n-total 520
"""
import argparse
import io
import json
import random
import sys
import zipfile
from collections import Counter
from pathlib import Path

from tqdm import tqdm

import config
from download_kitti import HTTPRangeFile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ANNOTATIONS_URL = "http://images.cocodataset.org/annotations/annotations_trainval2017.zip"
IMAGES_URL = "http://images.cocodataset.org/zips/val2017.zip"
ANNOTATION_MEMBER = "annotations/instances_val2017.json"
IMAGE_MEMBER_PREFIX = "val2017/"

COCO_DIR = config.RAW_DIR / "coco"
CAR_CATEGORY = "car"
# 이보다 작은 상자는 버린다. KITTI 라벨에는 이 크기가 거의 없어서
# 오류 주입의 의미가 달라진다(30% 줄이면 몇 픽셀이 된다).
MIN_BOX_PX = 4


def download_annotations() -> Path:
    """주석 zip에서 val2017 것만 뽑는다. 전체 253MB 중 필요한 건 일부다."""
    COCO_DIR.mkdir(parents=True, exist_ok=True)
    out = COCO_DIR / "instances_val2017.json"
    if out.exists():
        print(f"주석 이미 존재: {out} (스킵)")
        return out

    print("주석 zip에 Range 요청으로 접속 중...")
    with zipfile.ZipFile(HTTPRangeFile(ANNOTATIONS_URL)) as zf:
        data = zf.read(ANNOTATION_MEMBER)
    out.write_bytes(data)
    print(f"주석 저장 → {out} ({len(data)/1e6:.1f}MB)")
    return out


def car_counts(ann_path: Path) -> tuple[dict[int, int], dict[int, dict]]:
    """이미지별 자동차 개수와 이미지 메타."""
    data = json.loads(ann_path.read_text(encoding="utf-8"))
    car_id = next(c["id"] for c in data["categories"] if c["name"] == CAR_CATEGORY)
    counts: Counter = Counter()
    boxes: dict[int, list] = {}
    for a in data["annotations"]:
        if a["category_id"] != car_id or a.get("iscrowd"):
            continue
        # COCO bbox는 [x, y, w, h] (좌상단 기준). 아주 작은 상자는 버린다 —
        # KITTI 라벨에는 없는 크기라 오류 주입의 의미가 달라진다.
        if a["bbox"][2] < MIN_BOX_PX or a["bbox"][3] < MIN_BOX_PX:
            continue
        counts[a["image_id"]] += 1
        boxes.setdefault(a["image_id"], []).append(a["bbox"])
    images = {i["id"]: i for i in data["images"]}
    return counts, {"boxes": boxes, "images": images}


def report(counts: dict[int, int]) -> None:
    total = sum(counts.values())
    print(f"\n자동차가 있는 이미지 {len(counts)}장, 자동차 상자 {total}개 "
          f"(장당 평균 {total/max(len(counts),1):.1f}개)")
    print(f"  {'장당 개수':>10}{'이미지 수':>10}")
    buckets = Counter()
    for n in counts.values():
        buckets["1" if n == 1 else "2" if n == 2 else "3-4" if n <= 4
                else "5-9" if n <= 9 else "10+"] += 1
    for key in ("1", "2", "3-4", "5-9", "10+"):
        print(f"  {key:>10}{buckets[key]:>10}")
    # KITTI 400장에 Car가 1851개였다 — 장당 4.6개. 비교 가능한 밀도를 고르려면
    # 이 분포를 보고 최소 개수를 정해야 한다.
    print("  (참고: KITTI 400장은 Car 1851개, 장당 4.6개)")


def main() -> None:
    ap = argparse.ArgumentParser(description="COCO val2017 자동차 프레임 다운로드")
    ap.add_argument("--annotations-only", action="store_true",
                    help="분포만 보고 멈춘다")
    ap.add_argument("--n-total", type=int, default=520,
                    help="내려받을 이미지 수 (기본 520 = KITTI와 같은 400+120)")
    # val2017에 자동차가 있는 이미지가 535장뿐이라 밀도까지 맞춰 고를 여유가
    # 없다. 자동차 4개 이상은 197장이라 520장을 못 채운다. 그래서 KITTI와 같은
    # 규칙("자동차가 있는 프레임 중 무작위")을 그대로 쓰고, 밀도 차이(장당 3.6
    # vs KITTI 4.6)는 도메인 차이의 일부로 기록한다.
    ap.add_argument("--min-cars", type=int, default=1,
                    help="이 개수 이상 자동차가 있는 이미지만 고른다")
    ap.add_argument("--seed", type=int, default=config.SEED)
    args = ap.parse_args()

    ann = download_annotations()
    counts, extra = car_counts(ann)
    report(counts)
    if args.annotations_only:
        return

    pool = sorted(i for i, n in counts.items() if n >= args.min_cars)
    print(f"\n자동차 {args.min_cars}개 이상인 이미지: {len(pool)}장")
    if len(pool) < args.n_total:
        raise SystemExit(f"{len(pool)}장뿐이라 요청한 {args.n_total}장을 못 채운다. "
                         f"--min-cars를 낮출 것.")
    chosen = sorted(random.Random(args.seed).sample(pool, args.n_total))
    picked = sum(counts[i] for i in chosen)
    print(f"{len(chosen)}장 선택, 자동차 {picked}개 (장당 {picked/len(chosen):.1f}개)")

    images_dir = COCO_DIR / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    meta = extra["images"]
    missing = [i for i in chosen if not (images_dir / meta[i]["file_name"]).exists()]
    if missing:
        print(f"이미지 {len(missing)}장 부분 다운로드 중...")
        with zipfile.ZipFile(HTTPRangeFile(IMAGES_URL)) as zf:
            for image_id in tqdm(missing, desc="COCO 이미지"):
                name = meta[image_id]["file_name"]
                (images_dir / name).write_bytes(zf.read(IMAGE_MEMBER_PREFIX + name))
    else:
        print("이미지 이미 전부 존재 (스킵)")

    # 선택 결과를 남긴다 — 라벨 변환이 이걸 읽는다
    sel = COCO_DIR / "selected.json"
    sel.write_text(json.dumps({
        "image_ids": chosen,
        "min_cars": args.min_cars,
        "seed": args.seed,
        "files": {str(i): meta[i]["file_name"] for i in chosen},
        "sizes": {str(i): [meta[i]["width"], meta[i]["height"]] for i in chosen},
        "boxes": {str(i): extra["boxes"][i] for i in chosen},
    }, ensure_ascii=False), encoding="utf-8")
    print(f"선택 결과 저장 → {sel}")


if __name__ == "__main__":
    main()
