"""`N_required` 사전 계획 — 검정력 민감도 표 (docs/n-required-plan.md).

**최종 N 하나를 내지 않는다.** D·N·오류 비율·Δ·이미지 내 묶임 수준을 늘어놓고
칸마다 추정 검정력과 몬테카를로 오차, 처리 용량·근거 범위를 같이 찍는다.

**시간으로 표본 크기를 정하지 않는다.** 용량 열은 "그 N을 시간 안에 볼 수
있는가"만 말한다. 검정력 열은 "그 N으로 Δ를 잡아낼 수 있는가"를 말한다. 둘은
다른 질문이고 `N_final`은 둘이 다 맞을 때만 후보가 된다 — 그것도 사용자가
정한다.

**이 표로 권고하지 않는다.** 시나리오 파일의 순위 품질과 후보 풀 크기는 근거가
없는 민감도 예시라, 모든 칸이 `official=False`로 나오는 것이 정상이다.

    ./experiment/venv/Scripts/python.exe experiment/power_report.py --estimate-only
    ./experiment/venv/Scripts/python.exe experiment/power_report.py --total-minutes 60 180
"""
import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# 판정 직후에 보고서가 콘솔 인코딩으로 죽은 일이 있었다(timing_report.py).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from evaluation.activity import capacity_from_blocks, evidence_range
from evaluation.bootstrap import paired_cluster_bootstrap
from evaluation.planning import (BASELINE, COMPARISON_POWERS, METHOD,
                                 MIN_OFFICIAL_BOOTSTRAP,
                                 MIN_OFFICIAL_ITERATIONS, ONE_SIDED_ALPHA,
                                 UNSUPPORTED, PlanningScenario, build_world,
                                 delta_options, power_against_targets,
                                 simulate_power, strength_from_auc,
                                 validate_scenario)

HERE = Path(__file__).resolve().parent
DEFAULT_SCENARIOS = HERE / "planning_scenarios.json"


def _mean_size(dist: dict) -> float:
    total = sum(float(w) for w in dist.values())
    return sum(int(k) * float(w) for k, w in dist.items()) / total


def _weakest(*sources: str) -> str:
    """파생값은 **가장 약한 근거**를 따른다."""
    return UNSUPPORTED if UNSUPPORTED in sources else sources[0]


def scenarios_from_grid(grid: dict, datasets=None, budgets=None) -> list[dict]:
    """격자의 각 칸을 `PlanningScenario`로 만든다. **값마다 근거를 붙인다.**"""
    ds_values = datasets or grid["datasets"]["values"]
    n_values = budgets or grid["budgets"]["values"]
    ratio = grid["pool_to_budget_ratio"]
    cpi = grid["candidates_per_image"]
    cells = []
    for prev in grid["error_prevalence"]:
      for dep in grid["dependence"]:
        for ranking in grid["ranking"]:
            for d in ds_values:
                for n in n_values:
                    pool = math.ceil(n * ratio["value"])
                    images = max(1, min(pool, round(pool / _mean_size(cpi["value"]))))
                    name = f"D{d}_N{n}_p{prev['value']}_{dep['name']}_{ranking['name']}"
                    sources = {
                        "dataset_count": grid["datasets"]["source"],
                        "candidates_per_dataset": _weakest(ratio["source"],
                                                           grid["budgets"]["source"]),
                        "images_per_dataset": _weakest(ratio["source"], cpi["source"]),
                        "candidates_per_image": cpi["source"],
                        "duplicates_per_unique_error":
                            dep["sources"]["duplicates_per_unique_error"],
                        "error_prevalence": prev["source"],
                        "image_error_concentration":
                            dep["sources"]["image_error_concentration"],
                        "aida_ranking_strength": ranking["source"],
                        "baseline_ranking_strength": ranking["source"],
                        "hold_rate": grid["hold_rate"]["source"],
                        "delta": grid["delta"]["source"],
                        "alpha": grid["alpha"]["source"],
                        "target_power": grid["target_power"]["source"],
                        "iterations": grid["iterations"]["source"],
                        "bootstrap_iterations": grid["bootstrap_iterations"]["source"],
                        "random_seed": grid["random_seed"]["source"],
                    }
                    scenario = PlanningScenario(
                        name=name, dataset_count=d, candidates_per_dataset=pool,
                        images_per_dataset=images,
                        candidates_per_image=cpi["value"],
                        duplicates_per_unique_error=dep["duplicates_per_unique_error"],
                        error_prevalence=prev["value"],
                        image_error_concentration=dep["image_error_concentration"],
                        aida_ranking_strength=strength_from_auc(ranking["aida_auc"]),
                        baseline_ranking_strength=strength_from_auc(ranking["baseline_auc"]),
                        hold_rate=grid["hold_rate"]["value"],
                        delta=grid["delta"]["value"],
                        alpha=grid["alpha"]["value"],
                        target_power=grid["target_power"]["value"],
                        iterations=grid["iterations"]["value"],
                        bootstrap_iterations=grid["bootstrap_iterations"]["value"],
                        random_seed=grid["random_seed"]["value"],
                        sources=sources)
                    validate_scenario(scenario)
                    cells.append({"scenario": scenario, "budget": n,
                                  "prevalence": prev["value"],
                                  "dependence": dep["name"],
                                  "ranking": ranking["name"],
                                  "aida_auc": ranking["aida_auc"],
                                  "baseline_auc": ranking["baseline_auc"]})
    return cells


