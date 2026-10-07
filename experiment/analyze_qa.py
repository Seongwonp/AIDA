"""Q-A 최종 분석 경로 (연구용). **require_judged_top_n=True를 강제**하고, 분석 입력이 묶음의 coverage
설정·입력 지문과 다르면 중단한다.

사용법:
  python analyze_qa.py --export labelled.json --budget 90 --iterations 2000 --seed 42 \
      --methods aida all_label_iou all_label_objectlab --out result.json

- 내보내기는 `GET .../export?methods=...&scope=labelled_candidates&mode=candidate_generation_included`
  (기본 판정자 primary). 다른 판정자의 내보내기는 `--adjudicator`로 명시할 때만 받는다 — 민감도 분석용.
- 비교는 (기준선 − aida)의 고유 오류 수 차이, 이미지·기록 묶음 짝지은 부트스트랩. Δ는 없다 —
  성공·실패를 적지 않는다.
- 출처 관문: 내보내기의 `provenance`가 `synthetic_dryrun`이거나, dataset_id·evaluation_id가 출처 등록부
  (`experiment/planning_evidence/dataset_provenance_registry.json`)에 연습·출처 손상으로 적혀 있으면 중단한다.
- 이 경로가 보장하는 것은 **고정 재표본의 판정 누락이 없다**는 것뿐이다. 구간의 포함률·통계적 타당성은
  검증하지 않는다(docs/unjudged-bootstrap-review-2026-09-27.md).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluation.bootstrap import paired_cluster_bootstrap  # noqa: E402
from evaluation.coverage import check_export_against_coverage, unjudged_in_fixed_resamples  # noqa: E402
from evaluation.importer import load_export  # noqa: E402
from evaluation.provenance import assert_official_input  # noqa: E402
from evaluation.schema import ValidationError  # noqa: E402
from evaluation.summary import summarise  # noqa: E402

AIDA = "aida"


def analyse(export: dict, budget: int, iterations: int, seed: int, methods: list[str],
            adjudicator: str = "primary") -> dict:
    # 합성 드라이런(synthetic_dryrun)과 출처 등록부의 연습·출처 손상 자료(practice1 등)는 공식 분석 입력이 아니다.
    assert_official_input(export, "내보내기")
    if export.get("adjudicator", "primary") != adjudicator:
        raise ValidationError(
            f"내보내기의 판정자({export.get('adjudicator', 'primary')})가 분석이 요구한 판정자({adjudicator})와 다르다")
    if export.get("requested_scope") != "labelled_candidates" or \
            export.get("comparison_mode") != "candidate_generation_included":
        raise ValidationError("1차 분석은 labelled_candidates 층·candidate_generation_included 모드의 내보내기만 받는다")
    settings = check_export_against_coverage(export, budget, iterations, seed, methods)
    facts, ranks = load_export(export, require_comparison=True)
    exported_methods = {r.method for r in ranks}
    if set(methods) - exported_methods:
        raise ValidationError(f"내보내기에 없는 방법이 있다: {sorted(set(methods) - exported_methods)}")
    for method in methods:
        observed = summarise(facts, ranks, method, budget)
        if observed.in_budget != observed.judged:
            raise ValidationError(f"원래 표본의 '{method}' 상위 N에 미판정 후보가 있다")
    missing = unjudged_in_fixed_resamples(facts, ranks, methods, budget, iterations, seed)
    if any(missing.values()):
        raise ValidationError(
            "고정 재표본의 상위 N에 미판정 후보가 있다: " +
            ", ".join(f"{m} {len(v)}건" for m, v in missing.items() if v) +
            " — 판정을 끝내기 전에는 분석하지 않는다")
    baselines = [m for m in methods if m != AIDA]
    if AIDA not in methods or not baselines:
        raise ValidationError("aida와 기준선 하나 이상이 있어야 한다")
    out = {"settings": settings, "adjudicator": adjudicator, "difference_sign": "baseline - aida",
           "guarantee": "고정 재표본의 판정 누락이 없음을 확인했다. 구간의 포함률·통계적 타당성은 검증하지 않았다",
           "summaries": {m: summarise(facts, ranks, m, budget).as_dict() for m in methods},
           "comparisons": {}}
    for base in baselines:
        out["comparisons"][f"{base}_minus_{AIDA}"] = paired_cluster_bootstrap(
            facts, ranks, base, AIDA, budget, iterations, seed,
            require_same_candidates=False, require_judged_top_n=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Q-A 최종 분석 (연구용)")
    ap.add_argument("--export", required=True)
    ap.add_argument("--budget", type=int, required=True)
    ap.add_argument("--iterations", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--methods", nargs="+", required=True)
    ap.add_argument("--adjudicator", default="primary")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    export = json.loads(Path(a.export).read_text(encoding="utf-8"))
    try:
        result = analyse(export, a.budget, a.iterations, a.seed, a.methods, a.adjudicator)
    except ValidationError as exc:
        print(f"중단: {exc}", file=sys.stderr)
        return 2
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, c in result["comparisons"].items():
        print(f"{name}: 관측 {c['observed_difference']} 구간 [{c['ci_low']}, {c['ci_high']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
