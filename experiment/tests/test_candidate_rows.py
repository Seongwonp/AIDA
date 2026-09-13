"""진단 결과 파일의 후보 줄 (label_diagnosis.candidate_rows).

`review_queue`(화면용 상위 N건)와 `all_candidates`(평가가 얼리는 전부)가 같은
함수로 만들어진다. 둘이 어긋나면 평가가 얼린 후보와 화면의 후보가 달라진다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from label_diagnosis import BoxFinding, candidate_rows  # noqa: E402

BOX = (1.04, 2.0, 3.0, 4.0)


def finding(image, label_index, suspicion, severity, label_iou=None, class_id=None):
    return BoxFinding(image, label_index, suspicion, severity, "", BOX,
                      0.3, 0.9, class_id, label_iou)


def test_순위는_받은_순서대로_1부터다():
    """심각도로 다시 줄 세우지 않는다 — 순서는 `review_order`가 이미 정했다."""
    rows = candidate_rows([finding("a.png", 0, "width", 0.5),
                           finding("b.png", 1, "class_mismatch", 0.99)], [])
    assert [(r["rank"], r["image"]) for r in rows] == [(1, "a.png"), (2, "b.png")]


def test_잘라서_만든_줄은_전체의_앞부분과_같다():
    ranked = [finding(f"{i}.png", 0, "width", 1 - i / 10) for i in range(5)]
    assert candidate_rows(ranked[:2], []) == candidate_rows(ranked, [])[:2]


def test_기준선_재료와_클래스를_옮긴다():
    rows = candidate_rows([finding("a.png", 0, "width", 0.5, label_iou=0.42, class_id=1),
                           finding("a.png", None, "missing", 0.7, class_id=9)],
                          ["Car", "Pedestrian"])
    assert rows[0]["label_iou"] == 0.42 and rows[0]["class_name"] == "Pedestrian"
    assert rows[1]["label_iou"] is None and rows[1]["class_name"] is None
    assert rows[0]["box"] == [1.0, 2.0, 3.0, 4.0]
