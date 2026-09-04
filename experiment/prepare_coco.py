"""COCO 선택분을 KITTI와 같은 형식의 학습/평가 세트로 바꾼다.

download_coco.py가 남긴 selected.json(이미지 목록 + 자동차 상자)을 읽어
YOLO 라벨로 변환하고, data/processed/ 아래에 KITTI와 같은 구조로 놓는다.
그 뒤로는 기존 파이프라인(error_injector, train, diagnose_labels)이 그대로
돈다 — 데이터셋이 다르다는 건 경로 접미사로만 드러난다.

**Car 한 클래스만 쓴다.** COCO `bicycle`은 자전거 자체를, KITTI `Cyclist`는
자전거 탄 사람을 가리켜 의미가 다르다. 애매한 매핑을 넣으면 "도메인이 달라서
무너진 것"과 "라벨 정의가 달라서 무너진 것"이 섞인다.

파일 이름은 COCO 이미지 id를 그대로 쓴다(000000000139.jpg → 000000000139).
KITTI 프레임은 6자리(000001)라 겹치지 않는다 — 공유 폴더에 같이 놓여도
서로를 덮지 않는다.

사용법:
  AIDA_DATASET=coco python prepare_coco.py
"""
import json
import shutil
import sys
from pathlib import Path

import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

COCO_DIR = config.RAW_DIR / "coco"


def to_yolo(box: list[float], width: int, height: int) -> str:
    """COCO [x, y, w, h](좌상단) → YOLO [cls cx cy w h](정규화)."""
    x, y, w, h = box
    cx, cy = (x + w / 2) / width, (y + h / 2) / height
    # 상자가 이미지 밖으로 조금 나가는 경우가 있다. 자르지 않고 가두기만 한다 —
    # 잘라내면 상자 크기가 달라져 오류 주입의 기준이 흔들린다.
    cx, cy = min(max(cx, 0.0), 1.0), min(max(cy, 0.0), 1.0)
    return f"0 {cx:.6f} {cy:.6f} {w / width:.6f} {h / height:.6f}"


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="COCO를 KITTI 형식으로 변환")
    ap.add_argument("--n-train", type=int, default=config.N_TRAIN)
    ap.add_argument("--n-val", type=int, default=config.N_VAL)
    args = ap.parse_args()

    if config.DATASET != "coco":
        raise SystemExit("AIDA_DATASET=coco 로 실행할 것 — 아니면 KITTI 산출물을 덮는다")

    sel_path = COCO_DIR / "selected.json"
    if not sel_path.exists():
        raise SystemExit(f"{sel_path} 없음 — download_coco.py를 먼저 돌릴 것")
    sel = json.loads(sel_path.read_text(encoding="utf-8"))

    ids = [str(i) for i in sel["image_ids"]]
    need = args.n_train + args.n_val
    if len(ids) < need:
        raise SystemExit(f"이미지가 {len(ids)}장뿐인데 {need}장이 필요하다")
    train_ids, val_ids = ids[:args.n_train], ids[args.n_train:need]

    for split, split_ids in (("train", train_ids), ("val", val_ids)):
        img_dir = (config.IMAGES_TRAIN_DIR if split == "train" else config.IMAGES_VAL_DIR)
        lbl_dir = (config.LABELS_GT_TRAIN_DIR if split == "train"
                   else config.LABELS_GT_VAL_DIR)
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        n_boxes = 0
        for image_id in split_ids:
            name = sel["files"][image_id]
            stem = Path(name).stem
            src = COCO_DIR / "images" / name
            if not src.exists():
                raise SystemExit(f"{src} 없음 — download_coco.py를 다시 돌릴 것")
            # 확장자를 .png로 바꾸지 않는다. ultralytics는 확장자를 가리지 않고,
            # 억지로 바꾸면 실제 형식과 이름이 어긋나 나중에 헷갈린다.
            dst = img_dir / name
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dst)

            width, height = sel["sizes"][image_id]
            lines = [to_yolo(b, width, height) for b in sel["boxes"][image_id]]
            (lbl_dir / f"{stem}.txt").write_text("\n".join(lines) + "\n",
                                                 encoding="utf-8")
            n_boxes += len(lines)
        print(f"{split}: 이미지 {len(split_ids)}장, 자동차 {n_boxes}개 "
              f"(장당 {n_boxes / len(split_ids):.1f}개)")
        print(f"  이미지 → {img_dir}")
        print(f"  라벨   → {lbl_dir}")

    # 프레임 목록도 남긴다 — error_injector가 어떤 stem을 쓸지 정할 때 읽는다
    stems = [Path(sel["files"][i]).stem for i in ids[:need]]
    config.SELECTED_FRAMES_FILE.write_text("\n".join(stems) + "\n", encoding="utf-8")
    print(f"\n프레임 목록 → {config.SELECTED_FRAMES_FILE}")


if __name__ == "__main__":
    main()
