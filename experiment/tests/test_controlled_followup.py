"""통제 기준선 후속 집계(analyze_controlled_baseline_followup) — 합성 기록만."""
import copy
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_controlled_baseline_followup as F  # noqa: E402
import analyze_controlled_baseline_stage2 as A2  # noqa: E402
from test_controlled_stage2 import _rec  # noqa: E402


def test_k_of_integer_floor_min_one():
    assert F.k_of(30, 10) == 3 and F.k_of(9, 10) == 1 and F.k_of(0, 5) == 1
    assert F.k_of(199, 50) == 99 and F.k_of(479, 2) == 9
    for n in range(0, 2000):  # 10%는 2단계 집계의 int(n * 0.1)과 같아야 한다
        assert F.k_of(n, 10) == max(1, int(n * 0.1))


def test_paired_summary_seed_then_condition_means_and_t_interval():
    d = {1: {"a": 0.2, "b": 0.0}, 2: {"a": 0.1, "b": -0.1}, 3: {"a": 0.3, "b": 0.1}}
    s = F.paired_summary(d)
    seed_means = [0.1, 0.0, 0.2]
    assert s["mean"] == pytest.approx(0.1) and s["n_seeds"] == 3 and s["t_df"] == 2
    half = 4.302652729911275 * 0.1 / math.sqrt(3)  # t(0.975, 2) × sd / √n
    assert s["exploratory_t95"] == [round(0.1 - half, 4), round(0.1 + half, 4)]
    assert s["seeds_positive"] == "2/3"  # 시드 2의 평균이 0
    # 조건별 시드 평균: a 0.2, b 0.0 → 양수 1/2, 0 하나
    assert s["conditions_positive"] == "1/2" and s["conditions_zero"] == 1
    assert sorted(float(v) for v in s["per_seed_mean"].values()) == pytest.approx(sorted(seed_means))


def test_paired_summary_single_seed_has_no_interval():
    s = F.paired_summary({42: {"a": 0.5, "b": -0.1}})
    assert s["exploratory_t95"] is None and s["sd_across_seeds"] is None
    assert s["seeds_positive"] == "1/1" and s["conditions_positive"] == "1/2"


def test_ranked_lists_match_stage2_metrics_at_ten_percent():
    for seed in [A2.PRIMARY_TIE_SEED, 1, 7, None]:
        rec = _rec(n_findings=30)
        cm = A2.condition_metrics(rec, seed)
        info = {"flagged": 30, "tp": rec["rows"][A2.CUR]["tp"], "n_labels": 40,
                "n_injected": 3}
        got = F.metrics_at(F.ranked_lists(rec, seed), cm["k"], info)
        for m in ("aida_legacy", "aida_current", "aida_iou_reorder", "aida_current_unique",
                  "all_label_iou", "all_label_objectlab", "aida_random_expected",
                  "all_label_random_expected"):
            assert round(got[m]["v"], 4) == cm["methods"][m], (seed, m)


def test_random_expected_scaled_when_candidates_short():
    info = {"flagged": 4, "tp": 2, "n_labels": 40, "n_injected": 10}
    m = F.metrics_at({"aida_current": [True, False, True, False]}, 8, info)
    assert m["aida_random_expected"]["v"] == pytest.approx(0.5 * 4 / 8)
    assert m["aida_random_expected"]["act"] == pytest.approx(0.5)
    assert m["all_label_random_expected"]["v"] == pytest.approx(0.25)  # 후보 40 ≥ k
    assert m["aida_current"]["v"] == pytest.approx(2 / 8)  # 분모 k
    assert m["aida_current"]["act"] == pytest.approx(2 / 4)  # 실제 분모
    assert m["aida_current"]["n"] == 4


def test_precision_top_matches_product_definition():
    import evaluate_box_accuracy as E
    flags = [True, False, True]
    assert F.precision_top(flags, 5) == E.precision_at_k([(f,) for f in flags], 5) == pytest.approx(2 / 3)
    assert F.precision_top([], 5) == 0.0


def _full_rec(**kw):
    rec = _rec(**kw)
    for r in rec["population"]["all_labels"]:
        r.setdefault("objectlab_score", 0.5)
    rec["population"]["objectlab"]["labels_scored"] = len(rec["population"]["all_labels"])
    for o in (A2.LEG, A2.CUR):
        row = copy.deepcopy(rec["rows"][o])
        row["flagged"] = len(row["verdicts_by_rank"])
        row["tp"] = sum(v[0] for v in row["verdicts_by_rank"])
        rec["rows"][o] = row
    return rec


