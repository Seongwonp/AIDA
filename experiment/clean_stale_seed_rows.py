"""다중 시드 CSV에서 '돌리지 않았는데 기록된' 행을 지운다.

run_multi_seed가 metrics.csv를 통째로 복사하던 시절, 그 실행과 무관한
조건들(재검수 시뮬레이션·정제 부분집합처럼 한 번만 학습한 것)의 seed=42 값이
새 시드의 측정값인 척 기록됐다. 집계하면 "시드 3개인데 편차 0"이 되어 오히려
확실해 보인다.

기준은 이름이 아니라 **실제 학습 산출물의 유무**다: 그 시드의 runs 디렉토리에
가중치가 없으면 그 시드에서 돌린 적이 없는 것이다.

사용법:
  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" python clean_stale_seed_rows.py
  ... --apply     실제로 지운다 (기본은 보고만)
"""
import argparse
import os
import sys

import pandas as pd

import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def runs_dir_for(seed: int):
    """그 시드의 runs 디렉토리. config는 import 시점 환경으로 굳으므로 직접 만든다."""
    suffix = config._csuffix + (f"_e{seed}" if seed != 42 else "")
    return config.EXPERIMENT_ROOT / f"runs{suffix}"


def main() -> None:
    ap = argparse.ArgumentParser(description="가중치 없는 시드 행 정리")
    ap.add_argument("--apply", action="store_true", help="실제로 지운다")
    args = ap.parse_args()

    path = config.MULTI_SEED_CSV
    if not path.exists():
        raise SystemExit(f"{path} 없음")
    df = pd.read_csv(path)

    drop_idx = []
    for seed, grp in df.groupby("error_seed"):
        rd = runs_dir_for(int(seed))
        have = ({d.name for d in rd.iterdir()
                 if d.is_dir() and (d / "weights" / "best.pt").exists()}
                if rd.is_dir() else set())
        stale = grp[~grp["condition"].isin(have)]
        if len(stale):
            print(f"seed {seed}: {len(grp)}행 중 {len(stale)}행이 "
                  f"{rd.name}에 가중치가 없습니다")
            print(f"  {', '.join(sorted(stale['condition'])[:6])}"
                  + (" ..." if len(stale) > 6 else ""))
            drop_idx += list(stale.index)

    if not drop_idx:
        print("지울 행 없음")
        return
    print(f"\n총 {len(drop_idx)}행 / 남는 행 {len(df) - len(drop_idx)}")
    if not args.apply:
        print("--apply 를 주면 실제로 지웁니다.")
        return
    df.drop(index=drop_idx).to_csv(path, index=False)
    print(f"정리 완료 → {path}")


if __name__ == "__main__":
    main()
