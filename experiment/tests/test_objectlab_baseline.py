"""ObjectLab 기준선의 입력 변환과 점수 붙이기 — cleanlab 없이 도는 부분만."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import objectlab_baseline as OL  # noqa: E402

np = pytest.importorskip("numpy")

IMAGES = [
    {"image": "a.png", "labels": [(0, 0, 10, 10), (100, 100, 110, 110)], "label_classes": None,
     "predictions": [(0, 0, 10, 10), (300, 300, 310, 310)], "confidences": [0.9, 0.95],
     "pred_classes": None},
    {"image": "b.png", "labels": [], "label_classes": None,
     "predictions": [], "confidences": [], "pred_classes": None},
]


def test_입력은_이미지마다_라벨_배열과_클래스별_예측_배열이다():
    labels, preds = OL.build_inputs(IMAGES, num_classes=1)
    assert labels[0]["bboxes"].shape == (2, 4) and labels[0]["labels"].tolist() == [0, 0]
    assert preds[0][0].shape == (2, 5) and preds[0][0][1, 4] == pytest.approx(0.95)
    assert labels[1]["bboxes"].shape == (0, 4) and preds[1][0].shape == (0, 5)


def test_다중_클래스면_예측이_클래스별로_갈린다():
    im = dict(IMAGES[0], pred_classes=[0, 1], label_classes=[0, 1])
    _, preds = OL.build_inputs([im], num_classes=2)
    assert preds[0][0].shape == (1, 5) and preds[0][1].shape == (1, 5)


def test_예측_차례는_cleanlab이_클래스별로_이어붙인_순서다():
    # cleanlab은 클래스별 배열을 이어붙여 번호를 매긴다. 예측이 클래스 순이 아니면
    # cleanlab의 i번째 점수는 원래 i번째 예측의 것이 아니다 — 그 상자에 남의 점수가
    # 붙은 적이 있어 남긴다.
    im = {"image": "a.png", "predictions": [(0, 0, 1, 1)] * 3, "pred_classes": [1, 0, 0]}
    assert OL.prediction_order(im, 2) == [1, 2, 0]
    # 클래스가 하나면 차례가 그대로다 (Car 단일 클래스 실행이 바뀌지 않는다)
    im1 = {"image": "a.png", "predictions": [(0, 0, 1, 1)] * 3, "pred_classes": None}
    assert OL.prediction_order(im1, 1) == [0, 1, 2]


def test_overlooked는_cleanlab_기본_문턱_아래_예측에_붙지_않는다():
    # 관측: 미매칭 예측 419건 전부에 점수가 없었다. cleanlab 기본
    # high_probability_threshold=0.95 아래 예측은 NaN이라 **이 방법의 모집단에 없다**.
    # 문턱을 AIDA에 맞추면 기준선이 아니므로 값을 지어내지 않는 이 동작을 고정한다.
    pytest.importorskip("cleanlab")
    base = {"image": "a.png", "labels": [(0, 0, 50, 50)], "label_classes": None,
            "predictions": [(0, 0, 50, 50), (400, 400, 460, 460)], "pred_classes": None}
    below = OL.score([dict(base, confidences=[0.99, 0.93])], 1)
    above = OL.score([dict(base, confidences=[0.99, 0.96])], 1)
    assert below["pred_scores"] == {}
    assert ("a.png", 1) in above["pred_scores"]


def test_cleanlab이_없으면_붙이지_않고_그_사실을_남긴다():
    pop = {"all_labels": [{"image": "a.png", "label_index": 0}], "unmatched_predictions": []}
    meta = OL.attach(pop, IMAGES, {"available": False, "reason": "cleanlab 없음"})
    assert meta["available"] is False and "objectlab_score" not in pop["all_labels"][0]


def test_점수는_라벨_번호와_예측_상자로_행에_붙는다():
    pop = {"all_labels": [{"image": "a.png", "label_index": 1, "box": [100.0, 100.0, 110.0, 110.0]}],
           "unmatched_predictions": [{"image": "a.png", "box": [300.0, 300.0, 310.0, 310.0]},
                                     {"image": "a.png", "box": [0.0, 0.0, 10.0, 10.0]}]}
    scored = {"available": True, "cleanlab_version": "x",
              "label_scores": {("a.png", 1): 0.3}, "pred_scores": {("a.png", 1): 0.0}}
    meta = OL.attach(pop, IMAGES, scored)
    assert pop["all_labels"][0]["objectlab_score"] == 0.3
    assert pop["unmatched_predictions"][0]["objectlab_overlooked"] == 0.0
    # NaN이었던(점수 없는) 예측에는 값을 지어내지 않는다
    assert "objectlab_overlooked" not in pop["unmatched_predictions"][1]
    assert meta["labels_scored"] == 1 and meta["predictions_scored"] == 1


def test_진단_실행기가_모집단에_objectlab_점수를_붙인다():
    src = (Path(__file__).resolve().parent.parent / "diagnose_labels.py").read_text(encoding="utf-8")
    assert "objectlab_baseline.score(" in src and "objectlab_baseline.attach(" in src
    assert '"objectlab": population.get("objectlab"' in src
