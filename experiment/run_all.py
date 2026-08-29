"""전체 파이프라인을 하나의 배치로 순차 실행.

download_kitti.py → data_loader.py → error_injector.py → (train.py + evaluate.py)
순서로 실행한다. 학습은 핵심 7개(priority 1)를 먼저 끝내고 나서 세분화 6개
(priority 2)를 실행하므로, 중간에 시간이 부족해 멈추더라도 핵심 실험 결과는
이미 backend/app/data/metrics.csv에 반영되어 있다.

사용 예:
  python run_all.py                 # 전체 13개 조건
  python run_all.py --priority 1     # 핵심 7개만
  python run_all.py --skip-download  # 이미 다운로드/전처리 끝났으면 학습부터
"""
import argparse

import config
import data_loader
import download_kitti
import error_injector
from evaluate import append_metrics, evaluate_condition
from train import train_condition


def main():
    parser = argparse.ArgumentParser(description="AIDA 실험 파이프라인 전체 실행")
    parser.add_argument("--priority", choices=["1", "2", "all"], default="all")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-preprocess", action="store_true", help="data_loader/error_injector 스킵")
    parser.add_argument("--epochs", type=int, default=None, help="config.EPOCHS 대신 사용 (스모크 테스트용)")
    parser.add_argument("--conditions", nargs="+",
                        help="특정 조건만 실행 (예: 이미 끝난 조건을 다시 돌리지 않을 때)")
    args = parser.parse_args()

    if not args.skip_download:
        download_kitti.main([])
    if not args.skip_preprocess:
        data_loader.main()
        error_injector.main()

    by_name = {c.name: c for c in config.CONDITIONS}
    if args.priority == "1":
        names = config.PRIORITY_1_NAMES
    elif args.priority == "2":
        names = config.PRIORITY_2_NAMES
    else:
        # PRIORITY_1/2(13개)만 쓰면 나중에 추가된 NEXT_PHASE_CONDITIONS(스케일·
        # 중심점이동 8개)가 "all"에서 빠진다 — conditions_in_run_order()가 21개
        # 전체(핵심 13개 + 확장 8개)를 올바른 순서로 반환한다.
        names = [c.name for c in config.conditions_in_run_order()]

    if args.conditions:
        unknown = [n for n in args.conditions if n not in by_name]
        if unknown:
            raise SystemExit(f"알 수 없는 조건: {unknown}")
        names = [n for n in names if n in set(args.conditions)]

    for i, name in enumerate(names, 1):
        condition = by_name[name]
        print(f"\n=== [{i}/{len(names)}] {condition.name} ({condition.type} {condition.magnitude}) ===")
        train_condition(condition, epochs=args.epochs)
        append_metrics(evaluate_condition(condition))

    print(f"\n전체 완료 → {config.METRICS_CSV}")


if __name__ == "__main__":
    main()
