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
    TYPE_RELIABILITY_NOISE,
    TYPE_RELIABILITY_PRESENT,
    classify_geometry,
    diagnose_image,
    iou,
    match_boxes,
    present_types,
    rescore,
    severity_for,
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
    # 두 번째 반환값은 원시 신호(변형률)다 — 재검수 정렬에 쓰는 severity는
    # severity_for()가 유형 신뢰도를 곱해 따로 만든다.
    suspicion, raw, _ = classify_geometry(PRED, apply_width(PRED, -30))
    assert suspicion == "width"
    assert raw == pytest.approx(0.30, abs=0.01)


def test_detects_height_error():
    suspicion, _, _ = classify_geometry(PRED, apply_height(PRED, 30))
    assert suspicion == "height"


def test_scale_error_reported_as_scale_not_width_or_height():
    """가로·세로가 함께 변하면 width/height 둘 다 걸리지만 scale로 불러야 한다."""
    suspicion, raw, _ = classify_geometry(PRED, apply_scale(PRED, -30))
    assert suspicion == "scale"
    assert raw == pytest.approx(0.30, abs=0.01)


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


def test_middling_confidence_prediction_does_not_raise_missing():
    """0.5~0.7 확신도 구간은 실측상 오탐이 진짜의 2배였다 (570건 표본).

    예전 기준(0.5)에서는 이게 누락으로 잡혀 유형 정밀도를 끌어내렸다.
    """
    findings = diagnose_image("a.png", predictions=[PRED], confidences=[0.6], labels=[])
    assert findings == []


def test_prediction_swallowed_by_existing_label_is_not_missing():
    """라벨된 차 안에 들어앉은 고확신 예측 = 중복 탐지이거나 가려진 객체.

    IoU로는 안 걸린다 — 작은 박스가 큰 박스 안에 있으면 IoU는 낮기 때문이다.
    """
    inner = (110.0, 110.0, 140.0, 140.0)
    big_label = (100.0, 100.0, 300.0, 300.0)
    findings = diagnose_image("a.png", predictions=[inner], confidences=[0.95],
                              labels=[big_label])
    assert [f.suspicion for f in findings] == []


def test_confident_prediction_beside_a_label_is_still_missing():
    """겹치지 않는 자리의 고확신 예측은 필터를 통과해야 한다."""
    far = (600.0, 600.0, 700.0, 700.0)
    findings = diagnose_image("a.png", predictions=[far], confidences=[0.95],
                              labels=[(100.0, 100.0, 300.0, 300.0)])
    assert [f.suspicion for f in findings] == ["missing"]


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


# ── 심각도(재검수 정렬 키) ───────────────────────────────────────────────────
# 초기 버전은 유형별 원시 신호(누락=확신도, 크기=변형률)를 그대로 severity로
# 썼는데, 단위가 서로 달라 확신도 0.9대인 누락 의심이 목록 상단을 점령했다.
# 정작 누락은 유형별 정밀도가 가장 낮아서(27%) 상위 10% 정밀도가 28.5%로
# 전체 평균(58.9%)보다 낮아지는 역전이 일어났다. 아래 테스트들이 그 회귀를 막는다.
#
# 주의: "누락이 항상 꼴찌"를 테스트로 굳히지 않는다. 누락 판정에 필터를 넣은
# 뒤 정밀도가 27% → 98.5%로 뒤집혀서, 그런 테스트는 개선을 막는 족쇄가 됐다.
# 지켜야 할 성질은 유형 순위가 아니라 **심각도가 실측 신뢰도를 따른다**는 것이다.

def test_severity_is_comparable_across_types():
    """신뢰도 낮은 유형은 신호가 최대여도 신뢰도 높은 유형의 최소보다 낮아야 한다."""
    low, high = "width", "duplicate"  # 실측 0.20 vs 0.69 (부재 시)
    assert TYPE_RELIABILITY_NOISE[low] < TYPE_RELIABILITY_NOISE[high]
    assert severity_for(low, 1.0) < severity_for(high, 0.5)


def test_severity_orders_by_type_reliability():
    """같은 신호 세기라면 신뢰도 순서가 그대로 심각도 순서가 된다."""
    ranked = sorted(TYPE_RELIABILITY_NOISE, key=lambda t: -TYPE_RELIABILITY_NOISE[t])
    severities = [severity_for(t, 1.0) for t in ranked]
    assert severities == sorted(severities, reverse=True)


def test_severity_rises_with_signal_within_a_type():
    """같은 유형 안에서는 더 크게 어긋난 박스가 먼저 와야 한다."""
    assert severity_for("scale", 0.40) > severity_for("scale", 0.15)


