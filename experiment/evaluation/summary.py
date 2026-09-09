"""한 방법·한 데이터셋의 요약 (docs/evaluation-protocol.md).

**세 가지를 분리해 센다** — 판정 수, 오류로 판정된 후보 수, 고유 오류 수.
이것들이 뭉치면 "같은 오류를 두 번 지목한 것"이 성과처럼 보인다.
"""
from dataclasses import dataclass

from .ranking import top_n
from .schema import Judgement
from .unique import unique_error_ids


@dataclass(frozen=True)
class Summary:
    budget: int | None          # 검수 예산 N (None이면 전부)
    in_budget: int              # 예산 안에 들어온 후보 수
    judged: int                 # 판정 완료 수 (보류 포함 — 시간을 썼다)
    holds: int
    hits: int                   # 오류로 판정된 **후보** 수
    unique_errors: int          # 중복 제거한 **고유 오류** 수
    precision: float | None     # 없으면 정의 없음. 0이 아니다.
    hold_rate: float | None

    def as_dict(self) -> dict:
        return {
            "budget": self.budget, "in_budget": self.in_budget,
            "judged": self.judged, "holds": self.holds, "hits": self.hits,
            "unique_errors": self.unique_errors,
            "precision": self.precision, "hold_rate": self.hold_rate,
        }


def summarise(rows: list[Judgement], budget: int | None = None) -> Summary:
    """예산 N건까지 보고 무엇을 얻었는가.

    **보류는 예산을 쓰지만 정밀도의 분모에서는 빠진다** — 사람이 시간을 썼지만
    오류였는지 아닌지를 모르기 때문이다.

    **후보가 없거나 판정이 0건이면 정밀도는 `None`이다.** 0%가 아니다 — 0%는
    "다 틀렸다"는 뜻이고 여기서는 "말할 수 없다"가 맞다.
    """
    picked = top_n(rows, budget)
    judged = [r for r in picked if r.verdict is not None]
    holds = [r for r in judged if r.verdict == "hold"]
    decided = [r for r in judged if r.verdict in ("hit", "miss")]
    hits = [r for r in decided if r.verdict == "hit"]

    return Summary(
        budget=budget,
        in_budget=len(picked),
        judged=len(judged),
        holds=len(holds),
        hits=len(hits),
        unique_errors=len(unique_error_ids(hits)),
        precision=(len(hits) / len(decided)) if decided else None,
        hold_rate=(len(holds) / len(judged)) if judged else None,
    )
