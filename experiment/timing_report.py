"""파일럿 작업 기록에서 시간 요약을 만든다 (docs/manual-timing-pilot.md).

**성과는 보지 않는다.** 여기서 나오는 것은 "후보 하나에 얼마나 걸렸는가"뿐이고,
AIDA가 기준선보다 나은지는 다루지 않는다 — 그건 다른 경로이고 아직 열면 안 된다.

`timing_usable`이 거짓이면 **N을 계산하지 않는다.** 끊긴 기록의 잘린 시간을
넣으면 후보당 시간이 짧아져 N이 부풀려진다.
"""
import argparse
import json
import sys
from pathlib import Path

import config
from evaluation.activity import (budget_from_pilot, delta_scenarios,
                                 plan_seconds_per_candidate, read_events,
                                 summarise_activity)


def load(dataset_id: str, evaluation_id: str) -> list[dict]:
    path = (config.uploads_dir() / dataset_id / "evaluations" / evaluation_id
            / "activity.jsonl")
    if not path.exists():
        raise SystemExit(f"작업 기록이 없습니다: {path}\n"
                         "판정을 한 번도 안 했거나 기록이 전송되지 않았습니다.")
    return read_events(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="파일럿 시간 요약")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--out", help="요약 JSON을 저장할 경로")
    # D와 T를 주면 N을 계산해 본다. **주지 않으면 계산하지 않는다** — 값을
    # 지어내지 않는다.
    parser.add_argument("--datasets", type=int,
                        help="최종 평가의 데이터셋 수 D (아직 미정이면 비워 둔다)")
    parser.add_argument("--total-minutes", type=float,
                        help="전체 활동 시간 상한 T, 분 (아직 미정이면 비워 둔다)")
    args = parser.parse_args()

    summary = summarise_activity(load(args.dataset, args.evaluation))
    plan = plan_seconds_per_candidate(summary)
    data = summary.as_dict()

    print(f"세션 {summary.sessions}개 "
          f"(온전 {summary.complete_sessions}, 끊김 {summary.incomplete_sessions})")
    print(f"판정한 후보 {summary.judged_candidates}개 "
          f"(보류 {summary.holds})")
    print(f"활동 {data['active_seconds']}초 / 대기 {data['wait_seconds']}초 "
          f"/ 자리비움 {data['idle_seconds']}초")
    print(f"  판정 {data['adjudication_seconds']}초, "
          f"누락 객체 고르기 {data['missing_link_seconds']}초, "
          f"후보 밖 {data['unattributed_seconds']}초")
    print(f"중복 이벤트 {summary.duplicate_events}건, "
          f"빠진 순번 {summary.missing_sequences}개")
    print()
    print(f"timing_usable = {summary.timing_usable}")

    if plan["status"] != "ok":
        print(f"  → N을 계산하지 않습니다: {plan['reason']}")
        print(f"  최소 기준: 온전한 세션 {plan['minimum_sessions']}개, "
              f"판정 후보 {plan['minimum_candidates']}개")
        print(f"  ({plan['minimum_basis']})")
    else:
        print(f"  평균 {plan['mean_seconds']:.2f}초 / "
              f"중앙값 {plan['median_seconds']:.2f}초")
        print(f"  P75 {plan['p75_seconds']:.2f}초 — {plan['p75_basis']}")
        print(f"  s_plan {plan['s_plan_seconds']:.2f}초 — {plan['s_plan_basis']}")

        if args.datasets and args.total_minutes:
            n = budget_from_pilot(args.total_minutes * 60, args.datasets,
                                  plan["s_plan_seconds"])
            print()
            print(f"  D={args.datasets}, T={args.total_minutes}분 → N={n} "
                  f"(데이터셋마다, 총 {None if n is None else n * args.datasets}건)")
            print("  Δ 선택지 — **고르는 것은 사용자다**:")
            for row in delta_scenarios(n):
                print(f"    {row['name']}: {row['rule']} → {row['delta']} "
                      f"({row['note']})")
        else:
            print()
            print("  D와 T를 주면 N을 계산합니다 "
                  "(--datasets, --total-minutes). 지금은 둘 다 미정입니다.")

    if args.out:
        Path(args.out).write_text(
            json.dumps({"summary": data, "plan": plan}, ensure_ascii=False,
                       indent=2), encoding="utf-8")
        print()
        print(f"저장했습니다: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
