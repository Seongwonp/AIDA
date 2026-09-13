"""개발 증거 추정기 검사 (experiment/estimate_planning_inputs.py).

기대값은 손으로 계산한 것이다. 구현이 낸 값을 옮겨 적지 않는다.
"""
import json

import pytest

import estimate_planning_inputs as est


# ── 짝 비교 확률 ─────────────────────────────────────────────────────────────

def test_목록_순서_AUC_손계산():
    """[정, 오, 정, 오] — 1위 정답은 오답 2개 위, 3위 정답은 오답 1개 위.

    이긴 쌍 3 / 전체 쌍 (2 × 2) = 0.75
    """
    assert est.auc_from_order([True, False, True, False]) == 0.75
    assert est.auc_from_order([True, False]) == 1.0
    assert est.auc_from_order([False, True]) == 0.0


def test_정답이나_오답이_없으면_AUC를_내지_않는다():
    assert est.auc_from_order([True, True]) is None
    assert est.auc_from_order([False]) is None
    assert est.auc_from_order([]) is None
    assert est.auc_from_scores([(True, 0.3)]) is None


def test_점수_AUC는_동점을_반으로_센다():
    """정답 0.9·0.1, 오답 0.9·0.5.

    (0.9 vs 0.9) 0.5 + (0.9 vs 0.5) 1 + (0.1 vs 0.9) 0 + (0.1 vs 0.5) 0 = 1.5 / 4 = 0.375
    """
    got = est.auc_from_scores([(True, 0.9), (False, 0.9), (True, 0.1), (False, 0.5)])
    assert got == 0.375


def test_Wilson_구간은_0건에서도_폭이_있다():
    """0/10의 95% Wilson 상한은 0.2775 (z²/(n+z²) = 3.8415/13.8415)."""
    low, high = est.wilson(0, 10)
    assert low == 0.0
    assert high == pytest.approx(0.2775, abs=1e-4)
    low, high = est.wilson(5, 10)
    assert (low, high) == (pytest.approx(0.2366, abs=1e-4), pytest.approx(0.7634, abs=1e-4))
    assert est.wilson(0, 0) is None


# ── 층과 합치기 ──────────────────────────────────────────────────────────────

def _row(correct, suspicion, severity, class_id=0):
    return [correct, suspicion, severity, False, 0.0, 0.9, class_id]


def test_누락_후보는_기존_라벨_층에서_뺀다():
    rows = [_row(True, "width", 0.9), _row(False, "missing", 0.8), _row(False, "width", 0.1)]
    got = est.condition_summary(rows)
    assert got["labelled_candidates"] == 2
    assert got["injected_true"] == 1
    assert got["hit_rate_against_injected_truth"] == 0.5
    assert got["aida_auc_by_review_order"] == 1.0
    assert got["missing_candidates_excluded"] == 1


def test_조건을_건너_합친_값을_내지_않는다(tmp_path):
    """조건마다 주입 설계가 달라서 합치면 설계를 재게 된다."""
    cache = {
        "width_m30": {"type": "width", "magnitude": -30,
                      "verdicts_by_rank": [_row(True, "width", 0.9), _row(False, "width", 0.2)]},
        "missing_10": {"type": "missing", "magnitude": 10,
                       "verdicts_by_rank": [_row(False, "width", 0.7), _row(False, "width", 0.6)]},
    }
    path = tmp_path / "box_accuracy_verdicts_mc.json"
    path.write_text(json.dumps(cache), encoding="utf-8")
    got = est.analyse_file(path)

    assert got["per_condition"]["width_m30"]["aida_auc_by_review_order"] == 1.0
    assert got["per_condition"]["missing_10"]["aida_auc_by_review_order"] is None
    # 조건 사이 분포만: AUC가 있는 조건은 하나다.
    assert got["aida_auc_by_review_order_across_conditions"] == {
        "n": 1, "min": 1.0, "median": 1.0, "max": 1.0}
    # 합친 hit 비율 같은 칸이 없다.
    assert "by_suspicion_type" not in got
    assert "hit_rate_against_injected_truth" not in got
    assert got["truth"] == "injected"
    assert len(got["sha256"]) == 64


def test_클래스별_AUC는_표본이_모자라면_내지_않는다(tmp_path):
    few = [_row(True, "width", 0.9, 1)] * 3 + [_row(False, "width", 0.1, 1)] * 3
    enough = ([_row(True, "width", 0.9, 0)] * est.MIN_PER_SIDE
              + [_row(False, "width", 0.1, 0)] * est.MIN_PER_SIDE)
    path = tmp_path / "box_accuracy_verdicts_mc.json"
    path.write_text(json.dumps({"c": {"type": "width", "magnitude": 1,
                                      "verdicts_by_rank": few + enough}}), encoding="utf-8")
    got = est.analyse_file(path)["aida_auc_by_class_within_condition"]
    assert "1" not in got
    assert got["0"] == {"n": 1, "min": 1.0, "median": 1.0, "max": 1.0}


def test_자와_데이터가_어긋난_구성은_계획에_쓰지_않는다고_표시한다():
    for tag in ("_mc_cyclist_rich_ruler_runs", "_mc_ruler_self"):
        assert est.CONFIGURATION[tag]["use_for_planning"].startswith("쓰지 않는다")


def test_기준선_AUC는_추정_불가로_남긴다():
    """raw_signal을 1 − label_iou 대신 쓰지 않는다."""
    assert "label_iou" in est.NOT_ESTIMABLE["baseline_iou_auc"]
    assert "aida_minus_baseline_auc_gap" in est.NOT_ESTIMABLE
