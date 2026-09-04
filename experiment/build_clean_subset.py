"""정제가 고른 것과 **같은 프레임에 깨끗한 라벨**을 붙인 대조군을 만든다.

자기 정제 실험(docs/21 W·X)은 네 칸으로 손익을 분해한다:

  전체 N장 · 오류 0%    (clean)              상한
  전체 N장 · 오류 30%   (scale_m30)          정제 안 함
  절반    · 오류 0%     (clean_sub<N/2>)     ← 이 스크립트가 만든다
  절반    · 오류 ~12%   (scale_m30_refined50) 정제한 것

세 번째 칸이 핵심이다. **이미지를 반 버리는 손해만 따로 떼어내는 대조군**이라,
정제가 지는 이유가 "데이터가 줄어서"인지 "남은 오류 때문"인지 가른다.

그래서 refined50이 고른 것과 **정확히 같은 프레임**을 써야 한다. 다른 프레임을
쓰면 장면 난이도 차이가 섞여 비교가 깨진다.

사용법:
  python build_clean_subset.py --from scale_m30_refined50
"""
import argparse
import sys

import config
from error_injector import symlink_files, write_data_yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    ap = argparse.ArgumentParser(description="정제 부분집합의 깨끗한 대조군")
    ap.add_argument("--from", dest="source", required=True,
                    help="기준이 될 정제 조건 (예: scale_m30_refined50)")
    ap.add_argument("--name", default=None,
                    help="만들 조건 이름 (기본: clean_sub<프레임 수>)")
    args = ap.parse_args()

    src = config.CONDITIONS_DIR / args.source
    if not src.is_dir():
        raise SystemExit(f"{src} 없음 — refine_ruler.py를 먼저 돌릴 것")

    kept = {p.stem for p in (src / "images" / "train").iterdir()}
    if not kept:
        raise SystemExit(f"{src}에 학습 이미지가 없다")
    name = args.name or f"clean_sub{len(kept)}"

    out = config.CONDITIONS_DIR / name
    # 이미지는 같은 프레임, 라벨은 **깨끗한 원본**을 쓴다. 이게 조건의 전부다 —
    # 정제 조건은 오류가 주입된 라벨을 쓰고, 이쪽은 참값을 쓴다.
    symlink_files(config.IMAGES_TRAIN_DIR, out / "images" / "train", kept)
    symlink_files(config.LABELS_GT_TRAIN_DIR, out / "labels" / "train", kept)
    val_stems = {p.stem for p in config.LABELS_GT_VAL_DIR.glob("*.txt")}
    symlink_files(config.IMAGES_VAL_DIR, out / "images" / "val", val_stems)
    symlink_files(config.LABELS_GT_VAL_DIR, out / "labels" / "val", val_stems)
    yaml_path = write_data_yaml(out)

    n_boxes = sum(len(p.read_text(encoding="utf-8").strip().splitlines())
                  for p in (out / "labels" / "train").glob("*.txt")
                  if p.read_text(encoding="utf-8").strip())
    print(f"[{name}] {args.source}와 같은 {len(kept)}장 + 깨끗한 라벨 "
          f"(상자 {n_boxes}개)")
    print(f"  → {out}\n  → {yaml_path}")
    if name not in config._BY_NAME:
        print(f"  주의: config에 '{name}'이 없어 이름으로 학습할 수 없다. "
              f"REFINED_CONDITIONS에 추가할 것.")


if __name__ == "__main__":
    main()