def nominal_unique_errors(pool: int, prevalence: float, duplicates: dict) -> float:
    """설정값만으로 계산한 풀 안의 고유 오류 수 — **상한 쪽 참고값이 아니다.**

    `풀 × 오류 비율 ÷ 평균 중복`. 그런데 중복 묶음은 **같은 이미지 안에서만**
    생기므로, 이미지 대부분이 후보 1건이면 설정한 중복이 만들어지지 않는다. 그러면
    실제 고유 오류는 이 값보다 **많다.** 표의 `!` 표시는 이 값이 아니라 시뮬레이션이
    실제로 만든 수(`mean_pool_unique_errors`)로 한다 — 처음엔 이 값으로 표시해서
    Δ가 어렵다고 잘못 찍었다.
    """
    return pool * prevalence / _mean_size(duplicates)


def capacity_columns(datasets: int, budget: int, block: int, s_plan: float,
                     totals: list[float] | None) -> dict:
    """그 N을 **시간 안에 볼 수 있는가**와 근거 범위. 검정력과 다른 질문이다."""
    blocks_per_dataset = math.ceil(budget / block)
    blocks_total = blocks_per_dataset * datasets
    out = {
        "blocks_per_dataset": blocks_per_dataset,
        "blocks_total": blocks_total,
        "per_dataset_evidence": ("observed" if blocks_per_dataset <= 1
                                 else evidence_range(blocks_per_dataset)),
        "evidence": evidence_range(blocks_total),
        "required_active_minutes": round(budget * datasets * s_plan / 60, 1),
        # N_capacity가 N 이상이 되는 가장 작은 활동 시간. 블록 단위로 올린다.
        "min_active_minutes_for_capacity": round(blocks_total * block * s_plan / 60, 1),
        "capacity": {},
    }
    for total in totals or []:
        got = capacity_from_blocks(total * 60, datasets, block, s_plan)
        cap = got["n_capacity"] or 0
        out["capacity"][str(total)] = {"n_capacity": cap, "meets": cap >= budget}
    return out


def _run_cell(payload: dict) -> dict:
    """작업자 프로세스에서 칸 하나를 돈다. **집계는 실제 함수가 한다.**"""
    result = simulate_power(payload["scenario"], payload["budget"],
                            iterations=payload["iterations"],
                            bootstrap_iterations=payload["bootstrap_iterations"],
                            seed=payload["seed"], deltas=payload["deltas"])
    return {"key": payload["key"], "result": result}


def _calibrate_seconds_per_candidate_iteration() -> float:
    """이 기계에서 재표집 한 번이 후보 하나당 몇 초인가. 추정 시간에만 쓴다."""
    probe = PlanningScenario(
        name="calibration", dataset_count=2, candidates_per_dataset=480,
        images_per_dataset=300, candidates_per_image={"1": 38, "2": 10, "3": 8},
        duplicates_per_unique_error={"1": 1.0}, error_prevalence=0.1,
        image_error_concentration=0.0, aida_ranking_strength=1.0,
        baseline_ranking_strength=0.5, hold_rate=0.0, delta=None, alpha=0.05,
        target_power=None, iterations=1, bootstrap_iterations=1, random_seed=1,
        sources={})
    import random
    adjudications, rankings = build_world(probe, random.Random(1))
    started = time.perf_counter()
    paired_cluster_bootstrap(adjudications, rankings, METHOD, BASELINE,
                             budget=240, iterations=6, seed=1)
    return (time.perf_counter() - started) / (6 * len(adjudications))


def _fmt_power(entry: dict | None, flag: bool) -> str:
    if entry is None:
        return "     -      "
    mark = "!" if flag else " "
    return f"{entry['power']:.2f}±{entry['monte_carlo_se']:.2f}{mark}"


