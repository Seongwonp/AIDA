"""새 평가 데이터가 우리 자의 학습 데이터와 겹치는가 (docs/24 C1).

**왜 필요한가.** 자는 KITTI와 COCO로 학습했다. 평가 데이터에 그 이미지가
섞여 있으면 자가 이미 본 것을 진단하는 셈이라 **성능이 실제보다 좋게 나온다.**
파일 이름이 다르다고 다른 이미지가 아니다 — 크기를 바꾸거나 다시 인코딩한
사본은 이름도 해시도 다르다.

**어떻게 재는가.** dHash(차이 해시)를 쓴다. 이미지를 9×8 회색조로 줄이고 가로
이웃 픽셀의 대소를 64비트로 적는다. 크기 변경·재인코딩·약한 압축에는 거의 안
변하고, 다른 장면에서는 크게 벌어진다. 두 해시의 해밍 거리로 판정한다.

**정확한 방법이 아니다.** 비슷한 장면(같은 도로를 몇 초 뒤에 찍은 프레임)도
가깝게 나온다. 그것도 알아야 하는 정보다 — docs/24 C가 "연속 장면 등 가까운
표본"을 함께 확인하라고 적은 이유다.

사용법:
  python check_dataset_overlap.py --candidate <새 데이터 이미지 폴더>
  python check_dataset_overlap.py --candidate <폴더> --threshold 6
"""
import argparse
import collections
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config  # noqa: E402

SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
# 해밍 거리가 이 이하면 "같은 이미지로 의심"한다. dHash 64비트에서 0~5는
# 재인코딩·크기 변경 수준, 10 이상은 대체로 다른 장면이다. **이 값은 판정이
# 아니라 사람이 볼 목록을 만드는 문턱이다.**
DEFAULT_THRESHOLD = 5


def dhash(path: Path) -> int | None:
    """9×8로 줄여 가로 이웃의 대소를 64비트로."""
    try:
        with Image.open(path) as im:
            small = im.convert("L").resize((9, 8), Image.LANCZOS)
            px = list(small.getdata())
    except Exception:
        return None                      # 깨진 파일은 건너뛴다
    bits = 0
    for row in range(8):
        base = row * 9
        for col in range(8):
            bits = (bits << 1) | int(px[base + col] > px[base + col + 1])
    return bits


def hashes_of(directory: Path) -> dict[int, list[str]]:
    out: dict[int, list[str]] = collections.defaultdict(list)
    for p in sorted(directory.rglob("*")):
        if p.suffix.lower() not in SUFFIXES or not p.is_file():
            continue
        h = dhash(p)
        if h is not None:
            out[h].append(p.name)
    return out


def known_image_dirs(paths: list[Path] | None) -> list[tuple[str, Path]]:
    """우리가 자를 학습할 때 쓴 이미지 폴더들.

    **KITTI와 COCO가 한 폴더에 섞여 있다.** 이미지 경로는 데이터셋별로 갈리지
    않고(`config.PROCESSED_DIR / "images"`), 어느 프레임이 어느 데이터셋인지는
    `selected_frames*.txt`와 `labels_gt*`가 정한다. 그래서 겹침 검사는 폴더
    전체를 상대로 한다 — 갈라 봐야 얻을 것이 없고 빠뜨릴 위험만 있다.
    """
    if paths:
        return [(str(p), p) for p in paths if p.is_dir()]
    root = config.PROCESSED_DIR / "images"
    return [(f"학습에 쓴 이미지 전체 ({root.name})", root)] if root.is_dir() else []


def main() -> None:
    ap = argparse.ArgumentParser(description="평가 데이터가 학습 데이터와 겹치는가")
    ap.add_argument("--candidate", required=True, type=Path)
    ap.add_argument("--against", nargs="*", type=Path, default=None,
                    help="비교할 폴더들 (기본: 학습에 쓴 이미지 전체)")
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    ap.add_argument("--show", type=int, default=10)
    args = ap.parse_args()

    if not args.candidate.is_dir():
        raise SystemExit(f"{args.candidate} 없음")

    cand = hashes_of(args.candidate)
    n_cand = sum(len(v) for v in cand.values())
    if not n_cand:
        raise SystemExit("후보 폴더에 이미지가 없습니다")
    print(f"후보 이미지 {n_cand}장 (고유 해시 {len(cand)}개)")

    dirs = known_image_dirs(args.against)
    if not dirs:
        raise SystemExit("비교할 학습 이미지 폴더를 못 찾았습니다")

    total_hits = 0
    for label, d in dirs:
        known = hashes_of(d)
        n_known = sum(len(v) for v in known.values())
        exact = sum(len(cand[h]) for h in cand if h in known)
        near = []
        if args.threshold > 0:
            for hc in cand:
                for hk in known:
                    if hc != hk and bin(hc ^ hk).count("1") <= args.threshold:
                        near.append((cand[hc][0], known[hk][0], bin(hc ^ hk).count("1")))
        total_hits += exact + len(near)
        print(f"\n■ {label} ({n_known}장)")
        print(f"  해시 완전 일치 {exact}장 · 거리 {args.threshold} 이하 {len(near)}쌍")
        for a, b, dist in near[:args.show]:
            print(f"    {a}  ~  {b}  (거리 {dist})")
        if len(near) > args.show:
            print(f"    … {len(near) - args.show}쌍 더")

    print()
    if total_hits == 0:
        print("겹침이 안 보인다. **없다는 증명은 아니다** — dHash가 못 잡는 변형이 있다.")
    else:
        print(f"의심 {total_hits}건. **사람이 눈으로 확인해야 한다** — 비슷한 장면과")
        print("같은 이미지를 이 도구는 구분하지 못한다.")


if __name__ == "__main__":
    main()
