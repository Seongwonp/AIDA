"""집계 기준 구현 검사 (docs/evaluation-protocol.md).

**기대값은 손으로 세어 리터럴로 적는다.** 구현으로 다시 계산하면 틀린 구현도
같이 통과한다. 계산 과정은 `tests/fixtures/README.md`의 표에 있다.

이 검사들이 막는 것은 "숫자가 다르다"가 아니라 **잘못된 입력이 그럴듯한 결과가
되는 것**이다.
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from evaluation import (Judgement, ValidationError, equal_weight_overall,  # noqa: E402
                        paired_cluster_bootstrap, paired_difference,
                        split_judgements, summarise, validate)
from evaluation.bootstrap import verdict_against_delta  # noqa: E402
from evaluation.ranking import rank_candidates, top_n  # noqa: E402


def j(candidate_id, *, dataset="ds1", image="img1", method="aida", rank=1,
      suspicion="width", severity=0.5, verdict=None, label_index=None,
      unique_error_id=None, group_id=None) -> Judgement:
    return Judgement(dataset_id=dataset, image_id=image, method=method,
                     candidate_id=candidate_id, rank=rank, suspicion=suspicion,
                     severity=severity, verdict=verdict, label_index=label_index,
                     unique_error_id=unique_error_id, group_id=group_id)


def summarise_rows(rows, method="aida", budget=None):
    facts, ranks = split_judgements(rows)
    return summarise(facts, ranks, method, budget)


def paired_rows(rows, method="aida", baseline="base", budget=None):
    facts, ranks = split_judgements(rows)
    return paired_difference(facts, ranks, method, baseline, budget)


# --- A. 중복 지목: 후보 정밀도와 고유 오류를 가른다 ------------------------------

def test_two_candidates_one_real_error():
    """같은 라벨을 width와 scale이 지목 → 후보 2, 고유 오류 1.

    **문서는 분자를 '고유 오류'라고 적어 놓고 코드는 hit 후보 수를 쓰고 있었다.**
    같은 오류를 두 번 지목한 것이 성과처럼 보이는 자리다. 이름을 갈랐다.
    """
    s = summarise_rows([j("c1", suspicion="width", verdict="hit", label_index=0),
                        j("c2", suspicion="scale", verdict="hit", label_index=0)])
    assert s.judged == 2
    assert s.hit_candidates == 2          # 후보는 둘
    assert s.unique_error_yield == 1      # 오류는 하나 ← 주지표
    assert s.candidate_precision == 1.0   # 후보 기준 정밀도는 2/2


# --- B·C. 빈 것 ---------------------------------------------------------------

def test_no_candidates_precision_is_undefined():
    s = summarise_rows([j("c1", severity=0.5)], budget=0)
    assert s.in_budget == 0 and s.judged == 0
    assert s.candidate_precision is None, "0.0이 아니라 정의 없음이다"
    assert s.hold_rate is None
    assert s.unique_error_yield == 0


def test_candidates_but_nothing_judged():
    s = summarise_rows([j("c1"), j("c2"), j("c3")])
    assert s.in_budget == 3 and s.judged == 0
    assert s.candidate_precision is None and s.hold_rate is None


# --- D·E. 보류 ----------------------------------------------------------------

def test_all_holds_consume_budget_but_not_precision():
    s = summarise_rows([j(f"c{i}", verdict="hold") for i in (1, 2, 3)])
    assert s.judged == 3                  # 시간을 썼다
    assert s.holds == 3
    assert s.decided == 0
    assert s.candidate_precision is None  # 결정된 것이 없다
    assert s.hold_rate == 1.0


def test_partial_holds():
    s = summarise_rows([j("c1", verdict="hit", label_index=0),
                        j("c2", verdict="miss"),
                        j("c3", verdict="hold"),
                        j("c4", verdict="hit", label_index=0)])
    assert s.judged == 4
    assert s.holds == 1
    assert s.decided == 3
    assert s.hit_candidates == 2
    assert s.unique_error_yield == 1
    assert s.candidate_precision == 2 / 3   # 보류는 분모에서 빠진다
    assert s.hold_rate == 0.25


# --- F. 동점 ------------------------------------------------------------------

def _tie_rows():
    return [j("cB", image="imgB", severity=0.5),
            j("cA", image="imgA", severity=0.5),
            j("cC", image="imgA", severity=0.5)]


def test_severity_ties_break_by_image_then_candidate():
    facts, ranks = split_judgements(_tie_rows())
    by_key = {a.key: a for a in facts}
    ordered = [by_key[r.candidate_key].candidate_id
               for r in rank_candidates(ranks, by_key)]
    assert ordered == ["cA", "cC", "cB"]
    picked = [by_key[r.candidate_key].candidate_id for r in top_n(ranks, by_key, 2)]
    assert picked == ["cA", "cC"]


def test_input_order_does_not_change_the_result():
    a = summarise_rows(_tie_rows(), budget=2)
    b = summarise_rows(list(reversed(_tie_rows())), budget=2)
    assert a == b


def test_missing_candidate_ties_are_deterministic():
    """누락 후보도 같은 규칙으로 자른다 — 좌표가 아니라 id 순이다."""
    rows = [j("m2", image="i1", severity=0.9, verdict="hit", unique_error_id="e2"),
            j("m1", image="i1", severity=0.9, verdict="hit", unique_error_id="e1")]
    facts, ranks = split_judgements(rows)
    by_key = {a.key: a for a in facts}
    ordered = [by_key[r.candidate_key].candidate_id
               for r in rank_candidates(ranks, by_key)]
    assert ordered == ["m1", "m2"]


# --- 묶음 ---------------------------------------------------------------------

def test_many_candidates_in_one_image_are_one_cluster():
    facts, _ = split_judgements([j("c1"), j("c2"), j("c3")])
    assert len({a.cluster for a in facts}) == 1


def test_group_id_joins_several_images():
    """연속 장면은 이미지가 달라도 한 묶음이다."""
    facts, _ = split_judgements([j("c1", image="i1", group_id="scene7"),
                                 j("c2", image="i2", group_id="scene7")])
    assert len({a.cluster for a in facts}) == 1


def test_same_group_id_in_two_datasets_stays_apart():
    """**다른 데이터셋의 같은 `scene7`이 한 묶음으로 합쳐지면 재표집이 틀린다.**"""
    facts, _ = split_judgements([
        j("c1", dataset="dsA", image="i1", group_id="scene7"),
        j("c2", dataset="dsB", image="i1", group_id="scene7")])
    assert len({a.cluster for a in facts}) == 2


def test_same_unique_error_id_in_two_datasets_stays_apart():
    """**다른 데이터셋의 같은 오류 id가 한 오류로 세어지면 고유 오류가 줄어든다.**"""
    facts, _ = split_judgements([
        j("c1", dataset="dsA", image="i1", verdict="hit", unique_error_id="e1"),
        j("c2", dataset="dsB", image="i1", verdict="hit", unique_error_id="e1")])
    assert len({a.error_key for a in facts}) == 2


# --- 검증이 선택 사항이 아니다 ---------------------------------------------------

def test_summarise_itself_rejects_a_bad_hit():
    """호출자가 validate()를 빼먹어도 잘못된 입력이 집계되면 안 된다."""
    with pytest.raises(ValidationError, match="고유 오류 id"):
        summarise_rows([j("c1", verdict="hit")])


def test_hit_with_label_index_is_fine():
    validate([j("c1", verdict="hit", label_index=3)])


def test_unknown_verdict_is_rejected():
    with pytest.raises(ValidationError, match="판정"):
        validate([j("c1", verdict="maybe")])


def test_duplicate_candidate_in_one_method_is_rejected():
    with pytest.raises(ValidationError, match="두 번"):
        validate([j("c1"), j("c1")])


@pytest.mark.parametrize("field,value", [
    ("dataset", ""), ("image", ""), ("candidate_id", ""), ("method", ""),
])
def test_empty_identifiers_are_rejected(field, value):
    kw = {"candidate_id": "c1"}
    if field == "candidate_id":
        kw["candidate_id"] = value
    else:
        kw[field] = value
    with pytest.raises(ValidationError, match="비어 있으면"):
        validate([j(**kw)])


def test_negative_label_index_is_rejected():
    with pytest.raises(ValidationError, match="0 이상"):
        validate([j("c1", verdict="hit", label_index=-1)])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_severity_is_rejected(bad):
    with pytest.raises(ValidationError, match="유한한"):
        validate([j("c1", severity=bad)])


def test_negative_budget_is_rejected():
    with pytest.raises(ValidationError, match="0 이상"):
        summarise_rows([j("c1")], budget=-1)


def test_zero_iterations_is_rejected():
    facts, ranks = split_judgements(_two_method_rows())
    with pytest.raises(ValidationError, match="1 이상"):
        paired_cluster_bootstrap(facts, ranks, "aida", "base", iterations=0)


def test_unknown_method_is_rejected():
    with pytest.raises(ValidationError, match="순위가 하나도 없다"):
        summarise_rows([j("c1")], method="없는방법")


def test_missing_baseline_is_rejected():
    """기준선 행이 하나도 없으면 비교가 성립하지 않는다."""
    with pytest.raises(ValidationError, match="기준선"):
        paired_rows([j("c1", method="aida")])


def test_comparing_a_method_with_itself_is_rejected():
    with pytest.raises(ValidationError, match="같은 방법"):
        paired_rows(_two_method_rows(), method="aida", baseline="aida")


def test_label_index_conflicting_with_unique_error_id_is_rejected():
    with pytest.raises(ValidationError, match="어긋난다"):
        validate([j("c1", verdict="hit", label_index=0, unique_error_id="딴것")])


# --- 판정은 방법과 무관한 하나의 사실이다 ----------------------------------------

def test_verdict_differing_by_method_is_rejected():
    """가림 판정은 방법의 의견이 아니다."""
    with pytest.raises(ValidationError, match="방법마다 다르다"):
        validate([j("c1", method="aida", verdict="hit", label_index=0),
                  j("c1", method="base", verdict="miss")])


def test_same_verdict_across_methods_is_fine():
    facts, ranks = split_judgements([
        j("c1", method="aida", severity=0.9, verdict="hit", label_index=0),
        j("c1", method="base", severity=0.1, verdict="hit", label_index=0)])
    assert len(facts) == 1        # 사실은 하나
    assert len(ranks) == 2        # 점수는 둘


def test_different_candidate_sets_are_rejected():
    """후보가 다르면 정렬 효과가 아니라 작업 전체 효과다."""
    with pytest.raises(ValidationError, match="후보 집합이 다르다"):
        paired_rows([j("c1", method="aida"), j("c2", method="aida"),
                     j("c1", method="base")])


# --- G. 데이터셋 동등 가중 ------------------------------------------------------

def _weighted_rows() -> list[Judgement]:
    """손계산 표 G.

    **모든 이미지가 같은 모양이다** — 오류 후보 하나와 오류 아닌 후보 하나.
    AIDA는 오류를 위로, 기준선은 오류 아닌 것을 위로 매긴다. 그래서 예산 1건이면
    **어느 묶음이 뽑히든** AIDA는 +1, 기준선은 0이다.

    묶음마다 결과가 같아야 재표집의 변동과 가중치를 따로 볼 수 있다.

    | 데이터셋 | 이미지 | 후보 | AIDA 심각도 | 기준선 심각도 | 판정 |
    |---|---|---|---|---|---|
    | ds_small | si1, si2 | e(오류) / n(아님) | 0.9 / 0.1 | 0.1 / 0.9 | hit / miss |
    | ds_big | bi1~bi4 | 〃 | 〃 | 〃 | 〃 |

    - 예산 1건에서 데이터셋별 차이 = **+1**
    - 데이터셋 동등 가중 전체 = (1 + 1) / 2 = **1.0**
    - 후보 수로 가중했다면 ds_big이 두 배라 결론이 그쪽으로 끌렸을 것이다
    """
    rows: list[Judgement] = []
    for dataset, images in (("ds_small", ["si1", "si2"]),
                            ("ds_big", ["bi1", "bi2", "bi3", "bi4"])):
        for img in images:
            for method, err_sev, ok_sev in (("aida", 0.9, 0.1), ("base", 0.1, 0.9)):
                rows.append(j(f"{img}_e", dataset=dataset, image=img, method=method,
                              severity=err_sev, verdict="hit",
                              unique_error_id=f"{img}/e"))
                rows.append(j(f"{img}_n", dataset=dataset, image=img, method=method,
                              severity=ok_sev, verdict="miss"))
    return rows


def test_equal_weight_not_candidate_weight():
    facts, ranks = split_judgements(_weighted_rows())
    r = equal_weight_overall(facts, ranks, "aida", "base", budget=1)
    # 예산 1건에서 AIDA는 양쪽 다 오류를 집고 기준선은 못 집는다 → 각 +1
    assert r["per_dataset"]["ds_small"]["difference"] == 1
    assert r["per_dataset"]["ds_big"]["difference"] == 1
    assert r["overall_difference"] == 1.0
    # 예산은 데이터셋마다 적용된다 — 총 검수량은 2건이다.
    assert r["total_reviewed"] == 2


def test_dataset_sizes_do_not_change_the_overall():
    """ds_big의 이미지가 두 배지만 결론을 더 끌지 않는다."""
    facts, ranks = split_judgements(_weighted_rows())
    r = equal_weight_overall(facts, ranks, "aida", "base", budget=1)
    assert len(r["per_dataset"]["ds_big"]["method_summary"]) > 0
    assert r["overall_difference"] == 1.0    # 크기 가중이었다면 달랐을 것


# --- H. 개별 구간은 겹치지만 짝지은 차이는 0을 안 걸친다 --------------------------

def _two_method_rows() -> list[Judgement]:
    """이미지 4장, 각 이미지에서 AIDA가 정확히 1개 더 찾는다.

    같은 후보 집합을 두 방법이 서로 다르게 정렬한다 — AIDA는 오류를 위로,
    기준선은 아래로. 예산을 걸면 찾는 수가 갈린다.
    """
    rows: list[Judgement] = []
    for n in range(1, 5):
        img = f"img{n}"
        for k in range(n + 1):
            name = f"c{n}_{k}"
            is_error = k < n
            for method in ("aida", "base"):
                if method == "aida":
                    sev = 1.0 - k * 0.01           # 오류가 위로
                else:
                    sev = 0.5 if is_error else 1.0  # 오류 아닌 것이 맨 위로
                rows.append(j(name, image=img, method=method, severity=sev,
                              verdict="hit" if is_error else "miss",
                              unique_error_id=f"{img}/e{k}" if is_error else None))
    return rows


def test_observed_paired_difference():
    """예산 없이 전부 보면 두 방법이 같은 것을 찾는다 — 차이 0."""
    assert paired_rows(_two_method_rows())["difference"] == 0


def test_budget_makes_the_ordering_matter():
    """예산 1건이면 AIDA는 오류를, 기준선은 오류 아닌 것을 본다 → 이미지당 +1."""
    facts, ranks = split_judgements(_two_method_rows())
    r = equal_weight_overall(facts, ranks, "aida", "base", budget=1)
    assert r["per_dataset"]["ds1"]["difference"] == 1


def test_paired_bootstrap_records_iterations_and_seed():
    facts, ranks = split_judgements(_two_method_rows())
    r = paired_cluster_bootstrap(facts, ranks, "aida", "base", budget=1,
                                 iterations=33, seed=99)
    assert r["iterations"] == 33 and r["seed"] == 99


def test_bootstrap_resamples_clusters_per_dataset():
    """묶음이 4개면 재표본에도 묶음이 4개다 — 후보 단위로 뽑으면 구간이 좁아진다."""
    facts, ranks = split_judgements(_two_method_rows())
    r = paired_cluster_bootstrap(facts, ranks, "aida", "base", budget=1,
                                 iterations=10, seed=1)
    assert r["clusters"] == {"ds1": 4}


def test_bootstrap_is_equal_weight_across_datasets():
    """묶음이 많은 데이터셋이 더 큰 가중치를 가지면 안 된다."""
    facts, ranks = split_judgements(_weighted_rows())
    r = paired_cluster_bootstrap(facts, ranks, "aida", "base", budget=1,
                                 iterations=100, seed=3)
    assert r["weighting"] == "데이터셋 동등 가중"
    assert set(r["clusters"]) == {"ds_small", "ds_big"}
    # 두 데이터셋 모두 차이가 항상 +1이라 어떤 재표본에서도 평균은 1이다.
    assert r["ci_low"] == 1.0 and r["ci_high"] == 1.0


def test_same_seed_same_result():
    facts, ranks = split_judgements(_two_method_rows())
    kw = {"budget": 1, "iterations": 50, "seed": 7}
    a = paired_cluster_bootstrap(facts, ranks, "aida", "base", **kw)
    b = paired_cluster_bootstrap(facts, ranks, "aida", "base", **kw)
    assert a == b


# --- Δ가 TBD인 동안은 판정하지 않는다 --------------------------------------------

def test_no_verdict_while_delta_is_tbd():
    assert verdict_against_delta({"ci_low": 3.0, "ci_high": 5.0}, None) == "미정"


def test_verdict_uses_the_lower_bound():
    r = {"ci_low": 3.0, "ci_high": 5.0}
    assert verdict_against_delta(r, 2.0) == "성공"      # 하한이 Δ를 넘는다
    assert verdict_against_delta(r, 4.0) == "불확실"    # 구간이 Δ를 걸친다
    assert verdict_against_delta(r, 6.0) == "실패"      # 상한이 Δ 아래다
