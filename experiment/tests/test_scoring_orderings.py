"""채점 순서 버전(legacy_severity_v0 / review_order_v1)과 모집단 수집 — 합성 자료만.

GPU·실제 추론 없음. 조건 폴더는 tmp_path에 만들고 config.CONDITIONS_DIR를 바꾼다.
"""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import evaluate_box_accuracy as E  # noqa: E402
from config import Condition  # noqa: E402
from label_diagnosis import BoxFinding, rescore, review_order, summarize  # noqa: E402


def _make_condition(tmp_path, monkeypatch, name, record, images=("a.png", "b.png")):
    root = tmp_path / name
    (root / "images" / "train").mkdir(parents=True)
    (root / "labels" / "train").mkdir(parents=True)
    for im in images:
        Image.new("RGB", (100, 100)).save(root / "images" / "train" / im)
    (root / "injection_record.json").write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(config, "CONDITIONS_DIR", tmp_path)


def _f(image, idx, suspicion, severity, raw=0.3, conf=0.9):
    return BoxFinding(image=image, label_index=idx, suspicion=suspicion, severity=severity,
                      detail="", raw_signal=raw, confidence=conf)


# width 3건(라벨 10개 중 30% → 절대 문턱으로 계통), class_mismatch 1건(10%, 비계통).
# class_mismatch에 높은 심각도를 줘 -severity만이면 맨 위에 오게 한다.
def _mixed_findings():
    return [
        _f("a.png", 0, "width", 0.50),
        _f("a.png", 1, "width", 0.50),
        _f("b.png", 0, "width", 0.50),
        _f("b.png", 1, "class_mismatch", 0.99),
    ]


MIXED_RECORD = {"a": {"errored": [0, 1], "dropped": []},
                "b": {"errored": [0], "dropped": []}}


def test_legacy_and_current_differ_on_hand_built_case(tmp_path, monkeypatch):
    cond = Condition("width_x", "width", 30)
    _make_condition(tmp_path, monkeypatch, cond.name, MIXED_RECORD)
    legacy = E.score_findings(cond, _mixed_findings(), 10, None,
                              ordering=E.ORDER_LEGACY_SEVERITY_V0)
    current = E.score_findings(cond, _mixed_findings(), 10, None,
                               ordering=E.ORDER_REVIEW_V1)
    # 비계통 class_mismatch(오답)가 legacy에선 1위, current에선 꼴찌
    assert legacy["verdicts_by_rank"][0][1] == "class_mismatch"
    assert legacy["verdicts_by_rank"][0][0] is False
    assert current["verdicts_by_rank"][0][1] == "width"
    assert current["verdicts_by_rank"][-1][1] == "class_mismatch"
    assert E.precision_at_k(legacy["verdicts_by_rank"], 1) == 0.0
    assert E.precision_at_k(current["verdicts_by_rank"], 1) == 1.0
    # TP/FP 판정은 순서와 무관
    assert (legacy["tp"], legacy["fp"]) == (current["tp"], current["fp"]) == (3, 1)
    assert legacy["ordering"] == "legacy_severity_v0"
    assert current["ordering"] == "review_order_v1"


def test_legacy_equals_minus_severity_sort(tmp_path, monkeypatch):
    cond = Condition("width_x", "width", 30)
    _make_condition(tmp_path, monkeypatch, cond.name, MIXED_RECORD)
    findings = _mixed_findings()
    row = E.score_findings(cond, findings, 10, None, ordering=E.ORDER_LEGACY_SEVERITY_V0)
    sev = [v[2] for v in row["verdicts_by_rank"]]
    assert sev == sorted(sev, reverse=True)
    # 같은 승격(절대 문턱)을 거친 뒤 -severity 안정 정렬과 정확히 같다
    expected = sorted(rescore(findings, summarize(findings, 10), present={"width"}),
                      key=lambda f: -f.severity)
    assert [(v[1], v[2]) for v in row["verdicts_by_rank"]] == \
        [(f.suspicion, f.severity) for f in expected]


def test_legacy_does_not_use_relative_fallback(tmp_path, monkeypatch):
    """상대 문턱 물러남(09-06)은 legacy에 없다 — 승격 집합이 다르다."""
    cond = Condition("width_x", "width", 30)
    _make_condition(tmp_path, monkeypatch, cond.name, MIXED_RECORD)
    # 라벨 100개: width 10%(절대 문턱 0.12 미달, 상대 문턱 충족), 나머지 1%씩
    findings = ([_f("a.png", i, "width", 0.4) for i in range(10)]
                + [_f("b.png", 0, "class_mismatch", 0.9), _f("b.png", 1, "height", 0.3)])
    legacy = E.score_findings(cond, findings, 100, None, ordering=E.ORDER_LEGACY_SEVERITY_V0)
    current = E.score_findings(cond, findings, 100, None, ordering=E.ORDER_REVIEW_V1)
    assert legacy["present_types"] == []
    assert current["present_types"] == ["width"]


