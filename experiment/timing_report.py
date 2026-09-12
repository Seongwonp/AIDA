"""파일럿 작업 기록에서 시간 요약을 만든다 (docs/manual-timing-pilot.md).

**자동 클릭으로 잰 시간은 N에 쓰지 않는다.** 사람이 이미지를 보고 판단한
시간이어야 하고, 그렇지 않아 보이면 `implausible_for_human_judging`으로
막는다. 통과했다고 사람이 한 것이 증명되지는 않는다 — 못 한 것만 걸러낸다.

**성과는 보지 않는다.** 여기서 나오는 것은 "후보 하나에 얼마나 걸렸는가"뿐이고,
AIDA가 기준선보다 나은지는 다루지 않는다 — 그건 다른 경로이고 아직 열면 안 된다.

`timing_usable`이 거짓이면 **N을 계산하지 않는다.** 끊긴 기록의 잘린 시간을
넣으면 후보당 시간이 짧아져 N이 부풀려진다.
"""
import argparse
import json
import sys
from pathlib import Path

# 콘솔이 UTF-8이 아니면(윈도우 cp949, 파일로 리다이렉션) 설명문의 `—` 한 글자에
# **판정을 끝낸 직후** 보고서가 죽는다. 이 자리에서 죽은 것이 네 번째다.
# UTF-8 콘솔에서는 바뀔 것이 없고, 아닌 콘솔에서는 글자가 `?`로 나오지만 산다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

import config
from evaluation.activity import (INTERVAL_SIZE, S_PLAN_BASIS_LIMITS,
                                 budget_from_pilot, capacity_from_blocks,
                                 capacity_table, delta_scenarios,
                                 plan_seconds_per_candidate, read_events,
                                 summarise_activity, sustained_plan)


def load(dataset_id: str, evaluation_id: str) -> list[dict]:
    path = (config.uploads_dir() / dataset_id / "evaluations" / evaluation_id
            / "activity.jsonl")
    if not path.exists():
        raise SystemExit(f"작업 기록이 없습니다: {path}\n"
                         "판정을 한 번도 안 했거나 기록이 전송되지 않았습니다.")
    return read_events(path.read_text(encoding="utf-8"))


def parse_pilots(args) -> list[tuple[str, str]]:
    """어느 (데이터셋, 평가)들을 합쳐 볼 것인가.

    **블록을 나눠 하면 세션도 나뉜다.** 주소가 여러 개면 페이지도 여러 번 뜨고,
    그러면 세션 분리가 사람의 기억에 안 달린다 — timing1·timing2에서 두 번
    다 한 세션으로 끝났다.
    """
    pairs = []
    for raw in args.pilot or []:
        if ":" not in raw:
            raise SystemExit(f"--pilot은 '데이터셋:평가' 꼴입니다: {raw}")
        dataset, evaluation = raw.split(":", 1)
        pairs.append((dataset, evaluation))
    if args.dataset and args.evaluation:
        pairs.append((args.dataset, args.evaluation))
    if not pairs:
        raise SystemExit("--dataset/--evaluation 또는 --pilot을 주세요.")
    return pairs


