"""다중 error-seed 반복 실험.

AABB 21개 + OBB 5개 조건을 추가 error-seed로 재실행한다.
train/val 분할(SEED=42)은 고정하고 오류 주입 패턴만 바꿔
"같은 데이터, 다르게 주입된 오류"에서도 성능 패턴이 재현되는지 검증한다.

모든 결과는 metrics_multi_seed.csv / metrics_obb_multi_seed.csv에 누적된다.
첫 실행 시 기존 seed=42 결과(metrics.csv, metrics_obb.csv)를 자동 마이그레이션한다.

사용 예:
  python run_multi_seed.py                       # seed 123, 2024 실행
  python run_multi_seed.py --seeds 123 2024 999  # 원하는 seed 지정
  python run_multi_seed.py --migrate-only        # 기존 결과 마이그레이션만
  python run_multi_seed.py --epochs 1            # 스모크 테스트
  python run_multi_seed.py --obb-only            # OBB만 재실행
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

import config

DEFAULT_EXTRA_SEEDS = [123, 2024]


def migrate_seed42() -> None:
    """기존 seed=42 결과를 multi-seed CSV로 마이그레이션한다."""
    # AABB
    if config.METRICS_CSV.exists():
        df = pd.read_csv(config.METRICS_CSV)
        if "error_seed" not in df.columns:
            df.insert(0, "error_seed", 42)
        _merge_into(df, config.MULTI_SEED_CSV)
        print(f"AABB seed=42 마이그레이션 완료 → {config.MULTI_SEED_CSV}")
    else:
        print(f"[경고] {config.METRICS_CSV} 없음 — AABB seed=42 마이그레이션 건너뜀")

    # OBB — 다중 클래스에서는 건너뛴다. OBB 지표 CSV는 클래스 구성별로 갈려
    # 있지 않아(run_obb.py의 _refuse_multiclass 참고) 같은 파일을 다시 만지게
    # 되고, 로그만 보면 뭔가 한 것처럼 보여 혼란스럽다.
    if config.MULTICLASS:
        print("다중 클래스 구성이라 OBB 마이그레이션은 건너뜁니다 (단일 클래스 전용)")
    elif config.OBB_METRICS_CSV.exists():
        df = pd.read_csv(config.OBB_METRICS_CSV)
        if "error_seed" not in df.columns:
            df.insert(0, "error_seed", 42)
        _merge_into(df, config.OBB_MULTI_SEED_CSV)
        print(f"OBB seed=42 마이그레이션 완료 → {config.OBB_MULTI_SEED_CSV}")
    else:
        print(f"[경고] {config.OBB_METRICS_CSV} 없음 — OBB seed=42 마이그레이션 건너뜀")


def _merge_into(new_df: pd.DataFrame, csv_path: Path) -> None:
    """새 행을 기존 CSV에 병합한다. (error_seed, condition) 중복은 덮어쓴다."""
    if csv_path.exists():
        existing = pd.read_csv(csv_path)
        key = ["error_seed", "condition"]
        # 기존에서 겹치는 행 제거 후 합치기
        merged = existing[
            ~existing.set_index(key).index.isin(new_df.set_index(key).index)
        ]
        combined = pd.concat([merged, new_df], ignore_index=True)
    else:
        combined = new_df

    combined = combined.sort_values(["error_seed", "condition"])
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(csv_path, index=False)


def run_seed(seed: int, epochs: int | None, aabb: bool, obb: bool,
             conditions: list[str] | None = None) -> None:
    """하나의 error-seed에 대해 오류 주입 → 학습 → 평가 → CSV 저장 순으로 실행."""
    print(f"\n{'='*60}")
    print(f" error_seed = {seed}")
    print(f"{'='*60}")

    env = {**os.environ, "AIDA_ERROR_SEED": str(seed)}
    extra = ["--epochs", str(epochs)] if epochs else []
    if conditions:
        extra += ["--conditions", *conditions]

    if aabb:
        print(f"\n── AABB 오류 주입 (seed={seed}) ──")
        subprocess.run(
            [sys.executable, "error_injector.py"],
            env=env, check=True,
        )
        print(f"\n── AABB 학습·평가 (seed={seed}) ──")
        subprocess.run(
            [sys.executable, "run_all.py", "--skip-download", "--skip-preprocess"] + extra,
            env=env, check=True,
        )
        # run_all.py가 metrics.csv에 쓴 결과를 multi_seed_csv로 복사
        _copy_to_multi_seed(config.MULTI_SEED_CSV, seed, is_obb=False, env=env,
                            only=conditions)
        _restore_canonical(config.METRICS_CSV, config.MULTI_SEED_CSV, seed)

    if obb:
        print(f"\n── OBB 오류 주입 (seed={seed}) ──")
        subprocess.run(
            [sys.executable, "-c",
             "import config, error_injector\n"
             "[error_injector.build_obb_condition(c) for c in config.OBB_CONDITIONS]"],
            env=env, check=True,
        )
        print(f"\n── OBB 학습·평가 (seed={seed}) ──")
        subprocess.run(
            [sys.executable, "run_obb.py", "--skip-preprocess"] + extra,
            env=env, check=True,
        )
        _copy_to_multi_seed(config.OBB_MULTI_SEED_CSV, seed, is_obb=True, env=env)
        _restore_canonical(config.OBB_METRICS_CSV, config.OBB_MULTI_SEED_CSV, seed)


def _restore_canonical(canonical_csv: Path, multi_csv: Path, seed: int) -> None:
    """run_all.py/run_obb.py는 항상 canonical_csv(metrics.csv 등)를 덮어쓴다.

    seed!=42 실행 직후에는 canonical_csv가 방금 돌린 seed의 결과로 남아있는
    상태다. metrics.csv/metrics_obb.csv는 "seed=42 기준값"이라는 의미로
    대시보드 폴백·리포트·문서 등 여러 곳에서 직접 참조하므로, 해당 seed의
    복사가 끝나는 즉시 seed=42 기준값으로 되돌려 놓는다. multi_csv에 이미
    error_seed=42 행이 있다는 전제이므로 migrate_seed42()가 먼저 실행돼야
    한다(main()에서 항상 그렇게 함).
    """
    if seed == 42 or not multi_csv.exists():
        return
    df = pd.read_csv(multi_csv)
    baseline = df[df["error_seed"] == 42].drop(columns="error_seed")
    if baseline.empty:
        print(f"[경고] {multi_csv}에 error_seed=42 행이 없어 {canonical_csv} 복원 불가")
        return
    baseline.to_csv(canonical_csv, index=False)


def _copy_to_multi_seed(multi_csv: Path, seed: int, is_obb: bool, env: dict,
                         only: list[str] | None = None) -> None:
    """run_all/run_obb가 갱신한 단일-seed CSV를 multi_seed CSV에 합친다.

    run_all.py는 AIDA_ERROR_SEED에 따라 다른 RUNS_DIR을 쓰지만
    METRICS_CSV 경로는 동일하다 (metrics.csv 는 '현재 최신 단일 실행' 역할).
    여기서 error_seed 컬럼을 붙여 누적 CSV로 이전한다.
    """
    src = config.OBB_METRICS_CSV if is_obb else config.METRICS_CSV

    # subprocess 완료 후 파일을 재로드 (env 변경이 이 프로세스 config에는 반영 안 됨)
    if not src.exists():
        print(f"[경고] {src} 없음 — multi-seed 누적 건너뜀")
        return

    df = pd.read_csv(src)
    if only:
        # 일부 조건만 돌렸다면 그 조건 행만 옮긴다. metrics.csv에는 안 돌린
        # 조건의 seed=42 값이 그대로 남아 있는데, 그걸 통째로 복사하면 이미
        # 제대로 측정해둔 다른 seed 결과를 seed=42 값으로 덮어쓰게 된다.
        df = df[df["condition"].isin(only)]
    df.insert(0, "error_seed", seed)
    _merge_into(df, multi_csv)
    label = "OBB" if is_obb else "AABB"
    print(f"[seed={seed}] {label} → {multi_csv}")


def main() -> None:
    parser = argparse.ArgumentParser(description="다중 error-seed 반복 실험")
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_EXTRA_SEEDS,
                        help="실행할 error seed 목록 (기본: 123 2024)")
    parser.add_argument("--migrate-only", action="store_true",
                        help="기존 seed=42 결과 마이그레이션만 수행 (학습 없음)")
    parser.add_argument("--epochs", type=int, default=None, help="스모크 테스트용 epoch 수")
    parser.add_argument("--aabb-only", action="store_true", help="AABB만 실행")
    parser.add_argument("--obb-only", action="store_true", help="OBB만 실행")
    parser.add_argument("--conditions", nargs="+",
                        help="AABB 조건 중 일부만 실행 (이미 끝난 조건 재실행 방지)")
    args = parser.parse_args()

    run_aabb = not args.obb_only
    run_obb = not args.aabb_only
    if run_obb and config.MULTICLASS:
        # OBB는 단일 클래스 전용이다 (run_obb.py의 _refuse_multiclass 참고).
        # 다중 클래스에서는 AABB만 돌리고 조용히 넘어간다 — 여기서 죽으면
        # AABB 다중 시드까지 못 돌게 된다.
        if args.obb_only:
            raise SystemExit("OBB 실험은 단일 클래스 전용입니다 — --obb-only를 쓸 수 없습니다.")
        print("[알림] 다중 클래스 구성이라 OBB는 건너뜁니다 (단일 클래스 전용 실험)")
        run_obb = False

    print("=== seed=42 결과 마이그레이션 ===")
    migrate_seed42()

    if args.migrate_only:
        print("\n마이그레이션 완료. --migrate-only 지정으로 학습은 건너뜀.")
        return

    total = len(args.seeds)
    for i, seed in enumerate(args.seeds, 1):
        print(f"\n[{i}/{total}] error_seed={seed} 시작")
        run_seed(seed, args.epochs, run_aabb, run_obb, args.conditions)

    print(f"\n\n전체 완료!")
    print(f"  AABB 누적: {config.MULTI_SEED_CSV}")
    print(f"  OBB  누적: {config.OBB_MULTI_SEED_CSV}")
    print(f"\n집계하려면: python aggregate_seeds.py")


if __name__ == "__main__":
    main()
