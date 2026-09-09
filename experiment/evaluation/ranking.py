"""결정론적 순위와 동점 처리 (docs/evaluation-protocol.md).

**동점을 라이브러리에 맡기지 않는다.** 정렬이 안정적이어도 입력 순서가 다르면
결과가 달라진다 — 재표집할 때마다 순서가 바뀌므로 그러면 부트스트랩이 흔들린다.
"""
from .schema import Adjudication, Ranking


def rank_candidates(rankings: list[Ranking],
                    by_key: dict[str, Adjudication]) -> list[Ranking]:
    """심각도 내림차순. 같으면 **이미지 이름 · 후보 id 순**으로 자른다.

    규약 5절의 동점 규칙이다. 입력 행 순서에 기대지 않는다.
    """
    def order(r: Ranking) -> tuple:
        a = by_key[r.candidate_key]
        return (-r.severity, a.image_id, a.candidate_id)

    return sorted(rankings, key=order)


def top_n(rankings: list[Ranking], by_key: dict[str, Adjudication],
          n: int | None) -> list[Ranking]:
    """검수 예산 N건. `None`이면 전부, `0`이면 아무것도 안 본다."""
    ordered = rank_candidates(rankings, by_key)
    return ordered if n is None else ordered[:n]
