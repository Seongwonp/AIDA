"""재검수 순위 버전 — v1(계통 유형 승격)과 v2(후보 단위 신호) (docs/adr-ranking-separation.md).

**기대값은 손으로 적었다.** 구현 함수로 기대값을 만들면 구현이 틀려도 같이 틀린다.

세계(아래 `world`) — 데이터셋 요약에서 width가 계통 유형(비율 0.30)이다.

| 후보 | 층 | 유형 | 심각도 | label_iou | 1 − IoU |
|---|---|---|---|---|---|
| A | 기존 | width | 0.30 | 0.90 | 0.10 |
| B | 기존 | scale | 0.50 | 0.20 | 0.80 |
| C | 기존 | height | 0.40 | 0.55 | 0.45 |
| M | 누락 | missing | 0.70 | — | — |

- v1: width를 통째로 먼저 → A, 그 뒤 심각도 순 M(0.70), B(0.50), C(0.40).
- v2 기존 층: 1 − IoU 순 B, C, A. 누락 층: M. 화면 목록은 층 순위를 번갈아 → B, M, C, A.
"""
import itertools
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import label_diagnosis as L  # noqa: E402

V1 = "aida_v1_systematic_boost"
V2 = "aida_v2_candidate_iou"


def f(image, label_index, suspicion, severity, label_iou=None):
    return L.BoxFinding(image=image, label_index=label_index, suspicion=suspicion,
                        severity=severity, detail="", box=(0.0, 0.0, 10.0, 10.0),
                        raw_signal=0.3, confidence=0.9, label_iou=label_iou)


def summary_of(ratios: dict) -> dict:
    return {"by_type": [{"suspicion": k, "ratio": v} for k, v in ratios.items()]}


WIDTH_SYSTEMATIC = summary_of({"width": 0.30, "scale": 0.02, "height": 0.02, "missing": 0.02})
NOTHING_SYSTEMATIC = summary_of({"width": 0.04, "scale": 0.035, "height": 0.03, "missing": 0.03})


def world():
    return [f("a.png", 0, "width", 0.30, 0.90),
            f("b.png", 0, "scale", 0.50, 0.20),
            f("c.png", 0, "height", 0.40, 0.55),
            f("d.png", None, "missing", 0.70)]


def names(ranked):
    return [{"a.png": "A", "b.png": "B", "c.png": "C", "d.png": "M"}[x.image] for x in ranked]


# ── 버전 이름과 메타데이터 ────────────────────────────────────────────────────

def test_버전_이름은_고정된_문자열이다():
    assert L.RANKING_V1 == V1
    assert L.RANKING_V2 == V2
    assert L.LEGACY_RANKING_VERSION == V1


def test_v1은_데이터셋_승격이_순서를_바꾼다고_적고_v2는_아니라고_적는다():
    one, two = L.ranking_metadata(V1), L.ranking_metadata(V2)
    assert (one["ranking_version"], one["dataset_boost_affects_order"]) == (V1, True)
    assert (two["ranking_version"], two["dataset_boost_affects_order"]) == (V2, False)
    assert one["ranking_scope"] == "mixed_queue"
    assert two["ranking_scope"] == "per_layer"
    assert two["ranking_signal"] == {"labelled_candidates": "1 - label_iou",
                                     "missing_candidates": "severity"}
    assert one["tie_break_rule"] and two["tie_break_rule"]
    assert one["tie_break_rule"] != two["tie_break_rule"]


def test_모르는_버전은_거부한다():
    with pytest.raises(L.RankingError):
        L.ranking_metadata("aida_v3")
    with pytest.raises(L.RankingError):
        L.rank_findings(world(), WIDTH_SYSTEMATIC, "aida_v3")


# ── v1은 역사적 동작 그대로 ──────────────────────────────────────────────────

def test_v1은_계통_유형을_통째로_먼저_둔다():
    assert names(L.rank_findings(world(), WIDTH_SYSTEMATIC, V1)) == ["A", "M", "B", "C"]


def test_v1은_계통_유형이_없으면_심각도_순이다():
    assert names(L.rank_findings(world(), NOTHING_SYSTEMATIC, V1)) == ["M", "B", "C", "A"]


# ── v2: 데이터셋 요약이 후보 순서를 바꾸지 않는다 ─────────────────────────────

def test_계통_유형이_바뀌어도_v2_순서는_그대로다():
    with_boost = names(L.rank_findings(world(), WIDTH_SYSTEMATIC, V2))
    without = names(L.rank_findings(world(), NOTHING_SYSTEMATIC, V2))
    assert with_boost == without == ["B", "M", "C", "A"]


def test_v2는_심각도를_다시_매기지_않는다():
    """데이터셋 판정으로 후보 점수를 바꾸면 그것도 승격이다."""
    ranked = L.rank_findings(world(), WIDTH_SYSTEMATIC, V2)
    assert {x.image: x.severity for x in ranked} == {
        "a.png": 0.30, "b.png": 0.50, "c.png": 0.40, "d.png": 0.70}


