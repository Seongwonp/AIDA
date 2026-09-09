"""판정 화면의 내보내기 → 집계 입력 (evaluation/importer.py).

이 어댑터는 **두 세계의 유일한 연결점**이다. 여기서 조용히 기본값을 채우면
집계가 검증한 규약이 무의미해진다 — 그래서 빠진 것은 멈추는지를 본다.
"""
import pytest

from evaluation.importer import load_export, load_exports
from evaluation.schema import ValidationError
from evaluation.summary import summarise


def export(*rows, dataset_id="d1", methods=("aida",), version=1):
    """`rows`는 (image, candidate_id, label_index, suspicion, verdict, uid, sev)."""
    return {
        "schema_version": version,
        "evaluation_id": "e1",
        "dataset_id": dataset_id,
        "snapshot_hash": "h",
        "methods": list(methods),
        "adjudications": [
            {"canonical_candidate_id": cid, "image": im, "label_index": li,
             "suspicion": s, "verdict": v, "unique_error_id": uid,
             "group_id": None, "complete": v is not None}
            for im, cid, li, s, v, uid, _ in rows
        ],
        "rankings": [
            {"method": m, "canonical_candidate_id": cid, "severity": sev}
            for m in methods
            for _, cid, _, _, _, _, sev in rows
        ],
    }


def test_같은_라벨을_두_유형이_맞혀도_고유_오류는_하나다():
    """중복 지목이 성과로 세어지면 안 된다."""
    data = export(("a.jpg", "Laaa", 3, "width", "hit", "a.jpg/L3", 0.9),
                  ("a.jpg", "Lbbb", 3, "scale", "hit", "a.jpg/L3", 0.8))
    adjudications, rankings = load_export(data)
    result = summarise(adjudications, rankings, "aida", budget=2)
    assert result.hit_candidates == 2
    assert result.unique_error_yield == 1


def test_데이터셋_이름을_바꿔_넣을_수_있다():
    """업로드 id 대신 읽을 수 있는 이름으로 집계한다."""
    adjudications, _ = load_export(export(
        ("a.jpg", "Laaa", 0, "width", "hit", "a.jpg/L0", 0.9)), "kitti")
    assert adjudications[0].dataset_id == "kitti"
    assert adjudications[0].cluster == "kitti/a.jpg"


def test_모르는_판이면_멈춘다():
    """모양이 바뀐 파일을 옛 규칙으로 읽으면 조용히 다른 것을 센다."""
    with pytest.raises(ValidationError, match="판"):
        load_export(export(("a.jpg", "Laaa", 0, "w", None, None, 0.1),
                           version=99))


def test_누락_hit인데_오류_id가_없으면_멈춘다():
    """어댑터가 후보 id로 대신 채우지 않는다."""
    with pytest.raises(ValidationError, match="고유 오류 id"):
        load_export(export(("a.jpg", "Cxxx", None, "missing", "hit", None, 0.9)))


def test_판정에_없는_후보에_점수가_붙으면_멈춘다():
    data = export(("a.jpg", "Laaa", 0, "width", "hit", "a.jpg/L0", 0.9))
    data["rankings"].append({"method": "aida",
                             "canonical_candidate_id": "없는것",
                             "severity": 0.5})
    with pytest.raises(ValidationError, match="없는 후보"):
        load_export(data)


def test_라벨_인덱스와_오류_id가_어긋나면_멈춘다():
    with pytest.raises(ValidationError, match="어긋난다"):
        load_export(export(
            ("a.jpg", "Laaa", 0, "width", "hit", "a.jpg/L7", 0.9)))


def test_필수_항목이_빠지면_멈춘다():
    data = export(("a.jpg", "Laaa", 0, "width", "hit", "a.jpg/L0", 0.9))
    del data["adjudications"][0]["image"]
    with pytest.raises(ValidationError, match="image"):
        load_export(data)


def test_여러_평가를_합칠_때_이름이_겹치면_멈춘다():
    """겹치면 서로 다른 데이터셋의 묶음이 한 묶음으로 합쳐져 재표집이 틀린다."""
    one = export(("a.jpg", "Laaa", 0, "width", "hit", "a.jpg/L0", 0.9))
    two = export(("b.jpg", "Lbbb", 0, "width", "hit", "b.jpg/L0", 0.8))
    with pytest.raises(ValidationError, match="겹친다"):
        load_exports([one, two])


def test_여러_평가를_다른_이름으로_합친다():
    one = export(("a.jpg", "Laaa", 0, "width", "hit", "a.jpg/L0", 0.9))
    two = export(("b.jpg", "Lbbb", 0, "width", "hit", "b.jpg/L0", 0.8))
    adjudications, rankings = load_exports([one, two], ["kitti", "coco"])
    assert {a.dataset_id for a in adjudications} == {"kitti", "coco"}
    assert {a.cluster for a in adjudications} == {"kitti/a.jpg", "coco/b.jpg"}
    assert len(rankings) == 2


def test_다른_데이터셋의_같은_후보_이름이_한_후보로_안_섞인다():
    """후보 이름이 같아도 데이터셋이 다르면 다른 후보다."""
    one = export(("a.jpg", "Laaa", 0, "width", "hit", "a.jpg/L0", 0.9))
    two = export(("a.jpg", "Laaa", 0, "width", "hit", "a.jpg/L0", 0.8))
    adjudications, _ = load_exports([one, two], ["kitti", "coco"])
    assert len({a.key for a in adjudications}) == 2
