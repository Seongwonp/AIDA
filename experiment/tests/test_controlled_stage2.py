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


# ── 집계(analyze_controlled_baseline_stage2): 해시 동점 규칙·분모 부족분 ──
import analyze_controlled_baseline_stage2 as A2  # noqa: E402
from evaluation.coverage import tie_key  # noqa: E402


def _rec(condition="width_x", n_labels=40, n_findings=20, ol_scored=40, preds=()):
    """label_iou 0 동점 라벨 8개(그중 주입 오류는 a3·a6) + 0.5 이상 라벨들."""
    labels = []
    for i in range(n_labels):
        img = f"a{i}.png"
        r = {"image": img, "label_index": 0, "label_iou": 0.0 if i < 8 else 0.5 + i / 1000,
             "injected_error": i in (3, 6, 30)}
        if i < ol_scored:
            r["objectlab_score"] = 0.1 if i < 4 else 0.9
        labels.append(r)
    verd = [[i % 2 == 0, "width", 0.5, False] for i in range(n_findings)]
    fids = [[f"a{8 + i}.png", 0] for i in range(n_findings)]
    row = {"tp": n_findings // 2, "verdicts_by_rank": verd, "finding_ids_by_rank": fids,
           "present_types": ["width"]}
    return {"condition": condition, "rows": {A2.LEG: row, A2.CUR: row},
            "population": {"all_labels": labels, "unmatched_predictions": list(preds),
                           "objectlab": {"available": True}}}


def test_tie_rule_old_vs_seeded_hash():
    rec = _rec()  # k = 2, 상위 2는 label_iou 0 동점 8개 중 2개
    old = A2.condition_metrics(rec, A2.NAME_INDEX)
    # 옛 규칙: 이미지 이름 순 a0, a1 → 주입 오류 없음
    assert old["methods"]["all_label_iou"] == 0.0
    assert "all_label_iou" in old["boundary_tie"]
    for seed in [A2.PRIMARY_TIE_SEED, 1, 2, 3]:
        top = sorted(range(8), key=lambda i: tie_key(seed, f"a{i}.png/0"))[:2]
        want = sum(i in (3, 6) for i in top) / 2
        got = A2.condition_metrics(rec, seed)["methods"]["all_label_iou"]
        assert got == want
    # 입력 순서와 무관
    rev = _rec()
    rev["population"]["all_labels"].reverse()
    assert (A2.condition_metrics(rev, 7)["methods"]
            == A2.condition_metrics(_rec(), 7)["methods"])
    # 제품 순서(legacy·current)는 동점 규칙과 무관
    assert old["methods"]["aida_current"] == A2.condition_metrics(rec, 5)["methods"]["aida_current"]


def test_denominator_shortfall_counts_and_actual_variant():
    rec = _rec(n_findings=30, ol_scored=2)  # k = 3, ObjectLab 점수 있는 라벨 2개(a0·a1)
    m = A2.condition_metrics(rec)
    assert m["k"] == 3 and m["n_candidates"]["all_label_objectlab"] == 2
    assert m["denominator_shortfall"] == ["all_label_objectlab"]
    assert m["methods"]["all_label_objectlab"] == 0.0  # 분모 k 유지
    assert m["methods_actual_denominator"] == {"all_label_objectlab": 0.0}
    s = A2.shortfall_summary([m])["existing_label_layer"]["all_label_objectlab"]
    assert s["n_short"] == 1 and s["n_conditions"] == 1 and s["n_zero_candidates"] == 0


def test_missing_layer_shortfall_and_hash_ties():
    preds = [{"image": f"p{i}.png", "box": [i, 0, i + 1, 1], "confidence": 0.8,
              "matches_dropped": i == 1, **({"objectlab_overlooked": 0.2} if i == 1 else {})}
             for i in range(6)]
    rec = _rec(condition="missing_10", n_findings=20, preds=preds)
    for v in rec["rows"][A2.CUR]["verdicts_by_rank"][:10]:
        v[1] = "missing"
    m = A2.condition_metrics(rec)["missing_layer"]
    assert m["k_m"] == 1
    assert m["unmatched_objectlab"] == 1.0 and m["denominator_shortfall"] == []
    assert "unmatched_confidence" in m["boundary_tie"]  # 확신도 6개 모두 같음
    top = min(range(6), key=lambda i: tie_key(A2.PRIMARY_TIE_SEED, A2.pred_id(preds[i])))
    assert m["unmatched_confidence"] == float(top == 1)
    rec["population"]["unmatched_predictions"] = [dict(p) for p in preds if p["image"] != "p1.png"]
    m2 = A2.condition_metrics(rec)["missing_layer"]
    assert m2["denominator_shortfall"] == ["unmatched_objectlab"]
    assert m2["unmatched_objectlab"] == 0.0 and m2["methods_actual_denominator"] == {
        "unmatched_objectlab": None}
    ss = A2.shortfall_summary([A2.condition_metrics(rec)])["missing_layer"]["unmatched_objectlab"]
    assert ss == {"n_conditions": 1, "n_short": 1, "n_zero_candidates": 1,
                  "mean_actual_denominator": None}