def main() -> int:
    parser = argparse.ArgumentParser(description="N_required 사전 계획 — 검정력 민감도 표")
    parser.add_argument("--scenarios", default=str(DEFAULT_SCENARIOS))
    parser.add_argument("--datasets", type=int, nargs="+",
                        help="격자의 D를 덮어쓴다 (예: 1 3)")
    parser.add_argument("--budgets", type=int, nargs="+",
                        help="격자의 N을 덮어쓴다 (예: 120 360)")
    parser.add_argument("--iterations", type=int, help="몬테카를로 복제 수")
    parser.add_argument("--bootstrap", type=int, help="복제 하나당 재표집 수")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--total-minutes", type=float, nargs="*",
                        help="용량을 볼 활동 시간 상한 T(분) 후보. **정한 값이 아니다**")
    parser.add_argument("--estimate-only", action="store_true",
                        help="예상 소요 시간만 찍고 끝낸다")
    parser.add_argument("--max-minutes", type=float, default=30.0,
                        help="예상 시간이 이보다 길면 돌리지 않는다")
    parser.add_argument("--allow-long", action="store_true",
                        help="예상 시간을 보고 사용자가 승인했을 때만 붙인다")
    parser.add_argument("--out", help="결과 JSON을 저장할 경로")
    args = parser.parse_args()

    raw = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    grid = raw["grid"]
    cells = scenarios_from_grid(grid, args.datasets, args.budgets)
    reps = args.iterations or grid["iterations"]["value"]
    boots = args.bootstrap or grid["bootstrap_iterations"]["value"]
    block = grid["block_size"]["value"]
    s_plan = grid["s_plan_seconds"]["value"]

    unit = _calibrate_seconds_per_candidate_iteration()
    serial = sum(reps * (boots + 3) * c["scenario"].dataset_count
                 * c["scenario"].candidates_per_dataset * unit for c in cells)
    workers = max(1, args.workers)
    wall = serial / min(workers, len(cells)) * 1.2 / 60
    print(f"칸 {len(cells)}개 · 복제 {reps} · 재표집 {boots} · 작업자 {workers}")
    print(f"예상 소요: 약 {wall:.1f}분 (직렬이면 {serial / 60:.0f}분). "
          "CPU만 쓴다 — GPU·다운로드·유료 서비스 없음.")
    if reps < MIN_OFFICIAL_ITERATIONS or boots < MIN_OFFICIAL_BOOTSTRAP:
        print(f"  반복이 공식 최소({MIN_OFFICIAL_ITERATIONS}/{MIN_OFFICIAL_BOOTSTRAP})"
              "에 못 미친다 — 모든 칸이 too_few_iterations로 나온다. 탐색용이다.")
    if args.estimate_only:
        return 0
    if wall > args.max_minutes and not args.allow_long:
        print(f"  예상 {wall:.0f}분이 상한 {args.max_minutes:.0f}분을 넘어 돌리지 "
              "않습니다. 사용자가 시간을 보고 승인하면 --allow-long을 붙입니다.")
        return 2

    payloads = []
    for i, cell in enumerate(cells):
        s = cell["scenario"]
        deltas = [row["delta"] for row in delta_options(cell["budget"])
                  if row["delta"] is not None]
        payloads.append({"key": i, "scenario": s, "budget": cell["budget"],
                         "iterations": reps, "bootstrap_iterations": boots,
                         "seed": f"{s.random_seed}|{s.name}", "deltas": deltas,
                         "cost": s.dataset_count * s.candidates_per_dataset})
    payloads.sort(key=lambda p: -p["cost"])

    started = time.time()
    results: dict[int, dict] = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_cell, p) for p in payloads]
        for done, future in enumerate(as_completed(futures), 1):
            got = future.result()
            results[got["key"]] = got["result"]
            if done % max(1, len(futures) // 10) == 0 or done == len(futures):
                print(f"  {done}/{len(futures)} 칸 ({(time.time() - started) / 60:.1f}분)",
                      flush=True)

    rows = []
    for i, cell in enumerate(cells):
        s = cell["scenario"]
        result = results[i]
        cap = capacity_columns(s.dataset_count, cell["budget"], block, s_plan,
                               args.total_minutes)
        expected = result["mean_pool_unique_errors"]
        nominal = nominal_unique_errors(s.candidates_per_dataset, s.error_prevalence,
                                        s.duplicates_per_unique_error)
        deltas = []
        options = [o for o in delta_options(cell["budget"]) if o["delta"] is not None]
        for option, entry in zip(options, result["by_delta"]):
            deltas.append({"name": option["name"], "rule": option["rule"],
                           "delta": entry["delta"], "power": entry["power"],
                           "monte_carlo_se": entry["monte_carlo_se"],
                           "exceeds_expected_errors": entry["delta"] > expected,
                           **power_against_targets(entry["power"])})
        rows.append({"prevalence": cell["prevalence"], "dependence": cell["dependence"],
                     "ranking": cell["ranking"], "aida_auc": cell["aida_auc"],
                     "baseline_auc": cell["baseline_auc"],
                     "datasets": s.dataset_count, "budget": cell["budget"],
                     "pool": s.candidates_per_dataset, "images": s.images_per_dataset,
                     "pool_unique_errors_per_dataset": round(expected, 1),
                     "nominal_unique_errors_per_dataset": round(nominal, 1),
                     "mean_aida_unique_errors": round(result["mean_method_unique_errors"], 2),
                     "mean_baseline_unique_errors": round(result["mean_baseline_unique_errors"], 2),
                     "status": result["status"], "official_scenario": s.official,
                     "unsupported_fields": s.unsupported_fields,
                     "deltas": deltas, **cap})

    print()
    print("검정력 민감도 표 — **설계 민감도 분석이지 N_required가 아니다**")
    print(f"  판정 규칙: 짝지은 차이 95% 구간 하한 > Δ (한쪽 유의수준 {ONE_SIDED_ALPHA})")
    print("  칸: 추정 검정력 ± 몬테카를로 표준오차.  ! = Δ가 풀에 실제로 만들어진 고유 오류 수(평균)보다 큼")
    print("  목표 검정력은 미정 — 0.80·0.90은 비교로만 본다")
    for prev in grid["error_prevalence"]:
      for dep in grid["dependence"]:
        for ranking in grid["ranking"]:
            print()
            print(f"■ 오류 비율 {prev['value']} ({prev['source']}) · "
                  f"묶임 {dep['name']} · 순위 AUC AIDA {ranking['aida_auc']} / "
                  f"기준선 {ranking['baseline_auc']} ({ranking['source']})")
            print("   D    N  블록/DS 전체  근거(DS/전체)          active분  "
                  "풀오류 E[AIDA] E[기준]  A(Δ=1)      B(5%)       C(10%)")
            for row in rows:
                if (row["prevalence"] != prev["value"] or row["dependence"] != dep["name"]
                        or row["ranking"] != ranking["name"]):
                    continue
                by = {d["name"]: d for d in row["deltas"]}
                ev = f"{row['per_dataset_evidence']}/{row['evidence']}"
                print(f"  {row['datasets']:>2} {row['budget']:>4}  {row['blocks_per_dataset']:>6} "
                      f"{row['blocks_total']:>4}  {ev:<22} {row['required_active_minutes']:>7} "
                      f"{row['pool_unique_errors_per_dataset']:>6} "
                      f"{row['mean_aida_unique_errors']:>7} {row['mean_baseline_unique_errors']:>7}  "
                      + "  ".join(_fmt_power(by.get(k), bool(by.get(k)) and by[k]["exceeds_expected_errors"])
                                  for k in ("A", "B", "C")))
    print()
    print("Δ 값 (N별): " + ", ".join(
        f"N={n}: " + "/".join(str(o["delta"]) for o in delta_options(n) if o["delta"] is not None)
        for n in sorted({r["budget"] for r in rows})))

    if args.total_minutes:
        print()
        print("처리 용량을 넘는 조합 (T는 **활동 판정 시간** 후보이고 정한 값이 아니다):")
        for total in args.total_minutes:
            over = sorted({(r["datasets"], r["budget"]) for r in rows
                           if not r["capacity"][str(total)]["meets"]})
            print(f"  T={total:g}분: " + (", ".join(f"D{d}·N{n}" for d, n in over) or "없음"))
    else:
        print()
        print("T를 주지 않았다. 각 (D, N)을 볼 수 있는 최소 활동 시간:")
        for d, n, minutes in sorted({(r["datasets"], r["budget"],
                                      r["min_active_minutes_for_capacity"]) for r in rows}):
            print(f"  D{d}·N{n}: {minutes}분")

    unofficial = sorted({f for r in rows for f in r["unsupported_fields"]})
    print()
    print("공식 결론에 못 쓰는 이유:")
    if unofficial:
        print(f"  근거 없는 가정: {', '.join(unofficial)}")
    if any(r["status"] == "too_few_iterations" for r in rows):
        print(f"  반복 부족: 복제 {reps}/재표집 {boots} (최소 "
              f"{MIN_OFFICIAL_ITERATIONS}/{MIN_OFFICIAL_BOOTSTRAP})")
    print("  이 표로 N_required·N_final·Δ를 정하지 않고, 유리한 칸 하나를 권고하지 않는다.")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "scenarios_file": str(Path(args.scenarios).name),
            "iterations": reps, "bootstrap_iterations": boots,
            "comparison_powers": list(COMPARISON_POWERS),
            "n_required_status": "undetermined", "n_final_status": "undetermined",
            "delta_status": "undetermined", "rows": rows},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장했습니다: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