def test_default_path_unchanged(tmp_path, monkeypatch):
    cond = Condition("width_x", "width", 30)
    _make_condition(tmp_path, monkeypatch, cond.name, MIXED_RECORD)
    findings = _mixed_findings()
    default = E.score_findings(cond, findings, 10, None)
    assert "ordering" not in default
    # 기존 코드 경로: rescore → review_order
    summary = summarize(findings, 10)
    old = review_order(rescore(findings, summary), summary)
    assert [(v[1], v[2]) for v in default["verdicts_by_rank"]] == \
        [(f.suspicion, f.severity) for f in old]
    named = E.score_findings(cond, findings, 10, None, ordering=E.ORDER_REVIEW_V1)
    named.pop("ordering")
    assert named == default


def test_unknown_ordering_rejected(tmp_path, monkeypatch):
    cond = Condition("width_x", "width", 30)
    _make_condition(tmp_path, monkeypatch, cond.name, MIXED_RECORD)
    with pytest.raises(ValueError):
        E.score_findings(cond, _mixed_findings(), 10, None, ordering="severity")


@pytest.mark.parametrize("ordering", [None, "legacy_severity_v0", "review_order_v1"])
def test_ties_keep_input_order_deterministically(tmp_path, monkeypatch, ordering):
    cond = Condition("width_x", "width", 30)
    _make_condition(tmp_path, monkeypatch, cond.name, MIXED_RECORD)
    # 한 유형뿐이고 비율이 낮아 승격 없음 → 심각도 그대로, 전부 동점
    findings = [_f("a.png", 0, "height", 0.5), _f("a.png", 1, "height", 0.5),
                _f("b.png", 0, "height", 0.5)]
    rows = [E.score_findings(cond, findings, 100, None, ordering=ordering) for _ in range(2)]
    assert rows[0]["verdicts_by_rank"] == rows[1]["verdicts_by_rank"]
    # 동점은 진단이 낸 순서(이미지 이름 → 이미지 안 순서)를 그대로 둔다
    assert [v[0] for v in rows[0]["verdicts_by_rank"]] == [True, True, True]
    assert rows[0]["present_types"] == []


def test_population_truth_rows(tmp_path, monkeypatch):
    cond = Condition("duplicate_x", "duplicate", 30)
    # a: 복제본 인덱스 2(원본 1). b: 지운 박스 (0.5,0.5,0.2,0.2) → 픽셀 40~60
    record = {"a": {"errored": [2], "dropped": []},
              "b": {"errored": [], "dropped": [[0.5, 0.5, 0.2, 0.2]]}}
    _make_condition(tmp_path, monkeypatch, cond.name, record)
    population = {
        "all_labels": [
            {"image": "a.png", "label_index": 0, "label_iou": 0.9},
            {"image": "a.png", "label_index": 1, "label_iou": 0.8},
            {"image": "a.png", "label_index": 2, "label_iou": 0.8},
            {"image": "b.png", "label_index": 0, "label_iou": 0.0},
        ],
        "unmatched_predictions": [
            {"image": "b.png", "label_index": None, "box": [41.0, 41.0, 60.0, 60.0],
             "confidence": 0.7},
            {"image": "b.png", "label_index": None, "box": [0.0, 0.0, 10.0, 10.0],
             "confidence": 0.9},
        ],
        "objectlab": {"available": False},
    }
    out = E.label_population_truth(cond, population)
    assert [r["injected_error"] for r in out["all_labels"]] == [False, True, True, False]
    assert [r["matches_dropped"] for r in out["unmatched_predictions"]] == [True, False]
    assert out["objectlab"] == {"available": False}
    # 원본 행은 고치지 않는다
    assert "injected_error" not in population["all_labels"][0]


def test_score_condition_population_off_by_default(tmp_path, monkeypatch):
    import diagnose_labels
    cond = Condition("width_x", "width", 30)
    _make_condition(tmp_path, monkeypatch, cond.name, MIXED_RECORD)
    calls = []

    def fake_run(images_dir, labels_dir, limit, weights=None, collect_population=False):
        calls.append(collect_population)
        fit = {"matched_labels": 8, "predictions": 9, "confidences": []}
        if collect_population:
            pop = {"all_labels": [{"image": "a.png", "label_index": 0, "label_iou": 0.5}],
                   "unmatched_predictions": [], "objectlab": {"available": False}}
            return _mixed_findings(), 10, fit, pop
        return _mixed_findings(), 10, fit

    monkeypatch.setattr(diagnose_labels, "run", fake_run)
    off = E.score_condition(cond, None)
    on = E.score_condition(cond, None, collect_population=True)
    assert calls == [False, True]
    assert "population" not in off and "ordering" not in off
    assert on["population"]["all_labels"] == [
        {"image": "a.png", "label_index": 0, "label_iou": 0.5, "injected_error": True}]
    on.pop("population")
    assert on == off