def anchor_report(dataset_id: str, evaluation_id: str) -> dict | None:
    """anchor 판정 결과. **과속·무성의를 잡는 가드레일이지 정확도 증거가 아니다.**

    실제 후보에는 정답이 없어 "빨라진 것이 숙련인지 무성의인지"를 못 가린다.
    그래서 정답이 알려진 후보를 섞어 두었다.

    **허용 기준은 사전 등록돼 있지 않다.** 결과를 보고 정하면 기준이 아니라
    사후 설명이므로, 숫자를 만들지 않고 그대로 적기만 한다.
    """
    root = config.uploads_dir() / dataset_id
    key_path = root / "pilot_answer_key.json"
    adj_path = root / "evaluations" / evaluation_id / "adjudications.json"
    snap_path = root / "evaluations" / evaluation_id / "snapshot.json"
    if not (key_path.is_file() and adj_path.is_file() and snap_path.is_file()):
        return None
    try:
        answers = {a["image"]: a for a in
                   json.loads(key_path.read_text(encoding="utf-8"))["answers"]}
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        saved = json.loads(adj_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return None

    verdicts = {a["canonical_candidate_id"]: a["verdict"]
                for a in saved.get("adjudications", [])}
    rows = []
    for candidate in snapshot.get("candidates", []):
        answer = answers.get(candidate["image"])
        if answer is None:
            continue                     # 실제 후보 — 정답이 없다
        expected = "hit" if answer["truth"] == "error" else "miss"
        rows.append({"image": candidate["image"], "truth": answer["truth"],
                     "expected": expected,
                     "verdict": verdicts.get(candidate["canonical_candidate_id"]),
                     "agrees": verdicts.get(
                         candidate["canonical_candidate_id"]) == expected})
    if not rows:
        return None
    clean = [r for r in rows if r["truth"] == "clean"]
    error = [r for r in rows if r["truth"] == "error"]
    return {
        "status": "quality_threshold_not_preregistered",
        "total": len(rows),
        "clean_agree": sum(1 for r in clean if r["agrees"]), "clean": len(clean),
        "error_agree": sum(1 for r in error if r["agrees"]), "error": len(error),
        "rows": rows,
        "note": ("과속·무성의 판정을 잡는 가드레일이다. AIDA의 효능이나 실제 "
                 "후보의 판정 정확도가 아니다. 허용 기준은 사전 등록돼 있지 "
                 "않으므로 사람이 보고 판단한다."),
    }


def judging_mode(dataset_id: str, override: str | None) -> str | None:
    """이 파일럿을 어떻게 했는가. **기록만 보고는 알 수 없다.**

    다른 도구에서 화면을 들여다본 시간은 판정 탭의 활동 시간에 안 들어가므로,
    속도도 보류 비율도 멀쩡해 보인다. 그래서 `make_timing_pilot.py`가 적어 둔
    값을 읽고, 없으면 **모르는 채로 둔다** — 모르는 것을 "도움 없이 했다"로
    읽으면 실수 하나가 기준이 된다.
    """
    if override:
        return override
    path = config.uploads_dir() / dataset_id / "pilot_meta.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("judging_mode")
    except (OSError, ValueError):
        return None


def candidate_source(dataset_id: str) -> str | None:
    """후보가 실제 진단에서 왔는가, 주입한 오류인가.

    **안 적혀 있으면 모르는 채로 둔다.** 모르는 것을 "실제 후보였다"로 읽으면
    하한을 계획값으로 쓰게 된다.
    """
    path = config.uploads_dir() / dataset_id / "pilot_meta.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("candidate_source")
    except (OSError, ValueError):
        return None


EVIDENCE_LABEL = {
    "observed": "observed        (관측한 범위)",
    "extrapolated": "extrapolated    (관측 밖 — 블록 반복을 가정)",
    "strongly_extrapolated": "strongly_extrapolated (관측에서 멀다 — 채택 불가)",
    "none": "none",
}


def print_capacity(got: dict, datasets: int, total_minutes: float) -> None:
    """`N_capacity` 한 칸을 **근거 범위와 같이** 찍는다.

    숫자만 떼어 옮기면 15블록짜리 조합이 1블록짜리와 똑같아 보인다. 그래서
    블록 수·활동 시간·남는 시간·근거 범위를 한 덩어리로 붙여 찍는다.
    """
    print()
    if got["status"] == "no_plan_value":
        print("  N_capacity를 내지 않습니다 — 계획값이 없습니다.")
        return
    if got["status"] == "missing_input":
        print("  N_capacity를 내지 않습니다 — D·T·블록 크기가 모자랍니다.")
        return

    print(f"  D={datasets}, T={total_minutes}분 (활동 판정 시간 상한)")
    print(f"    블록 {got['block_size']}건 = {got['minutes_per_block']}분")
    if got["status"] == "infeasible":
        print("    N_capacity = 0  (infeasible)")
        print(f"    ！ {got['adoption_note']}")
        print(f"    {got['note']}")
        return

    print(f"    데이터셋당 블록 수      {got['blocks_per_dataset']}")
    print(f"    전체 블록 수            {got['blocks_total']}")
    print(f"    N_capacity              {got['n_capacity']}  (데이터셋당 후보 수)")
    print(f"    전체 후보 수            {got['total_candidates']}")
    print(f"    expected_active         {got['expected_active_minutes']}분")
    print(f"    unallocated_buffer      {got['unallocated_buffer_minutes']}분")
    print(f"    근거 범위               {EVIDENCE_LABEL[got['evidence']]}")
    print(f"    N_required              미정 ({got['n_required_status']})")
    print(f"    N_final                 미정 ({got['n_final_status']})")
    print(f"    {got['time_basis']}")
    print("    남는 시간을 더 많은 후보로 자동 재할당하지 않는다.")
    print(f"    {got['adoption_note']}")


def print_capacity_table(block_size: int, s_plan: float) -> None:
    """**시간 예산별 처리 용량 예시.** "N 표"가 아니다."""
    print()
    print(f"시간 예산별 처리 용량 예시 (블록 {block_size}건, "
          f"s_plan {s_plan:.2f}초)")
    print("  **이 표의 수는 처리 가능량(N_capacity)이지 통계적 표본 크기가 "
          "아닙니다.**")
    print("  N_required(필요량)와 N_final(최종 검수량)은 아직 미정입니다.")
    print()
    print(f"  {'T(분)':>6} {'D':>3} {'N_cap':>7} {'블록/DS':>8} "
          f"{'전체블록':>8} {'active(분)':>11} {'남는(분)':>9}  근거 범위")
    # 10분·30분을 넣어 두는 이유는 **observed 한 줄과 infeasible 한 줄을
    # 표에서 직접 보게 하려는 것**이다. 큰 값만 늘어놓으면 모든 줄이
    # 외삽이라 구분이 눈에 안 들어온다.
    for row in capacity_table((10, 15, 30, 60, 120, 180, 300), (1, 2, 3, 4),
                              block_size, s_plan):
        if row["status"] == "infeasible":
            print(f"  {row['total_minutes']:>6} {row['datasets']:>3} "
                  f"{'0':>7} {'0':>8} {'0':>8} {'-':>11} {'-':>9}  infeasible "
                  "(한 블록도 못 채운다)")
            continue
        print(f"  {row['total_minutes']:>6} {row['datasets']:>3} "
              f"{row['n_capacity']:>7} {row['blocks_per_dataset']:>8} "
              f"{row['blocks_total']:>8} "
              f"{row['expected_active_minutes']:>11} "
              f"{row['unallocated_buffer_minutes']:>9}  {row['evidence']}")
    print()
    print("  observed = 전체 1블록. 그보다 많으면 관측 밖이고, 전체 10블록 "
          "이상은 strongly_extrapolated다.")
    print("  이 표시는 성공 판정이 아니라 **근거가 어디까지인지**를 보여주는 "
          "경고다.")
    print()
    print("  s_plan의 근거 한계:")
    for line in S_PLAN_BASIS_LIMITS:
        print(f"    - {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description="파일럿 시간 요약")
    parser.add_argument("--dataset")
    parser.add_argument("--evaluation")
    parser.add_argument("--pilot", action="append", metavar="DATASET:EVAL",
                        help="블록을 나눠 했을 때. 여러 번 줄 수 있다")
    parser.add_argument("--out", help="요약 JSON을 저장할 경로")
    # D와 T를 주면 N을 계산해 본다. **주지 않으면 계산하지 않는다** — 값을
    # 지어내지 않는다.
    parser.add_argument("--datasets", type=int,
                        help="최종 평가의 데이터셋 수 D (아직 미정이면 비워 둔다)")
    parser.add_argument("--total-minutes", type=float,
                        help="전체 활동 시간 상한 T, 분 (아직 미정이면 비워 둔다)")
    parser.add_argument("--sustained", action="store_true",
                        help="지속 판정 기록으로 읽는다. 재표집 단위가 "
                             "세션이 아니라 구간이 된다")
    parser.add_argument("--interval", type=int, default=INTERVAL_SIZE,
                        help="구간 크기. **실행 전에 고정한다**")
    parser.add_argument("--sustained-block", type=int,
                        help="실제로 끊김 없이 판정한 건수 B. 주면 "
                             "블록 반복 방식으로 N을 낸다")
    parser.add_argument("--reviewed", action="store_true",
                        help="세션별 속도 변화와 anchor 결과를 사람이 "
                             "보고 받아들였다는 표시. 이것 없이는 N을 "
                             "내지 않는다")
    parser.add_argument("--safety-factor", type=float,
                        help="하한으로 잰 s_plan에 곱할 계수. **근거를 문서에 "
                             "적고** 결과 열람 전에 정한다")
    parser.add_argument("--capacity-table", action="store_true",
                        help="시간 예산별 처리 용량 예시를 찍는다. **표본 "
                             "크기가 아니다** — 근거 범위 표시를 같이 본다")
    parser.add_argument("--judging-mode", choices=("unaided_human",
                                                   "assisted_rehearsal"),
                        help="파일럿 메타에 적힌 값을 덮어쓴다")
    args = parser.parse_args()

    pilots = parse_pilots(args)
    modes = {judging_mode(dataset, args.judging_mode) for dataset, _ in pilots}
    if len(modes) > 1:
        # **섞으면 안 된다.** 하나라도 보조받았으면 합친 값도 보조받은 것이다.
        raise SystemExit(f"블록마다 판정 방식이 다릅니다: {sorted(map(str, modes))}")
    mode = modes.pop()

    sources = {candidate_source(dataset) for dataset, _ in pilots}
    if len(sources) > 1:
        raise SystemExit(f"블록마다 후보 출처가 다릅니다: {sorted(map(str, sources))}")
    source = sources.pop()

    events = []
    for dataset, evaluation in pilots:
        events += load(dataset, evaluation)
    summary = summarise_activity(events)
    if args.sustained:
        # **지속 판정은 세션이 하나인 것이 정상이다.** 재표집 단위가 구간으로
        # 바뀐다(docs/sustained-pilot-protocol.md).
        holds = {}
        for e in events:
            if e.get("event") == "verdict_set":
                cid = e.get("canonical_candidate_id")
                if cid:
                    holds[cid] = e.get("meta", {}).get("verdict")
        plan = sustained_plan(events, summary, judging_mode=mode,
                              candidate_source=source, size=args.interval,
                              holds_by_candidate=holds)
    else:
        plan = plan_seconds_per_candidate(summary, judging_mode=mode,
                                          candidate_source=source)
    data = summary.as_dict()

    print("블록: " + ", ".join(f"{d}:{e}" for d, e in pilots))
    print(f"판정 방식: {mode or '적혀 있지 않음'} / "
          f"후보 출처: {source or '적혀 있지 않음'}")
    print(f"세션 {summary.sessions}개 "
          f"(온전 {summary.complete_sessions}, 끊김 {summary.incomplete_sessions}, "
          f"판정이 든 것 {summary.sessions_with_judgements})")
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
    if args.sustained:
        # **세션 기준 판정을 그대로 찍으면 틀린 말이 된다.** 지속 판정은 세션이
        # 하나인 것이 정상이고, 표본 조건은 구간이 본다.
        print(f"표본 조건(구간 기준) = {plan.get('sample_ok', False)}"
              f"  — 세션 기준 timing_usable은 지속 판정에 안 쓴다")
    else:
        print(f"timing_usable = {summary.timing_usable}")

    if plan["status"] == "not_unaided_human":
        # **속도로는 도움 여부를 알 수 없다.** 명시적으로 적힌 것만 믿는다.
        print()
        print("  ！ 계획값을 내지 않습니다: " + plan["reason"])
        print(f"  ({plan.get('basis', '')})")
        print("  이 기록은 계측·화면 흐름 확인용(진단)으로만 씁니다.")
    elif plan["status"] == "implausible_for_human_judging":
        # **자동 클릭 시간이 N으로 흘러가면 안 된다.**
        print()
        print("  ！ 사람이 판정한 기록으로 보이지 않습니다. N을 계산하지 않습니다.")
        for warning in plan["provenance_warnings"]:
            print(f"    - {warning}")
        print(f"  ({plan.get('basis', '')})")
    elif plan["status"] != "ok":
        print(f"  → N을 계산하지 않습니다: {plan.get('reason', plan['status'])}")
        # **`.get`으로 읽는다.** 상태마다 담기는 항목이 달라, 없는 키를 꺼내면
        # 사람이 판정을 끝낸 **직후에** 보고서가 죽는다. 실제로 두 번 그랬다
        # (timing4 이름 불일치, timing5 `p75_basis` 누락).
        if plan.get("minimum_sessions") is not None:
            print(f"  최소 기준: 온전한 세션 {plan['minimum_sessions']}개, "
                  f"판정 후보 {plan['minimum_candidates']}개")
        if plan.get("minimum_intervals") is not None:
            print(f"  최소 기준: 완성된 구간 {plan['minimum_intervals']}개")
        if plan.get("minimum_basis"):
            print(f"  ({plan['minimum_basis']})")
    else:
        print(f"  평균 {plan['mean_seconds']:.2f}초 / "
              f"중앙값 {plan['median_seconds']:.2f}초")
        print(f"  P75 {plan['p75_seconds']:.2f}초 — {plan.get('p75_basis', '')}")
        print(f"  s_plan {plan['s_plan_seconds']:.2f}초 — "
              f"{plan.get('s_plan_basis', '')}")

        if plan["adoption_blocked"]:
            print()
            print("  ！ " + plan["adoption_note"])

        if args.datasets and args.total_minutes:
            # **사람이 검토했다고 말하기 전에는 N을 내지 않는다.**
            # 속도 증가와 정상 anchor 오탐은 기준이 사전 등록돼 있지 않아
            # 자동으로 판정할 수 없다(docs/timing4-realistic-protocol.md).
            if not args.reviewed:
                print()
                print("  N을 내지 않습니다 — 속도 변화와 anchor 결과를 사람이 "
                      "검토해야 합니다.")
                print("  위 세션별 평균과 anchor 줄을 보고, 받아들일 만하면 "
                      "--reviewed 를 붙이세요.")
                return 0
            factor = args.safety_factor
            if plan["adoption_blocked"] and not factor:
                print()
                print("  N을 내지 않습니다 — 하한을 그대로 넣으면 N이 과대해집니다.")
                print("  --safety-factor 를 명시하면 s_plan × 계수로 계산합니다.")
                return 0
            planned = plan["s_plan_seconds"] * (factor or 1.0)
            if factor:
                print()
                print(f"  안전계수 {factor}배 → 후보당 {planned:.2f}초로 계획")
            if args.sustained and args.sustained_block:
                # **블록을 반복하는 것만 외삽한다.** 한 시간을 쉬지 않고
                # 같은 속도로 간다고 가정하지 않는다.
                got = capacity_from_blocks(args.total_minutes * 60,
                                           args.datasets,
                                           args.sustained_block, planned)
                print_capacity(got, args.datasets, args.total_minutes)
                n = got["n_capacity"]
                if got["adoption_blocked"]:
                    # **여기서 멈춘다.** 시간이 된다는 것과 채택해도 된다는
                    # 것은 다른 말이다.
                    print()
                    print("  이 조합은 지금 채택할 수 없습니다. Δ 선택지도 "
                          "내지 않습니다 —")
                    print("  Δ는 N_required를 정하려고 고르는 것이지 "
                          "N_capacity에 맞추는 것이 아닙니다.")
                    return 0
            else:
                n = budget_from_pilot(args.total_minutes * 60, args.datasets,
                                      planned)
                print()
                print(f"  D={args.datasets}, T={args.total_minutes}분 → "
                      f"N_capacity={n} (데이터셋마다, 총 "
                      f"{None if n is None else n * args.datasets}건)")
            print()
            print("  Δ 선택지 — **고르는 것은 사용자다**. 아래 수는 "
                  "N_capacity에 맞춘 예시일 뿐이고,")
            print("  Δ를 정하는 근거는 사업적 최소 기준이지 처리 용량이 아니다:")
            for row in delta_scenarios(n):
                print(f"    {row['name']}: {row['rule']} → {row['delta']} "
                      f"({row['note']})")
        else:
            print()
            print("  D와 T를 주면 N_capacity를 계산합니다 "
                  "(--datasets, --total-minutes). 지금은 둘 다 미정입니다.")
            print("  **N_capacity는 처리 가능량이지 필요한 표본 크기가 "
                  "아닙니다** (docs/capacity-vs-sample-size.md).")

        if args.capacity_table and args.sustained_block:
            print_capacity_table(args.sustained_block,
                                 plan["s_plan_seconds"])

    if args.sustained and plan.get("intervals"):
        print()
        print(f"구간별 ({plan['interval_size']}건씩, 판정 순서로 끊음):")
        for row in plan["intervals"]:
            mark = "" if row["complete"] else "  ← 반쪽 구간, 비교에서 뺌"
            mean = row["mean_seconds"]
            print(f"  {row['first']:>3}~{row['last']:<3} {row['judged']:>3}건  "
                  f"{mean:5.2f}초  보류 {row['holds']}{mark}"
                  if mean is not None else
                  f"  {row['first']:>3}~{row['last']:<3} 판정 없음{mark}")
        if "change_pct" in plan:
            print(f"  첫 구간 대비 마지막 구간: {plan['change_pct']:+.1f}%")
        print(f"  완성된 구간 {plan.get('complete_intervals', 0)}개 "
              f"(최소 {plan.get('minimum_intervals', '?')})")

    # ── 세션별 속도와 anchor ────────────────────────────────────────────────
    good = [r for r in summary.session_reports if r.complete]
    if len(good) > 1:
        print()
        print("세션별 후보당 평균 (첫 세션 대 마지막 세션을 반드시 본다):")
        means = []
        for r in good:
            times = [c.active_seconds for c in summary.per_candidate
                     if c.session_id == r.session_id and c.judged]
            if not times:
                continue
            mean = sum(times) / len(times)
            means.append(mean)
            print(f"  {r.session_id[:12]}: {len(times):2d}건, {mean:5.2f}초")
        if len(means) > 1 and means[0]:
            change = (means[-1] - means[0]) / means[0] * 100
            print(f"  첫 세션 대비 마지막 세션: {change:+.0f}%")

    anchors = anchor_report(pilots[-1][0], pilots[-1][1])
    if anchors:
        print()
        print(f"anchor {anchors['total']}건 "
              f"(정상 {anchors['clean_agree']}/{anchors['clean']}, "
              f"오류 {anchors['error_agree']}/{anchors['error']})")
        print(f"  status={anchors['status']}")
        print(f"  {anchors['note']}")
        print("  **실제 후보에는 정답이 없어 accuracy를 계산하지 않습니다.**")

    if args.out:
        Path(args.out).write_text(
            json.dumps({"pilots": [f"{d}:{e}" for d, e in pilots],
                        "judging_mode": mode,
                        "summary": data, "plan": plan,
                        "anchors": anchors},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print()
        print(f"저장했습니다: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
