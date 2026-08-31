"""재검수 우선순위 등급 기준.

등급은 상대값이다 — "관측된 최대 저하 대비 몇 %인가". DB가 바뀌면 경계도
같이 움직인다는 게 장점이지만, 지배적인 유형 하나가 나머지를 눌러버리면
사실상 같은 값들이 경계를 사이에 두고 갈린다(docs/21 Q 한계 3번).
"""
from app.routers.report import (
    HIGH_PRIORITY_FRACTION,
    MEDIUM_PRIORITY_FRACTION,
    TIE_TOLERANCE_FRACTION,
    _review_priority,
)

WORST = 31.2  # 다중 클래스 표의 클래스 오기입


def grade(drop, worst=WORST, std=None):
    return _review_priority(drop_pct=drop, worst_overall=worst, drop_std=std)[0]


def test_near_identical_drops_get_the_same_grade():
    """0.1%p 차이로 등급이 갈리면 고객은 등급 전체를 의심하게 된다."""
    assert grade(7.8) == grade(7.7)


def test_clearly_different_drops_still_split():
    """여유가 등급 구분 자체를 없애면 안 된다."""
    assert grade(18.5) == "높음"
    assert grade(10.2) == "중간"
    assert grade(18.5) != grade(10.2)


def test_tolerance_is_too_small_to_move_the_car_table():
    """Car DB(최대 5.9%)에서는 여유가 0.12%p라 아무것도 안 움직여야 한다.

    중심점 세로 2.5%가 라벨 누락 3.8%와 같은 등급이 되면 과보정이다.
    """
    assert grade(3.8, worst=5.9) == "높음"
    assert grade(2.5, worst=5.9) == "중간"


def test_tolerance_scales_with_the_database():
    """절대값이 아니라 최대 저하 대비 비율이어야 DB가 바뀌어도 뜻이 같다."""
    small = 5.9 * TIE_TOLERANCE_FRACTION
    large = 31.2 * TIE_TOLERANCE_FRACTION
    assert large > small


def test_statistical_noise_outranks_the_grace_zone():
    """유의성 미달은 크기와 무관한 더 강한 이유다.

    옆 유형과 값이 비슷하다는 이유로 노이즈를 승격시키면 안 된다.
    """
    priority, _rationale, is_noise = _review_priority(
        drop_pct=WORST * MEDIUM_PRIORITY_FRACTION, worst_overall=WORST, drop_std=10.0)
    assert priority == "낮음" and is_noise


def test_boundaries_are_still_honoured():
    assert grade(WORST * HIGH_PRIORITY_FRACTION) == "높음"
    assert grade(WORST * MEDIUM_PRIORITY_FRACTION) == "중간"
    assert grade(WORST * MEDIUM_PRIORITY_FRACTION * 0.5) == "낮음"
