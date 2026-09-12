"""방법 간 짝지은 차이 (docs/evaluation-protocol.md).

**개별 구간의 겹침으로 판정하지 않는다.** 같은 이미지에서 두 방법을 다 재므로
상관이 있고, 개별 구간은 그 상관을 버린다. 차이를 직접 계산한다.

**두 방법이 같은 후보 집합을 봐야 한다.** 후보가 다르면 그것은 "정렬 효과"가
아니라 "작업 전체 효과"이고, 규약이 둘을 갈라 적으라고 한 바로 그 구분이다.
"""
from .schema import Adjudication, Ranking, ValidationError
from .summary import summarise


def _keys_of(rankings: list[Ranking], method: str) -> set[str]:
    return {r.candidate_key for r in rankings if r.method == method}


def check_same_candidate_set(rankings: list[Ranking], method: str,
                             baseline: str) -> None:
    """두 방법이 같은 후보를 봤는가.

    다르면 **거부한다.** 다른 후보 집합으로 낸 차이를 "정렬 효과"라고 부르면
    순서가 아니라 후보 생성의 차이를 재게 된다.
    """
    if method == baseline:
        raise ValidationError(f"같은 방법끼리 견줄 수 없다: {method!r}")

    a, b = _keys_of(rankings, method), _keys_of(rankings, baseline)
    if not a:
        raise ValidationError(f"그 방법의 순위가 하나도 없다: {method!r}")
    if not b:
        raise ValidationError(f"기준선의 순위가 하나도 없다: {baseline!r}")
    if a != b:
        only_a, only_b = sorted(a - b)[:3], sorted(b - a)[:3]
        raise ValidationError(
            f"두 방법의 후보 집합이 다르다 ({method}만 {len(a - b)}개, "
            f"{baseline}만 {len(b - a)}개). 정렬 효과는 같은 후보 안에서만 잰다 "
            f"— 후보가 다르면 작업 전체 효과이므로 따로 재야 한다. "
            f"예: {only_a} / {only_b}")


def paired_difference(adjudications: list[Adjudication], rankings: list[Ranking],
                      method: str, baseline: str,
                      budget: int | None = None) -> dict:
    """같은 후보 집합에서 두 방법의 성과 차이.

    주지표는 **고정 예산에서 찾은 고유 오류 수**다.

    여기서 `budget`은 **"각 방법이 상위 몇 건까지 검수하는가"** 로, 평가에
    들어가는 입력이다. `activity.capacity_from_blocks`가 내는
    `N_capacity`(시간 예산으로 처리 가능한 후보 수)와 **다른 것이다** —
    시간이 되니까 그 숫자를 여기에 넣으면 표본 크기를 일정이 정하게 된다.
    docs/capacity-vs-sample-size.md를 보고 `N_final`이 정해진 뒤에 넣는다.
    """
    check_same_candidate_set(rankings, method, baseline)
    a = summarise(adjudications, rankings, method, budget)
    b = summarise(adjudications, rankings, baseline, budget)
    return {
        "method": method, "baseline": baseline, "budget": budget,
        "method_unique_errors": a.unique_error_yield,
        "baseline_unique_errors": b.unique_error_yield,
        "difference": a.unique_error_yield - b.unique_error_yield,
        "method_summary": a.as_dict(), "baseline_summary": b.as_dict(),
    }