def test_v2_기존_층은_1_빼기_IoU_순이다():
    labelled = [x for x in L.rank_findings(world(), WIDTH_SYSTEMATIC, V2)
                if x.label_index is not None]
    assert names(labelled) == ["B", "C", "A"]


def test_v2는_label_iou가_없는_기존_라벨_후보를_지어내지_않고_멈춘다():
    broken = world() + [f("e.png", 0, "width", 0.9, None)]
    with pytest.raises(L.RankingError):
        L.rank_findings(broken, WIDTH_SYSTEMATIC, V2)


def test_v2_동점은_이미지_라벨_유형_순으로_입력_순서와_무관하다():
    tied = [f("b.png", 1, "width", 0.1, 0.5),
            f("a.png", 2, "scale", 0.9, 0.5),
            f("a.png", 0, "width", 0.5, 0.5),
            f("a.png", 0, "height", 0.2, 0.5)]
    expected = [("a.png", 0, "height"), ("a.png", 0, "width"),
                ("a.png", 2, "scale"), ("b.png", 1, "width")]
    for perm in itertools.permutations(tied):
        got = [(x.image, x.label_index, x.suspicion)
               for x in L.rank_findings(list(perm), NOTHING_SYSTEMATIC, V2)]
        assert got == expected


def test_v2_누락_층은_심각도_순이고_기존_층_점수와_섞지_않는다():
    """누락 후보의 심각도(0.99)가 기존 후보의 1 − IoU(0.10)보다 커도 층을 건너
    앞서지 않는다 — 두 수는 다른 신호라 크기를 비교하지 않는다. 화면 목록은 층
    순위를 번갈아 놓을 뿐이다."""
    findings = [f("a.png", 0, "width", 0.3, 0.9),
                f("z.png", None, "missing", 0.60),
                f("y.png", None, "missing", 0.99)]
    ranked = L.rank_findings(findings, NOTHING_SYSTEMATIC, V2)
    assert [(x.image, x.label_index) for x in ranked] == [
        ("a.png", 0), ("y.png", None), ("z.png", None)]


# ── 결과 파일의 줄 ────────────────────────────────────────────────────────────

def test_v2_줄에는_층과_층_안_순위가_붙는다():
    rows = L.candidate_rows(L.rank_findings(world(), WIDTH_SYSTEMATIC, V2), [], V2)
    assert [(r["image"], r["rank"], r["layer"], r["layer_rank"]) for r in rows] == [
        ("b.png", 1, "labelled_candidates", 1),
        ("d.png", 2, "missing_candidates", 1),
        ("c.png", 3, "labelled_candidates", 2),
        ("a.png", 4, "labelled_candidates", 3)]
    assert [r["priority_score"] for r in rows] == [0.8, 0.7, 0.45, 0.1]


def test_v1_줄의_층_안_순위는_v1_순서를_따른다():
    rows = L.candidate_rows(L.rank_findings(world(), WIDTH_SYSTEMATIC, V1), [], V1)
    assert [(r["image"], r["layer"], r["layer_rank"]) for r in rows] == [
        ("a.png", "labelled_candidates", 1),
        ("d.png", "missing_candidates", 1),
        ("b.png", "labelled_candidates", 2),
        ("c.png", "labelled_candidates", 3)]
    assert all("priority_score" not in r for r in rows)


# ── 파일 이름과 덮어쓰기 ─────────────────────────────────────────────────────

def test_버전마다_결과_파일이_따로다():
    assert L.diagnosis_filename(V1) == "label_diagnosis.json"
    assert L.diagnosis_filename(V2) == "label_diagnosis.aida_v2_candidate_iou.json"


def test_버전_기록이_없는_옛_결과는_v1로_읽는다():
    assert L.ranking_version_of({"summary": {}}) == V1
    assert L.ranking_version_of({"ranking": {"ranking_version": V2}}) == V2
    with pytest.raises(L.RankingError):
        L.ranking_version_of({"ranking": {"ranking_version": "aida_v9"}})


def test_다른_버전의_결과를_덮어쓰지_않는다(tmp_path):
    path = tmp_path / "label_diagnosis.json"
    path.write_text(json.dumps({"summary": {}}), encoding="utf-8")   # 옛 v1
    with pytest.raises(L.RankingError):
        L.refuse_cross_version_overwrite(path, V2)
    L.refuse_cross_version_overwrite(path, V1)                          # 같은 버전은 된다
    L.refuse_cross_version_overwrite(tmp_path / "없음.json", V2)        # 없으면 된다


def test_읽을_수_없는_기존_결과도_덮어쓰지_않는다(tmp_path):
    path = tmp_path / "label_diagnosis.json"
    path.write_text("{깨짐", encoding="utf-8")
    with pytest.raises(L.RankingError):
        L.refuse_cross_version_overwrite(path, V1)


def test_진단_실행기가_버전별_순서와_파일을_쓴다():
    src = (Path(__file__).resolve().parent.parent / "diagnose_labels.py").read_text(encoding="utf-8")
    assert "rank_findings(findings, summary, ranking)" in src
    assert "diagnosis_filename(args.ranking)" in src
    assert "refuse_cross_version_overwrite(out_path, args.ranking)" in src
    assert '"ranking": ranking_metadata(ranking)' in src
