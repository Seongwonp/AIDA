"""층별(상자 높이) 기술통계 (docs/advice-w5-2026-09-16.md).

**손계산 세계** — 이미지 하나, 후보 넷.

| 후보 | 높이 | `wide` 점수 | 판정 |
|---|---|---|---|
| s1 | 20 (0-30) | 0.9 | miss |
| s2 | 25 (0-30) | 0.8 | hit |
| m1 | 50 (30-60) | 0.7 | hold |
| t1 | 200 (120+) | 0.1 | hit |

예산 3이면 `wide`는 s1·s2·m1을 고른다 → 0-30: 2건 중 hit 1(정밀도 0.5), 30-60: 보류 1건.
t1은 예산 밖이라 어느 층에도 안 나온다. **층 안에서 다시 상위 N을 고르면** 120+에 t1이
나타난다 — 그게 틀린 계산이다.
"""
import pytest

from evaluation.importer import load_export
from evaluation.schema import Adjudication, Ranking, ValidationError
from evaluation.strata import (HEIGHT_BANDS, height_band, height_strata_from_export,
                               summarise_by_stratum)
from evaluation.summary import summarise


def box(height):
    return [0.0, 10.0, 50.0, 10.0 + height]


def test_높이_층_경계는_아래를_포함하고_위를_뺀다():
    assert height_band(box(0)) == "0-30"
    assert height_band(box(29.9)) == "0-30"
    assert height_band(box(30)) == "30-60"
    assert height_band(box(120)) == "120+"
    assert height_band(box(5000)) == "120+"


@pytest.mark.parametrize("bad", [None, [], [1, 2, 3], [0, "a", 0, 0]])
def test_상자가_없거나_틀리면_unknown(bad):
    assert height_band(bad) == "unknown"


def test_음수_높이는_어느_층에도_안_든다():
    assert height_band([0, 50, 10, 40]) == "unknown"


def world():
    rows = [("s1", 20, 0.9, "miss"), ("s2", 25, 0.8, "hit"), ("m1", 50, 0.7, "hold"),
            ("t1", 200, 0.1, "hit")]
    facts = [Adjudication("ds", "a.jpg", cid, "", verdict, i, None)
             for i, (cid, _, _, verdict) in enumerate(rows)]
    rankings = [Ranking("wide", f.key, score) for f, (_, _, score, _) in zip(facts, rows)]
    stratum_of = {f.key: height_band(box(h)) for f, (_, h, _, _) in zip(facts, rows)}
    return facts, rankings, stratum_of


def test_전체_상위_N을_고른_뒤_층으로_나눈다():
    facts, rankings, stratum_of = world()
    out = summarise_by_stratum(facts, rankings, "wide", stratum_of, budget=3)
    assert set(out) == {"0-30", "30-60"}                 # t1은 예산 밖
    assert out["0-30"]["in_budget"] == 2 and out["0-30"]["hit_candidates"] == 1
    assert out["0-30"]["candidate_precision"] == 0.5
    assert out["30-60"] == {"in_budget": 1, "judged": 1, "holds": 1, "decided": 0,
                            "hit_candidates": 0, "unique_error_yield": 0,
                            "candidate_precision": None}


def test_층_합계가_전체와_같다():
    facts, rankings, stratum_of = world()
    for budget in (1, 2, 3, 4, None):
        whole = summarise(facts, rankings, "wide", budget)
        parts = summarise_by_stratum(facts, rankings, "wide", stratum_of, budget)
        assert sum(p["in_budget"] for p in parts.values()) == whole.in_budget
        assert sum(p["hit_candidates"] for p in parts.values()) == whole.hit_candidates


def test_층이_없는_후보가_있으면_멈춘다():
    facts, rankings, stratum_of = world()
    stratum_of.pop(facts[3].key)
    with pytest.raises(ValidationError, match="층"):
        summarise_by_stratum(facts, rankings, "wide", stratum_of, budget=1)


def test_없는_방법은_멈춘다():
    facts, rankings, stratum_of = world()
    with pytest.raises(ValidationError):
        summarise_by_stratum(facts, rankings, "aida", stratum_of)


def test_내보내기의_상자로_층을_만들고_키가_load_export와_같다():
    export = {
        "schema_version": 1, "dataset_id": "ds1", "requested_scope": "labelled_candidates",
        "comparison_allowed": True,
        "adjudications": [
            {"canonical_candidate_id": "c1", "image": "a.jpg", "label_index": 0,
             "suspicion": "", "verdict": "hit", "box": box(10)},
            {"canonical_candidate_id": "c2", "image": "a.jpg", "label_index": 1,
             "suspicion": "", "verdict": "miss", "box": None},
        ],
        "rankings": [{"method": "wide", "canonical_candidate_id": "c1", "severity": 0.9},
                     {"method": "wide", "canonical_candidate_id": "c2", "severity": 0.1}],
    }
    strata = height_strata_from_export(export)
    facts, rankings = load_export(export)
    assert set(strata) == {f.key for f in facts}
    assert sorted(strata.values()) == ["0-30", "unknown"]
    assert HEIGHT_BANDS[0] == (0, 30)
