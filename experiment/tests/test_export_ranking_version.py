"""순위 버전이 다른 내보내기를 한 집계에 섞지 않는다 (docs/adr-ranking-separation.md).

버전 기록이 없는 옛 내보내기(prelim1 등)는 v1이 만든 것이다 — v2 전에는 v1뿐이었다.
"""
import pytest

from evaluation import importer
from evaluation.importer import load_export, load_exports
from evaluation.schema import ValidationError

V1 = "aida_v1_systematic_boost"
V2 = "aida_v2_candidate_iou"


def export(dataset_id, ranking_version=None):
    data = {
        "schema_version": 1, "evaluation_id": "e1", "dataset_id": dataset_id,
        "snapshot_hash": "h", "methods": ["aida"],
        "requested_scope": "labelled_candidates", "comparison_allowed": True,
        "comparison_limitation": "", "descriptive_only": False,
        "adjudications": [{"canonical_candidate_id": "La", "image": "a.jpg",
                           "label_index": 0, "suspicion": "width", "verdict": "hit",
                           "unique_error_id": "a.jpg/L0", "group_id": None,
                           "complete": True}],
        "rankings": [{"method": "aida", "canonical_candidate_id": "La", "severity": -1.0}],
    }
    if ranking_version is not None:
        data["ranking_version"] = ranking_version
    return data


def test_버전이_다른_내보내기는_합치지_않는다():
    with pytest.raises(ValidationError, match="순위 버전"):
        load_exports([export("d1", V1), export("d2", V2)])


def test_기록이_없는_옛_내보내기는_v1과_합칠_수_있다():
    adjudications, _ = load_exports([export("d1"), export("d2", V1)])
    assert len(adjudications) == 2


def test_기록이_없는_옛_내보내기는_v2와_합치지_않는다():
    with pytest.raises(ValidationError, match="순위 버전"):
        load_exports([export("d1"), export("d2", V2)])


def test_모르는_순위_버전은_읽지_않는다():
    with pytest.raises(ValidationError, match="순위 버전"):
        load_export(export("d1", "aida_v3"))


def test_내보내기의_순위_버전을_읽어_준다():
    assert importer.ranking_version_of(export("d1")) == V1
    assert importer.ranking_version_of(export("d1", V2)) == V2


def test_집계와_진단_코드의_버전_이름이_같다():
    import label_diagnosis as L
    assert (importer.RANKING_V1, importer.RANKING_V2) == (L.RANKING_V1, L.RANKING_V2) == (V1, V2)
