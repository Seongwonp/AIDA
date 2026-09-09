"""집계 기준 구현 검사 (docs/evaluation-protocol.md).

**기대값은 손으로 세어 리터럴로 적는다.** 구현으로 다시 계산하면 틀린 구현도
같이 통과한다. 계산 과정은 `tests/fixtures/README.md`의 표에 있다.
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from evaluation import (Judgement, ValidationError, equal_weight_overall,  # noqa: E402
                        paired_cluster_bootstrap, paired_difference,
                        rank_candidates, summarise, validate)
from evaluation.bootstrap import verdict_against_delta  # noqa: E402
from evaluation.ranking import top_n  # noqa: E402


def j(candidate_id, *, dataset="ds1", image="img1", method="aida", rank=1,
      suspicion="width", severity=0.5, verdict=None, label_index=None,
      unique_error_id=None, group_id=None) -> Judgement:
    return Judgement(dataset_id=dataset, image_id=image, method=method,
                     candidate_id=candidate_id, rank=rank, suspicion=suspicion,
                     severity=severity, verdict=verdict, label_index=label_index,
                     unique_error_id=unique_error_id, group_id=group_id)


# --- A. 중복 지목 -------------------------------------------------------------

def test_two_candidates_one_real_error():
    """같은 라벨을 width와 scale이 지목 → 후보 2, 고유 오류 1."""
    rows = [j("c1", suspicion="width", verdict="hit", label_index=0),
            j("c2", suspicion="scale", verdict="hit", label_index=0)]
    s = summarise(rows)
    assert s.judged == 2
    assert s.hits == 2                 # 후보는 둘
    assert s.unique_errors == 1        # 오류는 하나
    assert s.precision == 1.0


# --- B·C. 빈 것 ---------------------------------------------------------------

def test_no_candidates_precision_is_undefined():
    s = summarise([])
    assert s.in_budget == 0 and s.judged == 0
    assert s.precision is None, "0.0이 아니라 정의 없음이다"
    assert s.hold_rate is None


def test_candidates_but_nothing_judged():
    rows = [j("c1"), j("c2"), j("c3")]
    s = summarise(rows)
    assert s.in_budget == 3 and s.judged == 0
    assert s.precision is None and s.hold_rate is None


# --- D·E. 보류 ----------------------------------------------------------------

def test_all_holds_consume_budget_but_not_precision():
    rows = [j(f"c{i}", verdict="hold") for i in (1, 2, 3)]
    s = summarise(rows)
    assert s.judged == 3               # 시간을 썼다
    assert s.holds == 3
    assert s.precision is None         # 결정된 것이 없다
    assert s.hold_rate == 1.0


def test_partial_holds():
    rows = [j("c1", verdict="hit", label_index=0),
            j("c2", verdict="miss"),
            j("c3", verdict="hold"),
            j("c4", verdict="hit", label_index=0)]
    s = summarise(rows)
    assert s.judged == 4
    assert s.holds == 1
    assert s.hits == 2
    assert s.unique_errors == 1
    assert s.precision == 2 / 3        # 보류는 분모에서 빠진다
    assert s.hold_rate == 0.25


# --- F. 동점 ------------------------------------------------------------------

def test_severity_ties_break_by_image_then_candidate():
    rows = [j("cB", image="imgB", severity=0.5),
            j("cA", image="imgA", severity=0.5),
            j("cC", image="imgA", severity=0.5)]
    assert [r.candidate_id for r in rank_candidates(rows)] == ["cA", "cC", "cB"]
    assert [r.candidate_id for r in top_n(rows, 2)] == ["cA", "cC"]


def test_input_order_does_not_change_the_result():
    rows = [j("cB", image="imgB", severity=0.5),
            j("cA", image="imgA", severity=0.5),
            j("cC", image="imgA", severity=0.5)]
    assert rank_candidates(rows) == rank_candidates(list(reversed(rows)))


def test_missing_candidate_ties_are_deterministic():
    """누락 후보도 같은 규칙으로 자른다 — 좌표가 아니라 id 순이다."""
    rows = [j("m2", image="i1", severity=0.9, unique_error_id="e2"),
            j("m1", image="i1", severity=0.9, unique_error_id="e1")]
    assert [r.candidate_id for r in rank_candidates(rows)] == ["m1", "m2"]


# --- 여러 후보가 한 이미지에 ---------------------------------------------------

def test_many_candidates_in_one_image_are_one_cluster():
    rows = [j("c1"), j("c2"), j("c3")]
    assert len({r.cluster for r in rows}) == 1


def test_group_id_joins_several_images():
    """연속 장면은 이미지가 달라도 한 묶음이다."""
    rows = [j("c1", image="i1", group_id="scene7"),
            j("c2", image="i2", group_id="scene7")]
    assert len({r.cluster for r in rows}) == 1


# --- 검증 ---------------------------------------------------------------------

def test_hit_without_unique_error_id_is_rejected():
    """조용히 후보 id로 대신하면 고유 오류 수가 부풀려진다."""
    with pytest.raises(ValidationError, match="고유 오류 id"):
        validate([j("c1", verdict="hit")])


def test_hit_with_label_index_is_fine():
    validate([j("c1", verdict="hit", label_index=3)])


def test_unknown_verdict_is_rejected():
    with pytest.raises(ValidationError, match="판정"):
        validate([j("c1", verdict="maybe")])


def test_duplicate_candidate_is_rejected():
    with pytest.raises(ValidationError, match="두 번"):
        validate([j("c1"), j("c1")])


# --- G. 데이터셋 동등 가중 ------------------------------------------------------

def _two_datasets() -> list[Judgement]:
    rows: list[Judgement] = []
    # ds_small: AIDA 고유 오류 2, 기준선 0 → 차이 +2
    for i in (1, 2):
        rows.append(j(f"s{i}", dataset="ds_small", image=f"si{i}", method="aida",
                      verdict="hit", unique_error_id=f"se{i}"))
        rows.append(j(f"s{i}", dataset="ds_small", image=f"si{i}", method="base",
                      verdict="miss"))
    # ds_big: AIDA 4, 기준선 3 → 차이 +1
    for i in range(1, 5):
        rows.append(j(f"b{i}", dataset="ds_big", image=f"bi{i}", method="aida",
                      verdict="hit", unique_error_id=f"be{i}"))
    for i in range(1, 4):
        rows.append(j(f"b{i}", dataset="ds_big", image=f"bi{i}", method="base",
                      verdict="hit", unique_error_id=f"be{i}"))
    rows.append(j("b4", dataset="ds_big", image="bi4", method="base", verdict="miss"))
    return rows


def test_equal_weight_not_candidate_weight():
    r = equal_weight_overall(_two_datasets(), "aida", "base")
    assert r["per_dataset"]["ds_small"]["difference"] == 2
    assert r["per_dataset"]["ds_big"]["difference"] == 1
    assert r["overall_difference"] == 1.5     # 후보 가중이면 1.2였다


# --- H. 개별 구간은 겹치지만 짝지은 차이는 0을 안 걸친다 --------------------------

def _paired_rows() -> list[Judgement]:
    """이미지 4장, 각 이미지에서 AIDA가 정확히 1개 더 찾는다."""
    rows: list[Judgement] = []
    for n in range(1, 5):
        img = f"img{n}"
        for k in range(n):              # AIDA: n개
            rows.append(j(f"a{n}_{k}", image=img, method="aida", verdict="hit",
                          unique_error_id=f"{img}/e{k}"))
        for k in range(n - 1):          # 기준선: n-1개
            rows.append(j(f"b{n}_{k}", image=img, method="base", verdict="hit",
                          unique_error_id=f"{img}/e{k}"))
    return rows


def test_observed_paired_difference():
    assert paired_difference(_paired_rows(), "aida", "base")["difference"] == 4


def test_paired_bootstrap_interval_excludes_zero():
    r = paired_cluster_bootstrap(_paired_rows(), "aida", "base",
                                 iterations=200, seed=1)
    assert r["observed_difference"] == 4
    # 각 묶음의 차이가 항상 +1이라 어떤 재표본에서도 합은 4다.
    assert r["ci_low"] == 4 and r["ci_high"] == 4
    assert r["ci_low"] > 0, "0을 걸치면 안 된다"


def test_bootstrap_resamples_clusters_not_candidates():
    """묶음이 4개면 재표본에도 묶음이 4개다 — 후보 단위로 뽑으면 구간이 좁아진다."""
    r = paired_cluster_bootstrap(_paired_rows(), "aida", "base",
                                 iterations=10, seed=1)
    assert r["clusters"] == 4


def test_same_seed_same_result():
    kw = {"iterations": 50, "seed": 7}
    a = paired_cluster_bootstrap(_paired_rows(), "aida", "base", **kw)
    b = paired_cluster_bootstrap(_paired_rows(), "aida", "base", **kw)
    assert a == b


def test_result_records_iterations_and_seed():
    """이것 없이는 결과를 다시 만들 수 없다."""
    r = paired_cluster_bootstrap(_paired_rows(), "aida", "base",
                                 iterations=33, seed=99)
    assert r["iterations"] == 33 and r["seed"] == 99


# --- Δ가 TBD인 동안은 판정하지 않는다 --------------------------------------------

def test_no_verdict_while_delta_is_tbd():
    r = {"ci_low": 3.0, "ci_high": 5.0}
    assert verdict_against_delta(r, None) == "미정"


def test_verdict_uses_the_lower_bound():
    r = {"ci_low": 3.0, "ci_high": 5.0}
    assert verdict_against_delta(r, 2.0) == "성공"      # 하한이 Δ를 넘는다
    assert verdict_against_delta(r, 4.0) == "불확실"    # 구간이 Δ를 걸친다
    assert verdict_against_delta(r, 6.0) == "실패"      # 상한이 Δ 아래다
