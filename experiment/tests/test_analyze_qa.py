"""최종 분석 경로 — 지문·설정 대조, 미판정 거부, 판정자 확인."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analyze_qa  # noqa: E402
from evaluation.coverage import export_fingerprint, tie_key  # noqa: E402
from evaluation.schema import ValidationError  # noqa: E402

A, B = "aida", "all_label_iou"
N, ITER, SEED = 2, 30, 3


def export(judged_all=True):
    cands = [("i0", "c0", "g0", 1.0), ("i0", "c1", "g0", 1.0), ("i1", "c2", "g1", 0.9), ("i2", "c3", "g2", 0.8)]
    adjs = [{"canonical_candidate_id": c, "image": im, "label_index": 0, "suspicion": "",
             "verdict": ("hit" if k == 0 else "miss") if (judged_all or k < 2) else None,
             "unique_error_id": f"{im}/L0" if k == 0 else None, "group_id": g, "box": [0, 0, 5, 5],
             "complete": True, "source": "label", "random_sample": False, "coverage_extra": k >= 2}
            for k, (im, c, g, _) in enumerate(cands)]
    ranks = [{"method": m, "canonical_candidate_id": c, "severity": s, "score": s, "tie_key": tie_key(1, c)}
             for (im, c, g, s) in cands for m in (A, B)]
    e = {"schema_version": 1, "evaluation_id": "e", "dataset_id": "d", "adjudicator": "primary",
         "requested_scope": "labelled_candidates", "comparison_mode": "candidate_generation_included",
         "comparison_allowed": True, "judge_budget": N, "methods": [A, B],
         "adjudications": adjs, "rankings": ranks}
    e["bootstrap_coverage"] = {"iterations": ITER, "seed": SEED, "budget": N, "methods": [A, B],
                               "input_fingerprint": export_fingerprint(e)}
    return e


def test_설정과_지문이_맞고_전부_판정되면_분석한다():
    r = analyze_qa.analyse(export(), N, ITER, SEED, [A, B])
    assert r["comparisons"][f"{B}_minus_{A}"]["judged_top_n_required"] is True
    assert r["settings"]["fingerprint"] == export()["bootstrap_coverage"]["input_fingerprint"]


@pytest.mark.parametrize("budget,iters,seed,methods", [(3, ITER, SEED, [A, B]), (N, 31, SEED, [A, B]),
                                                      (N, ITER, 4, [A, B]), (N, ITER, SEED, [A])])
def test_설정이_다르면_중단한다(budget, iters, seed, methods):
    with pytest.raises(ValidationError):
        analyze_qa.analyse(export(), budget, iters, seed, methods)


def test_순위나_동점_키가_바뀌면_지문이_달라_중단한다():
    e = export()
    e["rankings"][0]["tie_key"] = "x"
    with pytest.raises(ValidationError, match="지문"):
        analyze_qa.analyse(e, N, ITER, SEED, [A, B])


def test_coverage_없는_묶음은_받지_않는다():
    e = export(); del e["bootstrap_coverage"]
    with pytest.raises(ValidationError, match="bootstrap_coverage"):
        analyze_qa.analyse(e, N, ITER, SEED, [A, B])


def test_미판정이_남아_있으면_중단한다():
    with pytest.raises(ValidationError, match="미판정"):
        analyze_qa.analyse(export(judged_all=False), N, ITER, SEED, [A, B])


def test_다른_판정자의_내보내기는_명시할_때만_받는다():
    e = export(); e["adjudicator"] = "ai"
    with pytest.raises(ValidationError, match="판정자"):
        analyze_qa.analyse(e, N, ITER, SEED, [A, B])
    analyze_qa.analyse(e, N, ITER, SEED, [A, B], adjudicator="ai")


def test_판정을_바꿔도_입력_지문은_그대로다():
    e = export(); f = copy.deepcopy(e)
    for r in f["adjudications"]:
        r["verdict"] = "hold"
    assert export_fingerprint(e) == export_fingerprint(f)


def test_original_top_n_must_be_judged_even_if_resamples_do_not_select_it(monkeypatch):
    e = export()
    e["adjudications"][0]["verdict"] = None
    e["adjudications"][0]["unique_error_id"] = None
    monkeypatch.setattr(analyze_qa, "unjudged_in_fixed_resamples", lambda *a, **k: {A: [], B: []})
    with pytest.raises(ValidationError, match="원래 표본"):
        analyze_qa.analyse(e, N, ITER, SEED, [A, B])
