"""학습 산출물 중 안 쓰는 파일 정리.

용량의 대부분은 venv(4.7G)와 KITTI 원본 이미지(843M)라 여기서 건드릴 게
아니다. 학습 폴더 안에서 실제로 버려도 되는 건 두 가지다:

  last.pt        마지막 epoch 체크포인트. 코드 어디서도 안 읽는다
                 (전부 best.pt만 쓴다). 조건당 6MB.
  train_batch*.jpg / val_batch*.jpg
                 학습·평가 중 배치 시각화. 사람이 눈으로 볼 용도이고
                 재실행하면 다시 생긴다. 학습 폴더와 *_val 폴더 양쪽에 있다.

곡선·혼동행렬 PNG는 남긴다. 27MB밖에 안 되고 분석 자료라서다.

**best.pt는 절대 지우지 않는다.** 진단 모델(runs/clean)이고,
evaluate_per_class.py가 재학습 없이 다시 재는 근거이며,
run_all.py --skip-done이 완료 판정에 쓴다.

기본은 보고만 한다. 실제로 지우려면 --delete를 준다.

사용법:
  python cleanup_runs.py             # 얼마나 회수되는지만 확인
  python cleanup_runs.py --delete
"""
import argparse
import sys
import time
from pathlib import Path

import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 지금 학습 중인 조건의 폴더는 건드리지 않는다. 최근에 쓰인 폴더는
# 진행 중일 가능성이 있으므로 통째로 건너뛴다.
ACTIVE_WINDOW_SEC = 300

DISPOSABLE_GLOBS = ["weights/last.pt", "train_batch*.jpg", "val_batch*.jpg"]


def run_dirs() -> list[Path]:
    """모든 학습 결과 폴더. 이름을 나열하지 않고 glob으로 찾는다.

    시드(_e123)·클래스 구성(_mc)·프레임 선택(_cyclist_rich)이 조합되면서
    runs 계열 폴더가 계속 늘어난다. 목록을 손으로 적어두면 새 조합이 생길
    때마다 조용히 빠지고, 정리했다고 생각한 용량이 그대로 남는다.
    """
    return [d for r in sorted(config.EXPERIMENT_ROOT.glob("runs*")) if r.is_dir()
            for d in sorted(r.iterdir()) if d.is_dir()]


def main() -> None:
    parser = argparse.ArgumentParser(description="학습 산출물 정리")
    parser.add_argument("--delete", action="store_true",
                        help="실제로 삭제한다 (기본은 보고만)")
    args = parser.parse_args()

    now = time.time()
    total = 0
    skipped_active, skipped_no_best = [], []
    victims: list[Path] = []

    for d in run_dirs():
        best = d / "weights" / "best.pt"
        is_val_dir = d.name.endswith("_val")
        if not best.exists() and not is_val_dir:
            # 학습이 끝나지 않은 조건 — 재개해야 하므로 손대지 않는다
            skipped_no_best.append(d.name)
            continue
        if now - d.stat().st_mtime < ACTIVE_WINDOW_SEC:
            skipped_active.append(d.name)
            continue
        # *_val은 평가 산출물뿐이라 가중치가 아예 없다. 여기서도 배치
        # 시각화만 지우고 곡선·혼동행렬 PNG는 남긴다 — 그쪽은 분석 자료다.
        patterns = ["val_batch*.jpg"] if is_val_dir else DISPOSABLE_GLOBS
        for pattern in patterns:
            for f in d.glob(pattern):
                if f.is_file():
                    victims.append(f)
                    total += f.stat().st_size

    print(f"정리 대상 {len(victims)}개 파일, {total / 1048576:.0f}MB")
    if skipped_active:
        print(f"  진행 중으로 보여 건너뜀: {', '.join(skipped_active)}")
    if skipped_no_best:
        print(f"  best.pt 없어 건너뜀({len(skipped_no_best)}개): "
              f"{', '.join(skipped_no_best[:6])}"
              + (" ..." if len(skipped_no_best) > 6 else ""))

    if not args.delete:
        print("\n--delete 를 주면 실제로 지웁니다. best.pt는 어떤 경우에도 안 지웁니다.")
        return

    for f in victims:
        f.unlink()
    print(f"\n{total / 1048576:.0f}MB 회수 완료")


if __name__ == "__main__":
    main()
