"""OBB 실험 전체 파이프라인.

data_loader_obb → error_injector_obb → (train_obb + evaluate_obb) 순서로 실행.
KITTI 다운로드와 AABB 전처리(data_loader.main())는 이미 완료된 것을 전제한다.

사용 예:
  python run_obb.py                   # 5개 OBB 조건 전부
  python run_obb.py --skip-preprocess # 라벨 생성이 이미 됐으면 학습부터
  python run_obb.py --epochs 1        # 스모크 테스트
"""
import argparse

import config
import data_loader
import error_injector
from evaluate_obb import append_obb_metrics, evaluate_obb_condition
from train_obb import train_obb_condition


def main():
    parser = argparse.ArgumentParser(description="AIDA OBB 실험 파이프라인")
    parser.add_argument("--skip-preprocess", action="store_true",
                        help="OBB GT 라벨 및 조건 데이터셋 생성 스킵 (이미 완료된 경우)")
    parser.add_argument("--epochs", type=int, default=None)
    args = parser.parse_args()

    if not args.skip_preprocess:
        print("=== OBB GT 라벨 생성 (polygon 포맷, angle=0) ===")
        data_loader.main_obb()

        print("\n=== OBB 조건별 에러 라벨 생성 ===")
        for condition in config.OBB_CONDITIONS:
            error_injector.build_obb_condition(condition)

    print(f"\n=== OBB 학습·평가 시작 (총 {len(config.OBB_CONDITIONS)}개 조건) ===")
    for i, condition in enumerate(config.OBB_CONDITIONS, 1):
        print(f"\n── [{i}/{len(config.OBB_CONDITIONS)}] {condition.name} "
              f"({condition.type} {condition.magnitude}) ──")
        train_obb_condition(condition, epochs=args.epochs)
        append_obb_metrics(evaluate_obb_condition(condition))

    print(f"\n전체 OBB 실험 완료 → {config.OBB_METRICS_CSV}")


if __name__ == "__main__":
    main()