def test_severity_never_exceeds_type_reliability():
    """심각도는 '진짜 오류일 가능성' 추정치이므로 유형 신뢰도를 넘을 수 없다."""
    for suspicion, reliability in TYPE_RELIABILITY_NOISE.items():
        assert severity_for(suspicion, 999.0) <= reliability + 1e-9
    for suspicion, reliability in TYPE_RELIABILITY_PRESENT.items():
        assert severity_for(suspicion, 999.0, is_present=True) <= reliability + 1e-9


def test_queue_order_follows_measured_reliability():
    """실제 대기열 정렬이 유형 신뢰도 순서를 따르는지.

    누락(필터 후 0.88)이 가로 길이 오류(0.20)보다 위에 와야 한다. 예전에는
    반대로 단언했는데, 그건 필터 전 누락 정밀도가 27%였기 때문이다.
    """
    findings = diagnose_image("a.png", [PRED], [0.99], [])  # 확신도 높은 누락
    findings += diagnose_image("b.png", [PRED], [0.9], [apply_width(PRED, -30)])
    ranked = sorted(findings, key=lambda f: -f.severity)
    assert [f.suspicion for f in ranked] == ["missing", "width"]


# ── rescore: 데이터셋 전체를 본 뒤 대표 유형의 심각도를 올린다 ────────────────
# 전역 상수 하나로는 "이 유형이 미더운가"와 "이 유형이 있기는 한가"가 뒤섞인다.
# 실측: 누락 의심은 대표 유형일 때 82.9%, 아닐 때 4.3%로 20배 가까이 갈린다.

def _missing_findings(n: int):
    findings = []
    for i in range(n):
        findings += diagnose_image(f"{i}.png", [PRED], [0.9], [])
    return findings


def test_rescore_promotes_dominant_type():
    """계통적 누락 데이터셋이면 누락 의심의 심각도가 올라가야 한다."""
    findings = _missing_findings(30)
    summary = summarize(findings, total_labels=100)
    assert summary["dominant_type"] == "missing" and summary["systematic"]

    before = findings[0].severity
    after = rescore(findings, summary)[0].severity
    assert after > before


def test_rescore_leaves_non_systematic_dataset_alone():
    """대표 유형 판정이 미덥지 않으면 건드리지 않는다 — 깨끗한 데이터셋 보호."""
    findings = _missing_findings(3)
    summary = summarize(findings, total_labels=100)
    assert summary["systematic"] is False
    assert rescore(findings, summary) == findings


def test_rescore_leaves_noise_level_types_alone():
    """계통적 수준에 못 미치는 유형은 그대로 둔다 — 오탐을 밀어올리면 안 된다."""
    findings = _missing_findings(30)
    findings += diagnose_image("x.png", [PRED], [0.9], [apply_scale(PRED, -30)])
    summary = summarize(findings, total_labels=100)

    rescored = rescore(findings, summary)
    for before, after in zip(findings, rescored):
        if before.suspicion in present_types(summary):
            assert after.severity > before.severity
        else:
            assert after.severity == before.severity


def test_rescore_changes_only_severity():
    """판정 자체(개수·유형·위치)는 그대로여야 한다 — 순서만 바꾸는 단계다."""
    findings = _missing_findings(30)
    summary = summarize(findings, total_labels=100)
    rescored = rescore(findings, summary)

    assert len(rescored) == len(findings)
    for before, after in zip(findings, rescored):
        assert (after.image, after.label_index, after.suspicion, after.detail, after.box) == \
               (before.image, before.label_index, before.suspicion, before.detail, before.box)


def test_rescore_promotes_secondary_present_type_too():
    """1등이 아니어도 계통적 수준으로 존재하면 승격해야 한다.

    혼합 오류 실측에서 2차 유형도 존재하기만 하면 대표 유형만큼 미더웠다
    (누락: 대표일 때 82.9% / 2차일 때 71.2%). 1등만 승격시키면 두 번째 오류가
    노이즈 신뢰도(누락 4%)로 목록 바닥에 깔린다.
    """
    findings = []
    for i in range(30):  # 대표: 스케일 30%
        findings += diagnose_image(f"s{i}.png", [PRED], [0.9], [apply_scale(PRED, -30)])
    for i in range(15):  # 2차: 가로 15% — 1등은 아니지만 임계값(12%)은 넘는다
        findings += diagnose_image(f"w{i}.png", [PRED], [0.9], [apply_width(PRED, -30)])

    summary = summarize(findings, total_labels=100)
    assert summary["dominant_type"] == "scale"
    assert present_types(summary) == {"scale", "width"}

    before = {f.suspicion: f.severity for f in findings}
    rescored = rescore(findings, summary)
    after = {f.suspicion: f.severity for f in rescored}
    assert after["width"] > before["width"]  # 2차 유형도 올라간다
    assert after["scale"] > before["scale"]
