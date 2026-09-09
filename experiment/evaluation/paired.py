"""방법 간 짝지은 차이 (docs/evaluation-protocol.md).

**개별 구간의 겹침으로 판정하지 않는다.** 같은 이미지에서 두 방법을 다 재므로
상관이 있고, 개별 구간은 그 상관을 버린다. 차이를 직접 계산한다.
"""
from .schema import Judgement
from .summary import summarise


def _rows_of(rows: list[Judgement], method: str) -> list[Judgement]:
    return [r for r in rows if r.method == method]


def paired_difference(rows: list[Judgement], method: str, baseline: str,
                      budget: int | None = None) -> dict:
    """같은 후보 집합에서 두 방법의 성과 차이.

    주지표는 **고정 예산에서 찾은 고유 오류 수**다.
    """
    a = summarise(_rows_of(rows, method), budget)
    b = summarise(_rows_of(rows, baseline), budget)
    return {
        "method": method, "baseline": baseline, "budget": budget,
        "method_unique_errors": a.unique_errors,
        "baseline_unique_errors": b.unique_errors,
        "difference": a.unique_errors - b.unique_errors,
        "method_summary": a.as_dict(), "baseline_summary": b.as_dict(),
    }
