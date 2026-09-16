"""모집단이 다른 두 방법의 짝지은 차이 (docs/next-work-2026-09-15.md W3·W4).

**기본은 지금까지 그대로 거부한다** — 같은 후보를 봐야 "정렬 효과"다. 후보 생성까지
포함한 비교(Q-A)는 애초에 후보 집합이 다르고, 그때 짝지음의 단위는 **후보가 아니라
이미지 묶음**이다. 같은 이미지 표본에서 두 방법이 각자 상위 N을 고르는 것을 견준다.
그래서 요청하는 쪽이 **명시적으로** 그 뜻을 밝혀야 풀린다.

**손계산 세계** — 이미지 둘, 이미지마다 후보 둘.

| 후보 | `aida` 점수 | `all_label_iou` 점수 | 판정 |
|---|---|---|---|
| a.jpg X | 0.9 | 0.5 | miss |
| a.jpg Y | **없음** | 0.95 | hit |
| b.jpg X | 0.8 | 0.4 | miss |
| b.jpg Y | **없음** | 0.90 | hit |

검수량 1에서 `aida`는 a.jpg X(miss) → 고유 오류 0, `all_label_iou`는 a.jpg Y(hit) → 1.
차이는 1이다. 이미지 묶음을 복원추출해도 어느 조합({a,a}·{a,b}·{b,b})에서든 1이라
구간은 [1, 1]이다.
"""
import pytest

from evaluation.bootstrap import paired_cluster_bootstrap
from evaluation.paired import paired_difference
from evaluation.schema import Adjudication, Ranking, ValidationError

AIDA = "aida"
WIDE = "all_label_iou"


def world():
    facts, rankings = [], []
    for image, aida_score, wide_score in (("a.jpg", 0.9, 0.95), ("b.jpg", 0.8, 0.90)):
        flagged = Adjudication("ds", image, "x", "width", "miss", 0, None)
        unflagged = Adjudication("ds", image, "y", "", "hit", 1, f"{image}/L1")
        facts += [flagged, unflagged]
        rankings += [
            Ranking(AIDA, flagged.key, aida_score),          # 규칙 밖 후보는 AIDA 순서에 없다
            Ranking(WIDE, flagged.key, wide_score - 0.45),
            Ranking(WIDE, unflagged.key, wide_score),
        ]
    return facts, rankings


def test_기본은_후보_집합이_다르면_거부한다():
    facts, rankings = world()
    with pytest.raises(ValidationError, match="후보 집합이 다르다"):
        paired_difference(facts, rankings, WIDE, AIDA, budget=1)
    with pytest.raises(ValidationError, match="후보 집합이 다르다"):
        paired_cluster_bootstrap(facts, rankings, WIDE, AIDA, budget=1, iterations=10)


def test_후보_생성_포함이라고_밝히면_이미지_묶음으로_짝짓는다():
    facts, rankings = world()
    got = paired_difference(facts, rankings, WIDE, AIDA, budget=1,
                            require_same_candidates=False)
    assert (got["method_unique_errors"], got["baseline_unique_errors"]) == (1, 0)
    assert got["difference"] == 1
    assert got["same_candidate_set"] is False


def test_구간도_같은_방식으로_낸다():
    facts, rankings = world()
    got = paired_cluster_bootstrap(facts, rankings, WIDE, AIDA, budget=1,
                                   iterations=200, seed=42, require_same_candidates=False)
    assert (got["observed_difference"], got["ci_low"], got["ci_high"]) == (1, 1.0, 1.0)
    assert got["same_candidate_set"] is False


def test_같은_후보를_볼_때는_그_사실도_적는다():
    """기본 경로의 결과에도 무엇을 짝지었는지 남아야 한다 — 보고서가 둘을 섞지 않게."""
    facts, rankings = world()
    same = [r for r in rankings if r.method == WIDE or r.candidate_key.endswith("/x")]
    same = [r for r in same if not (r.method == WIDE and r.candidate_key.endswith("/y"))]
    got = paired_difference(facts, same, WIDE, AIDA, budget=1)
    assert got["same_candidate_set"] is True


def test_모집단이_달라도_없는_방법은_거부한다():
    """뜻을 밝혔다고 해서 순위가 없는 방법까지 통과시키지 않는다."""
    facts, rankings = world()
    with pytest.raises(ValidationError, match="순위가 하나도 없다"):
        paired_difference(facts, rankings, "없는방법", AIDA, budget=1,
                          require_same_candidates=False)
    with pytest.raises(ValidationError, match="같은 방법끼리"):
        paired_difference(facts, rankings, AIDA, AIDA, budget=1,
                          require_same_candidates=False)