def test_check_record_clean_missing_fields_and_id_breaks():
    rec = _full_rec(n_findings=20)
    ok = F.check_record(rec, rec["condition"], None)
    assert "missing_fields" not in ok and "length_or_summary_mismatch" not in ok
    assert ok["finding_label_id_breaks"] == 0 and ok["finding_type_vs_label_index_mismatch"] == 0
    bad = copy.deepcopy(rec)
    del bad["population"]["unmatched_predictions"]
    del bad["rows"][A2.CUR]["finding_ids_by_rank"]
    mf = F.check_record(bad, bad["condition"], None)["missing_fields"]
    assert "population.unmatched_predictions" in mf
    assert f"rows.{A2.CUR}.finding_ids_by_rank" in mf
    brk = copy.deepcopy(rec)
    brk["rows"][A2.CUR]["finding_ids_by_rank"][0] = ["nowhere.png", 0]
    r = F.check_record(brk, brk["condition"], None)
    assert r["finding_label_id_breaks"] == 1
    assert "legacy and current finding id multisets differ" in r["length_or_summary_mismatch"]


def test_check_record_summary_mismatch_detected():
    rec = _full_rec(n_findings=20)
    k = max(1, int(20 * 0.1))
    good = A2.p_at([v[0] for v in rec["rows"][A2.CUR]["verdicts_by_rank"]], k)
    summ = {o: {"per_condition": {rec["condition"]: good}, "silent": []} for o in (A2.LEG, A2.CUR)}
    assert "length_or_summary_mismatch" not in F.check_record(rec, rec["condition"], summ)
    summ[A2.LEG]["per_condition"][rec["condition"]] = good + 0.1
    assert F.check_record(rec, rec["condition"], summ)["length_or_summary_mismatch"]


def _store(n_seeds=3):
    """시드마다 같은 조건 2개(width_x·missing_10) — missing_*는 A·B에서 빠져야 한다."""
    store = {}
    for s in range(n_seeds):
        store[s] = {}
        for c in ("width_x", "missing_10"):
            rec = _full_rec(condition=c, n_findings=30 + 10 * s)
            store[s][c] = F.compact_record(rec)
    return store


def test_section_a_uses_existing_layer_and_pairs_same_condition_seed():
    store = _store()
    a = F.section_a(store)
    e = a["aida_current_minus_all_label_objectlab"]["primary_tie_seed"]
    assert e["n_conditions"] == 1  # missing_10 제외
    want = [store[s]["width_x"]["by_tie"][str(F.PRIMARY)]["f10"]["aida_current"]["v"]
            - store[s]["width_x"]["by_tie"][str(F.PRIMARY)]["f10"]["all_label_objectlab"]["v"]
            for s in range(3)]
    assert e["mean"] == round(sum(want) / 3, 4)
    sens = a["aida_current_minus_all_label_iou"]["tie_seed_sensitivity"]
    assert len(sens["mean_by_tie_seed"]) == len(F.SENS)
    assert "tie_seed_sensitivity" not in a["aida_current_minus_all_label_random_expected"]


def test_section_b_shortfall_and_iou0_records():
    store = _store(n_seeds=1)
    b = F.section_b(store)
    # 전체 라벨 5% of 40 = 2, f50 of 30 findings = 15 → 고유 AIDA 후보(30) 충분
    assert store[0]["width_x"]["ks"] == {"f5": 1, "f10": 3, "f20": 6, "f50": 15,
                                         "l1": 1, "l2": 1, "l5": 2}
    # ObjectLab 점수 라벨 40개 → 부족 없음, 기존 라벨 층 조건 1개
    assert b["unique_label_unit"]["f50"]["all_label_objectlab"]["n_short"] == 0
    assert b["unique_label_unit"]["f50"]["all_label_objectlab"]["n_condition_runs"] == 1
    # IoU 0 라벨 8개: k = 15 > 8, k = 3 ≤ 8
    assert b["iou0"]["f50"] == {"condition_runs_k_gt_n_iou0": 1, "n_condition_runs": 1}
    assert b["iou0"]["f10"]["condition_runs_k_gt_n_iou0"] == 0
    assert b["iou0"]["n_iou0_by_condition"] == {"width_x": [8]}


def test_section_b_reports_aida_shortfall_on_label_based_k():
    rec = _full_rec(n_findings=1, n_labels=400)  # 지목 1건, 라벨 5% = 20 > 1
    store = {0: {"width_x": F.compact_record(rec)}}
    b = F.section_b(store)
    cur = b["finding_unit"]["l5"]["aida_current"]
    assert cur["n_short"] == 1 and "actual_denominator" in cur
    assert cur["value"]["mean"] == round(float(rec["rows"][A2.CUR]["verdicts_by_rank"][0][0]) / 20, 4)


def test_section_c_at5_and_at_k_are_separate():
    store = _store(n_seeds=2)
    c = F.section_c(store, None)
    for s, v in c["per_seed"].items():
        recs = store[int(s)].values()
        l5 = sum(r["at5"]["aida_legacy"] for r in recs) / 2
        assert v["legacy_at5"] == round(l5, 4) and v["n_conditions"] == 2  # missing_* 포함
    assert set(c) >= {"diff_at_k", "diff_at5"}
