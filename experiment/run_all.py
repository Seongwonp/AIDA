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


def _breadth_first(names: list[str], by_name: dict) -> list[str]:
    """유형마다 가장 강한 조건 하나씩을 앞으로 당긴다.

    조건 하나에 20분씩 걸려서 전체를 다 돌리려면 10시간이 넘는다. 순서대로
    돌리다 중간에 끊기면 width 네 개는 있는데 missing은 하나도 없는 표가
    남는다 — 유형별 비교가 목적이므로 그런 표는 쓸모가 없다. 유형마다 하나씩
    먼저 끝내두면 언제 끊겨도 모든 유형이 담긴 표가 손에 남는다.

    "가장 강한"은 |magnitude|가 큰 것. 저하가 가장 잘 보이는 조건이다.
    """
    first: dict[str, str] = {}
    for name in names:
        c = by_name[name]
        if c.type == "none":
            continue
        best = first.get(c.type)
        if best is None or abs(by_name[best].magnitude) < abs(c.magnitude):
            first[c.type] = name
    head = [n for n in names if n in set(first.values())]
    return head + [n for n in names if n not in set(head)]


def _already_done() -> set[str]:
    """학습 가중치와 평가 결과가 **둘 다** 있는 조건.

    둘 중 하나만 보면 안 된다 — 학습 도중에 끊기면 가중치 폴더는 있는데
    best.pt가 없거나, best.pt는 있는데 평가를 못 한 상태가 된다. 그런 조건을
    "끝났다"고 넘기면 metrics에 구멍이 남는다.
    """
    import pandas as pd

    if not config.METRICS_CSV.exists():
        return set()
    evaluated = set(pd.read_csv(config.METRICS_CSV)["condition"])
    return {
        name for name in evaluated
        if (config.RUNS_DIR / name / "weights" / "best.pt").exists()
    }


def main():
    parser = argparse.ArgumentParser(description="AIDA 실험 파이프라인 전체 실행")
    parser.add_argument("--priority", choices=["1", "2", "all"], default="all")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-preprocess", action="store_true", help="data_loader/error_injector 스킵")
    parser.add_argument("--epochs", type=int, default=None, help="config.EPOCHS 대신 사용 (스모크 테스트용)")
    parser.add_argument("--conditions", nargs="+",
                        help="특정 조건만 실행 (예: 이미 끝난 조건을 다시 돌리지 않을 때)")
    parser.add_argument("--breadth-first", action="store_true",
                        help="유형마다 가장 강한 조건 하나씩을 먼저 돌린다. "
                             "중간에 끊겨도 모든 유형이 담긴 표가 남는다.")
    parser.add_argument("--skip-done", action="store_true",
                        help="가중치와 metrics 행이 둘 다 있는 조건은 건너뛴다. "
                             "장시간 실행이 중간에 끊겼을 때 이어서 돌리는 용도.")
    args = parser.parse_args()

    if not args.skip_download:
        download_kitti.main([])
    if not args.skip_preprocess:
        data_loader.main()
        error_injector.main()

    # CLASS_SWAP_CONDITIONS는 CONDITIONS에 없다 — 다중 클래스에서 조건 이름을
    # 못 찾는다. evaluate_box_accuracy.py에서도 같은 자리를 고쳤다.
    by_name = {c.name: c for c in config.CONDITIONS + config.CLASS_SWAP_CONDITIONS}
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

    if args.breadth_first:
        names = _breadth_first(names, by_name)

    if args.skip_done:
        done = _already_done()
        skipped = [n for n in names if n in done]
        names = [n for n in names if n not in done]
        if skipped:
            print(f"이미 끝난 조건 {len(skipped)}개 건너뜀: {', '.join(skipped)}")
        if not names:
            print("남은 조건 없음 — 전부 끝나 있습니다.")
            return

    for i, name in enumerate(names, 1):
        condition = by_name[name]
        print(f"\n=== [{i}/{len(names)}] {condition.name} ({condition.type} {condition.magnitude}) ===")
        train_condition(condition, epochs=args.epochs)
        append_metrics(evaluate_condition(condition))

    print(f"\n전체 완료 → {config.METRICS_CSV}")


if __name__ == "__main__":
    main()
