"""링크였어야 할 파일이 실제 복사본이 된 것을 되돌린다.

robocopy로 조건 폴더를 옮길 때 심볼릭 링크를 따라가 버려서, 8GB짜리가
57GB로 부풀었다. 이미지가 대부분 링크였는데 조건마다 전부 복사됐기
때문이다(같은 이미지가 30번씩 들어 있다).

되돌리는 방법: 조건 폴더의 이미지가 원본(data/processed/images)과 **내용이
같으면** 링크로 바꾼다. 내용을 대조하므로 오류 주입으로 달라진 파일은
건드리지 않는다 — 라벨은 조건마다 다르니 애초에 대상이 아니고, 이미지는
어떤 조건에서도 변형하지 않는다.

안전장치:
  - 크기가 다르면 건너뛴다(빠른 1차 거름)
  - 크기가 같아도 내용을 전부 비교한다
  - 링크 생성에 실패하면 원본을 그대로 둔다

사용법:
  python relink_duplicates.py --dry-run D:/AIDA-data/experiment/conditions
  python relink_duplicates.py D:/AIDA-data/experiment/conditions
"""
import argparse
import filecmp
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
# 이미지 원본. 조건 폴더의 이미지는 전부 여기서 왔다.
SOURCES = [HERE / "data" / "processed" / "images" / "train",
           HERE / "data" / "processed" / "images" / "val"]


def source_for(name: str) -> Path | None:
    for d in SOURCES:
        p = d / name
        if p.exists():
            return p
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="복사본을 링크로 되돌린다")
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for root in args.roots:
        root_path = Path(root)
        if not root_path.is_dir():
            print(f"[{root}] 없음 — 건너뜀")
            continue
        relinked = skipped = freed = failed = 0
        for img in root_path.rglob("images/*/*"):
            if img.is_symlink() or not img.is_file():
                continue
            src = source_for(img.name)
            if src is None or src.stat().st_size != img.stat().st_size:
                skipped += 1
                continue
            if not filecmp.cmp(src, img, shallow=False):
                skipped += 1                    # 내용이 다르면 손대지 않는다
                continue
            size = img.stat().st_size
            if args.dry_run:
                relinked += 1
                freed += size
                continue
            try:
                img.unlink()
                os.symlink(src, img)
                relinked += 1
                freed += size
            except OSError:
                failed += 1
        print(f"[{root_path.name}] 링크로 되돌림 {relinked}개, 건너뜀 {skipped}개, "
              f"실패 {failed}개, 회수 {freed/1e9:.2f}GB"
              + (" (모의 실행)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
