"""비교 모집단 — 모든 기존 라벨과 **필터 전** 미매칭 예측 (docs/next-work-2026-09-15.md W3).

Q-A(후보 생성 포함 비교)와 Q-C(누락 층 기준선)는 **AIDA 규칙에 걸린 후보만으로는 잴 수 없다.**
규칙이 놓친 라벨과 규칙이 버린 예측이 모집단에 있어야 한다.

**기대값은 손으로 계산했다.**

| 라벨 | 상자 | 가장 많이 겹치는 예측 | IoU |
|---|---|---|---|
| L0 | (0,0,10,10) | P0 (0,0,10,10) | 100/100 = **1.0** |
| L1 | (100,100,110,110) | P1 (100,100,105,110) | 50/(100+50−50) = **0.5** |
| L2 | (200,200,210,210) | 없음 | **0.0** |

| 예측 | 상자 | 확신도 | 짝 | AIDA 누락 후보인가 |
|---|---|---|---|---|
| P0 | (0,0,10,10) | 0.90 | L0 (IoU 1.0) | — 짝이 있다 |
| P1 | (100,100,105,110) | 0.80 | L1 (IoU 0.5) | — 짝이 있다 |
| P2 | (300,300,310,310) | 0.30 | 없음 | **아니다** — 확신도가 0.70 미만 |
| P3 | (2,2,6,6) | 0.95 | 없음 (L0과 IoU 16/100 = 0.16) | **아니다** — L0에 다 삼켜졌다(1.0 ≥ 0.7) |

그래서 AIDA 누락 후보는 0건이지만 기준선 모집단은 P2·P3 **2건**이다. 그 차이가 Q-C의 질문이다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import label_diagnosis as L  # noqa: E402

LABELS = [(0.0, 0.0, 10.0, 10.0), (100.0, 100.0, 110.0, 110.0), (200.0, 200.0, 210.0, 210.0)]
PREDS = [(0.0, 0.0, 10.0, 10.0), (100.0, 100.0, 105.0, 110.0),
         (300.0, 300.0, 310.0, 310.0), (2.0, 2.0, 6.0, 6.0)]
CONFS = [0.90, 0.80, 0.30, 0.95]


# ── 모든 기존 라벨 ────────────────────────────────────────────────────────────

def test_규칙에_안_걸린_라벨도_한_줄씩_나온다():
    rows = L.label_rows("a.png", PREDS, LABELS, label_classes=[0, 0, 0], class_names=["Car"])
    assert [(r["label_index"], r["label_iou"]) for r in rows] == [(0, 1.0), (1, 0.5), (2, 0.0)]
    assert {r["image"] for r in rows} == {"a.png"}
    assert {r["class_name"] for r in rows} == {"Car"}
    assert rows[1]["box"] == [100.0, 100.0, 110.0, 110.0]


def test_예측이_하나도_없으면_모든_라벨의_IoU가_0이다():
    rows = L.label_rows("a.png", [], LABELS)
    assert [r["label_iou"] for r in rows] == [0.0, 0.0, 0.0]
    assert [r["class_name"] for r in rows] == [None, None, None]


def test_라벨이_없으면_빈_목록이다():
    assert L.label_rows("a.png", PREDS, []) == []


def test_후보의_label_iou와_모집단의_값이_같다():
    """둘이 다르면 같은 라벨이 방법마다 다른 점수를 받는다 — 비교가 무의미해진다."""
    findings = L.diagnose_image("a.png", PREDS, CONFS, LABELS)
    rows = {r["label_index"]: r["label_iou"] for r in L.label_rows("a.png", PREDS, LABELS)}
    flagged = [f for f in findings if f.label_index is not None]
    assert flagged, "이 세계에서는 기하 오류가 하나 이상 나와야 검사가 뜻이 있다"
    for f in flagged:
        assert f.label_iou == rows[f.label_index]


# ── 필터 전 미매칭 예측 ───────────────────────────────────────────────────────

def test_AIDA가_버린_예측도_기준선_모집단에는_남는다():
    rows = L.unmatched_prediction_rows("a.png", PREDS, CONFS, LABELS,
                                       pred_classes=[0, 0, 0, 0], label_classes=[0, 0, 0],
                                       class_names=["Car"])
    assert [(r["box"], r["confidence"]) for r in rows] == [
        ([300.0, 300.0, 310.0, 310.0], 0.3),      # 확신도가 낮아 AIDA가 버린다
        ([2.0, 2.0, 6.0, 6.0], 0.95)]             # 라벨에 삼켜져 AIDA가 버린다
    assert [r["covered_ratio"] for r in rows] == [0.0, 1.0]
    assert [r["label_index"] for r in rows] == [None, None]
    assert [r["class_name"] for r in rows] == ["Car", "Car"]


def test_AIDA_누락_후보는_그_부분집합이다():
    """같은 이미지에서 AIDA는 0건, 기준선 모집단은 2건이다."""
    aida_missing = [f for f in L.diagnose_image("a.png", PREDS, CONFS, LABELS)
                    if f.label_index is None]
    pool = L.unmatched_prediction_rows("a.png", PREDS, CONFS, LABELS)
    assert len(aida_missing) == 0
    assert len(pool) == 2


def test_AIDA가_남긴_누락_후보는_같은_상자로_모집단에_있다():
    """상자가 어긋나면 두 방법의 같은 객체를 잇지 못한다."""
    preds = PREDS + [(400.0, 400.0, 410.0, 410.0)]
    confs = CONFS + [0.95]
    missing = [f for f in L.diagnose_image("a.png", preds, confs, LABELS) if f.label_index is None]
    assert [f.box for f in missing] == [(400.0, 400.0, 410.0, 410.0)]
    boxes = [r["box"] for r in L.unmatched_prediction_rows("a.png", preds, confs, LABELS)]
    assert [400.0, 400.0, 410.0, 410.0] in boxes
    assert [round(v, 1) for v in missing[0].box] in boxes


def test_짝이_다_지어지면_빈_목록이다():
    assert L.unmatched_prediction_rows("a.png", PREDS[:1], CONFS[:1], LABELS[:1]) == []


# ── 진단 실행기가 이 모집단을 결과 파일에 담는가 ──────────────────────────────

def test_진단_실행기가_모집단을_모아_결과에_담는다():
    src = (Path(__file__).resolve().parent.parent / "diagnose_labels.py").read_text(encoding="utf-8")
    assert "label_rows(" in src and "unmatched_prediction_rows(" in src
    assert '"all_labels"' in src and '"unmatched_predictions"' in src
    assert "collect_population" in src
