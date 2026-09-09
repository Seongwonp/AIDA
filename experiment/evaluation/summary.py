"""한 방법·한 데이터셋의 요약 (docs/evaluation-protocol.md).

**세 가지를 이름으로 갈라 센다.**

    judged                판정 완료 수 (보류 포함 — 시간을 썼다)
    hit_candidates        오류로 판정된 **후보** 수
    unique_error_yield    중복 제거한 **고유 오류** 수

처음엔 이것들을 `precision` 하나로 뭉쳤는데, 문서는 분자를 "고유 오류"라고
적어 놓고 코드는 hit 후보 수를 쓰고 있었다. **같은 오류를 두 번 지목한 것이
성과처럼 보이는** 자리다.
"""
from dataclasses import dataclass

from .ranking import top_n
from .schema import Adjudication, Ranking, ValidationError, validate_adjudications


@dataclass(frozen=True)
class Summary:
    budget: int | None          # 검수 예산 N (None이면 전부)
    in_budget: int              # 예산 안에 들어온 후보 수
    judged: int                 # 판정 완료 수 (보류 포함)
    holds: int
    decided: int                # hit + miss. 정밀도의 분모다
    hit_candidates: int         # 오류로 판정된 **후보** 수
    unique_error_yield: int     # 중복 제거한 **고유 오류** 수 — 주지표
    candidate_precision: float | None   # hit 후보 / 결정된 후보
    hold_rate: float | None

    def as_dict(self) -> dict:
        return {
            "budget": self.budget, "in_budget": self.in_budget,
            "judged": self.judged, "holds": self.holds, "decided": self.decided,
            "hit_candidates": self.hit_candidates,
            "unique_error_yield": self.unique_error_yield,
            "candidate_precision": self.candidate_precision,
            "hold_rate": self.hold_rate,
        }


def _check_budget(budget: int | None) -> None:
    if budget is None:
        return
    if not isinstance(budget, int) or isinstance(budget, bool):
        raise ValidationError(f"검수 예산은 정수다: {budget!r}")
    if budget < 0:
        raise ValidationError(f"검수 예산은 0 이상이다: {budget}")


def summarise(adjudications: list[Adjudication], rankings: list[Ranking],
              method: str, budget: int | None = None) -> Summary:
    """예산 N건까지 보고 무엇을 얻었는가.

    **검증을 여기서 한다.** 호출자가 따로 `validate()`를 불러야만 안전한 API로
    두지 않는다 — 빼먹으면 잘못된 입력이 그럴듯한 숫자가 된다.

    **보류는 예산을 쓰지만 정밀도의 분모에서는 빠진다** — 사람이 시간을 썼지만
    오류였는지 아닌지를 모르기 때문이다.

    **후보가 없거나 결정된 것이 0건이면 정밀도는 `None`이다.** 0%가 아니다 —
    0%는 "다 틀렸다"는 뜻이고 여기서는 "말할 수 없다"가 맞다.

    `budget=0`은 **아무것도 안 본다**는 뜻이다(`None`은 전부 본다).
    """
    _check_budget(budget)
    validate_adjudications(adjudications)

    by_key = {a.key: a for a in adjudications}
    mine = [r for r in rankings if r.method == method]
    if not mine:
        raise ValidationError(f"그 방법의 순위가 하나도 없다: {method!r}")

    picked = [by_key[r.candidate_key] for r in top_n(mine, by_key, budget)]
    judged = [a for a in picked if a.verdict is not None]
    holds = [a for a in judged if a.verdict == "hold"]
    decided = [a for a in judged if a.verdict in ("hit", "miss")]
    hits = [a for a in decided if a.verdict == "hit"]

    return Summary(
        budget=budget,
        in_budget=len(picked),
        judged=len(judged),
        holds=len(holds),
        decided=len(decided),
        hit_candidates=len(hits),
        unique_error_yield=len({a.error_key for a in hits}),
        candidate_precision=(len(hits) / len(decided)) if decided else None,
        hold_rate=(len(holds) / len(judged)) if judged else None,
    )
