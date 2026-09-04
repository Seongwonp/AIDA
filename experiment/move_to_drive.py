"""실험 산출물을 다른 드라이브로 옮긴다 — 심볼릭 링크를 보존하면서.

robocopy는 이 일에 못 쓴다. 기본 동작은 링크를 **따라가서 실제 파일로**
복사하는데, 조건 폴더의 이미지가 대부분 링크라 8GB짜리가 57GB로 부푼다.
`/SL`(링크 자체를 복사)은 심볼릭 링크 생성 권한이 없어 실패하면서, 그
자리에 **0바이트 파일**을 남긴다 — 조용한 데이터 손실이다.

Python의 os.symlink는 같은 환경에서 동작한다(지금 있는 링크들을 그게
만들었다). 그래서 직접 옮긴다:

  - 실제 파일: 옮긴다
  - 심볼릭 링크: 같은 대상을 가리키는 링크를 새로 만든다
  - 링크 대상이 옮기는 트리 안이면: 절대경로 그대로 둔다. 옮긴 뒤 원래
    자리에 정션을 만들 것이므로 그 경로가 다시 해석된다.

사용법:
  python move_to_drive.py --dest D:/AIDA-data/experiment conditions_mc_e123 ...
  python move_to_drive.py --dest D:/AIDA-data/experiment --verify-only <이름>
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent


def move_tree(src: Path, dst: Path) -> dict:
    """src를 dst로 옮긴다. 링크는 링크로 남긴다."""
    stats = {"files": 0, "links": 0, "dirs": 0, "failed": []}
    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        stats["dirs"] += 1
        for name in files:
            s, d = Path(root) / name, dst / rel / name
            if d.exists() or d.is_symlink():
                continue                       # 이미 옮긴 것 — 이어서 돌 수 있게
            try:
                if s.is_symlink():
                    os.symlink(os.readlink(s), d)
                    stats["links"] += 1
                else:
                    shutil.move(str(s), str(d))
                    stats["files"] += 1
            except OSError as e:
                stats["failed"].append((str(s), repr(e)))
    return stats


def verify(dst: Path) -> dict:
    """옮긴 뒤 상태. 진짜 빈 파일이 있으면 손실 신호다."""
    out = {"files": 0, "links": 0, "empty_real": 0, "dead_links": 0}
    for root, _dirs, files in os.walk(dst):
        for name in files:
            p = Path(root) / name
            if p.is_symlink():
                out["links"] += 1
                if not p.exists():             # 대상이 없다
                    out["dead_links"] += 1
            else:
                out["files"] += 1
                if p.stat().st_size == 0:
                    out["empty_real"] += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="링크를 보존하며 다른 드라이브로 이동")
    ap.add_argument("names", nargs="+", help="experiment/ 아래 폴더 이름")
    ap.add_argument("--dest", required=True, help="옮길 대상 폴더")
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    dest_root = Path(args.dest)
    for name in args.names:
        src, dst = HERE / name, dest_root / name
        if args.verify_only:
            print(f"[{name}] {verify(dst)}")
            continue
        if src.is_symlink():
            print(f"[{name}] 이미 정션 — 건너뜀")
            continue
        if not src.is_dir():
            print(f"[{name}] 없음 — 건너뜀")
            continue

        print(f"[{name}] 이동 중...", flush=True)
        stats = move_tree(src, dst)
        if stats["failed"]:
            print(f"  실패 {len(stats['failed'])}건 — 원본을 지우지 않는다")
            for path, err in stats["failed"][:3]:
                print(f"    {path}: {err}")
            continue
        after = verify(dst)
        print(f"  옮김: 실파일 {stats['files']}, 링크 {stats['links']}")
        print(f"  검증: 실파일 {after['files']}, 링크 {after['links']}, "
              f"빈 실파일 {after['empty_real']}, 끊긴 링크 {after['dead_links']}")

        shutil.rmtree(src)
        # 정션은 관리자 권한 없이도 만들어진다. 이걸로 기존 절대경로가 그대로
        # 동작하므로 코드를 한 줄도 안 고쳐도 된다.
        os.system(f'cmd /c mklink /J "{src}" "{dst}" >nul')
        print(f"  정션 생성 → {dst}")


if __name__ == "__main__":
    main()
