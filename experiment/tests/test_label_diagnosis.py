"""label_diagnosis.py의 박스 대조 로직(순수 함수, GPU/모델 불필요) 단위 테스트.

error_injector.py의 변형 함수를 그대로 써서 "주입한 오류를 도로 찾아내는가"를
검증한다 — 실제 파이프라인과 같은 방식으로 만들어진 오류라야 의미가 있다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from error_injector import (  # noqa: E402
    apply_height,
    apply_scale,
    apply_translation_x,
    apply_translation_y,
    apply_width,
)
from label_diagnosis import (  # noqa: E402
    classify_geometry,
    diagnose_image,
    iou,
    match_boxes,
    summarize,
)

# width=100, height=50인 기준 박스 (test_error_injector.py와 같은 규약)
PRED = (0.0, 0.0, 100.0, 50.0)


# ── IoU / 매칭 ──────────────────────────────────────────────────────────────

def test_iou_identical_boxes_is_one():
    assert iou(PRED, PRED) == pytest.approx(1.0)


def test_iou_disjoint_boxes_is_zero():
    assert iou(PRED, (200.0, 200.0, 300.0, 250.0)) == pytest.approx(0.0)


def test_match_boxes_pairs_overlapping_and_reports_leftovers():
    preds = [PRED, (200.0, 0.0, 300.0, 50.0)]
    labels = [PRED]  # 두 번째 예측은 짝이 없어야 함
    matched, unmatched_preds, unmatched_labels = match_boxes(preds, labels)
    assert matched == {0: 0}
    assert unmatched_preds == [1]
    assert unmatched_labels == []


def test_match_boxes_is_one_to_one():
    """라벨 2개가 같은 예측에 겹쳐도 하나만 짝지어야 중복 탐지가 가능하다."""
    labels = [PRED, (5.0, 2.0, 105.0, 52.0)]  # 거의 같은 자리
    matched, _, unmatched_labels = match_boxes([PRED], labels)
    assert len(matched) == 1
    assert len(unmatched_labels) == 1


# ── 기하학적 분류: 주입한 오류를 도로 찾아내는가 ─────────────────────────────

def test_clean_label_is_not_flagged():
    assert classify_geometry(PRED, PRED) is None


def test_small_noise_is_tolerated():
    """모델 예측은 몇 %씩 흔들리므로 그 정도는 정상으로 봐야 한다."""
    slightly_off = apply_width(PRED, 5)
    assert classify_geometry(PRED, slightly_off) is None


def test_detects_width_error():
    suspicion, severity, _ = classify_geometry(PRED, apply_width(PRED, -30))
    assert suspicion == "width"
    assert severity == pytest.approx(0.30, abs=0.01)


def test_detects_height_error():
    suspicion, _, _ = classify_geometry(PRED, apply_height(PRED, 30))
    assert suspicion == "height"


def test_scale_error_reported_as_scale_not_width_or_height():
    """가로·세로가 함께 변하면 width/height 둘 다 걸리지만 scale로 불러야 한다."""
    suspicion, severity, _ = classify_geometry(PRED, apply_scale(PRED, -30))
    assert suspicion == "scale"
    assert severity == pytest.approx(0.30, abs=0.01)


def test_detects_translation_x():
    suspicion, _, _ = classify_geometry(PRED, apply_translation_x(PRED, 15))
    assert suspicion == "translation_x"


def test_detects_translation_y():
    suspicion, _, _ = classify_geometry(PRED, apply_translation_y(PRED, 15))
    assert suspicion == "translation_y"


# ── 이미지 단위 진단 ─────────────────────────────────────────────────────────

def test_missing_label_detected_when_model_is_confident():
    findings = diagnose_image("a.png", predictions=[PRED], confidences=[0.9], labels=[])
    assert [f.suspicion for f in findings] == ["missing"]
    assert findings[0].label_index is None  # 가리킬 라벨이 없음


def test_low_confidence_prediction_does_not_raise_missing():
    """모델 오탐까지 누락으로 잡으면 오진이 늘어난다."""
    findings = diagnose_image("a.png", predictions=[PRED], confidences=[0.2], labels=[])
    assert findings == []


def test_duplicate_label_detected():
    labels = [PRED, (3.0, 1.0, 103.0, 51.0)]  # 같은 객체에 라벨 2개
    findings = diagnose_image("a.png", [PRED], [0.9], labels)
    assert [f.suspicion for f in findings] == ["duplicate"]


def test_clean_image_produces_no_findings():
    findings = diagnose_image("a.png", [PRED], [0.9], [PRED])
    assert findings == []


# ── 요약 ────────────────────────────────────────────────────────────────────

def test_summarize_picks_most_common_type_as_dominant():
    findings = diagnose_image("a.png", [PRED], [0.9], [apply_scale(PRED, -30)])
    findings += diagnose_image("b.png", [PRED], [0.9], [apply_scale(PRED, -30)])
    findings += diagnose_image("c.png", [PRED], [0.9], [apply_width(PRED, -30)])
    summary = summarize(findings, total_labels=3)
    assert summary["dominant_type"] == "scale"
    assert summary["total_findings"] == 3


def test_summarize_handles_empty_dataset_without_dividing_by_zero():
    summary = summarize([], total_labels=0)
    assert summary["dominant_type"] is None
    assert summary["suspicion_ratio"] == 0.0
    assert summary["systematic"] is False


def test_concentrated_errors_are_flagged_systematic():
    """한 유형이 몰리면 계통적 오류 — 고객에게 재검수하라고 말할 근거."""
    findings = []
    for i in range(30):
        findings += diagnose_image(f"{i}.png", [PRED], [0.9], [apply_scale(PRED, -30)])
    summary = summarize(findings, total_labels=100)
    assert summary["dominant_type"] == "scale"
    assert summary["dominant_ratio"] == pytest.approx(0.30)
    assert summary["systematic"] is True


def test_scattered_noise_is_not_flagged_systematic():
    """깨끗한 데이터셋에서도 모델 예측이 흔들려 의심이 조금씩 나오는데,
    유형별로 흩어져 있으면 계통적 오류로 보면 안 된다 (clean 오탐 대응)."""
    findings = []
    findings += diagnose_image("a.png", [PRED], [0.9], [apply_width(PRED, -30)])
    findings += diagnose_image("b.png", [PRED], [0.9], [apply_height(PRED, 30)])
    findings += diagnose_image("c.png", [PRED], [0.9], [apply_translation_x(PRED, 20)])
    # 총 3건이지만 유형별로는 각 1건씩 → 100개 라벨 중 최대 유형 1%
    summary = summarize(findings, total_labels=100)
    assert summary["total_findings"] == 3
    assert summary["systematic"] is False
