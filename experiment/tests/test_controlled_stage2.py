"""통제 기준선 2단계 — 추론 한 번에 두 순서 채점, 조건별 저장·이어 돌리기. 합성 자료만(GPU 없음)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import compare_rulers_seeded as C  # noqa: E402
import evaluate_box_accuracy as E  # noqa: E402
from config import Condition  # noqa: E402
from test_scoring_orderings import MIXED_RECORD, _make_condition, _mixed_findings  # noqa: E402

BOTH = [E.ORDER_LEGACY_SEVERITY_V0, E.ORDER_REVIEW_V1]
FIT = {"matched_labels": 8, "predictions": 9, "confidences": []}


def _fake_run(calls):
    def run(images_dir, labels_dir, limit, weights=None, collect_population=False):
        calls.append(collect_population)
        if collect_population:
            pop = {"all_labels": [{"image": "a.png", "label_index": 0, "label_iou": 0.5}],
                   "unmatched_predictions": [], "objectlab": {"available": False}}
            return _mixed_findings(), 10, FIT, pop
        return _mixed_findings(), 10, FIT
    return run


def test_identity_off_by_default_and_aligned_when_on(tmp_path, monkeypatch):
    cond = Condition("width_x", "width", 30)
    _make_condition(tmp_path, monkeypatch, cond.name, MIXED_RECORD)
    off = E.score_findings(cond, _mixed_findings(), 10, None, ordering=E.ORDER_REVIEW_V1)
    on = E.score_findings(cond, _mixed_findings(), 10, None, ordering=E.ORDER_REVIEW_V1,
                          with_identity=True)
    assert "finding_ids_by_rank" not in off
    ids = on.pop("finding_ids_by_rank")
    assert on == off
    assert len(ids) == len(on["verdicts_by_rank"])
    # review_order: width 3건 먼저, 비계통 class_mismatch(b.png, 1) 꼴찌
    assert ids[-1] == ["b.png", 1]


def test_one_inference_scores_both_orderings(tmp_path, monkeypatch):
    import diagnose_labels
    cond = Condition("width_x", "width", 30)
    _make_condition(tmp_path, monkeypatch, cond.name, MIXED_RECORD)
    calls = []
    monkeypatch.setattr(diagnose_labels, "run", _fake_run(calls))
    res = E.score_condition_orderings(cond, None, BOTH, collect_population=True)
    assert calls == [True]  # 추론 한 번
    for o in BOTH:
        alone = E.score_findings(cond, _mixed_findings(), 10, None, FIT, ordering=o)
        assert res["rows"][o] == alone
    assert res["population"]["all_labels"][0]["injected_error"] is True
    with pytest.raises(ValueError):
        E.score_condition_orderings(cond, None, ["nope"])


def test_measure_orderings_store_and_resume(tmp_path, monkeypatch):
    import diagnose_labels
    cond = Condition("width_x", "width", 30)
    _make_condition(tmp_path, monkeypatch, cond.name, MIXED_RECORD)
    monkeypatch.setitem(config._BY_NAME, cond.name, cond)
    calls = []
    monkeypatch.setattr(diagnose_labels, "run", _fake_run(calls))
    store = C.ConditionStore(tmp_path / "out" / "r" / "s42")
    seen = []
    first = C.measure_orderings([cond.name], None, BOTH, collect_population=True, store=store,
                                on_condition=lambda n, rec, reused: seen.append(reused))
    assert calls == [True] and seen == [False]
    rec = store.load(cond.name)
    assert set(rec["rows"]) == set(BOTH) and "population" in rec
    assert rec["rows"][E.ORDER_REVIEW_V1]["finding_ids_by_rank"][-1] == ["b.png", 1]
    # 두 번째: 추론 없이 저장본에서
    second = C.measure_orderings([cond.name], None, BOTH, collect_population=True, store=store,
                                 on_condition=lambda n, rec, reused: seen.append(reused))
    assert calls == [True] and seen == [False, True]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    # legacy는 class_mismatch(오답)가 1위 → P@10%(k=1) 0, current는 1
    assert first[E.ORDER_LEGACY_SEVERITY_V0]["per_condition"][cond.name] == 0.0
    assert first[E.ORDER_REVIEW_V1]["per_condition"][cond.name] == 1.0
    with pytest.raises(FileExistsError):
        store.save(cond.name, rec)


def test_measure_default_path_unchanged(tmp_path, monkeypatch):
    """orderings 없이 부르면 예전처럼 조건마다 score_condition(ordering 인자 없이)."""
    seen_kwargs = []
    monkeypatch.setattr(E, "RULER_PATH", None)  # measure가 바꾸는 전역을 검사 뒤 되돌린다
    w = tmp_path / "best.pt"
    w.write_bytes(b"x")
    monkeypatch.setattr(C, "ruler_path", lambda kind, seed: w)
    monkeypatch.setattr(C, "CONDITIONS", ["width_m30", "class_swap_30"])

    def fake_score(cond, limit, **kw):
        seen_kwargs.append(kw)
        if cond.name == "class_swap_30":
            return {"tp": 0, "fp": 0, "verdicts_by_rank": [], "matched_label_ratio": None}
        v = [(True,)] * 9 + [(False,)]
        return {"tp": 9, "fp": 1, "verdicts_by_rank": v, "matched_label_ratio": 0.8}

    monkeypatch.setattr(E, "score_condition", fake_score)
    m = C.measure("matched", 42, 80)
    assert seen_kwargs == [{}, {}]
    assert m == {"precision": 0.9, "top10": 1.0, "top10_noswap": 1.0, "n_conditions": 1,
                 "per_condition": {"width_m30": 1.0}, "per_condition_fit": {"width_m30": 0.8},
                 "silent": ["class_swap_30"]}
    C.measure("matched", 42, 80, ordering=E.ORDER_REVIEW_V1)
    assert seen_kwargs[-1] == {"ordering": E.ORDER_REVIEW_V1}
