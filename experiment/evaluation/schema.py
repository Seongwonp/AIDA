"""입력 검증 (docs/evaluation-protocol.md).

**조용히 넘어가면 안 되는 것들을 여기서 막는다.** 집계가 잘못된 입력을 그럴듯한
숫자로 바꿔 내놓으면 아무도 모른다.
"""
from dataclasses import dataclass

VERDICTS = ("hit", "miss", "hold")
# 판정 없음은 None이다. "아직 안 봤다"와 "보류"는 다른 것이다.


class ValidationError(ValueError):
    """입력이 규약을 어겼다. 집계를 멈춘다."""


@dataclass(frozen=True)
class Judgement:
    """검수자가 후보 하나에 대해 남긴 것.

    `unique_error_id`는 **같은 실제 오류를 가리키는 후보들이 공유하는 id**다.
    기존 라벨의 오류는 `dataset/image/label_index`로 만들 수 있지만, 누락 객체는
    가리킬 라벨이 없어 **판정 단계가 정해 넘겨야 한다**(규약의 "고유 오류를
    무엇으로 식별하는가").
    """
    dataset_id: str
    image_id: str
    method: str
    candidate_id: str
    rank: int
    suspicion: str
    severity: float
    verdict: str | None = None
    label_index: int | None = None
    unique_error_id: str | None = None
    # 연속 장면 묶음. 없으면 이미지 하나가 곧 묶음이다.
    group_id: str | None = None

    @property
    def cluster(self) -> str:
        """재표집 단위. 같은 장면의 이미지들은 독립 표본이 아니다."""
        return self.group_id or f"{self.dataset_id}/{self.image_id}"


def validate(rows: list[Judgement]) -> None:
    """규약을 어긴 입력을 거부한다."""
    seen: set[tuple[str, str, str]] = set()
    for r in rows:
        if r.verdict is not None and r.verdict not in VERDICTS:
            raise ValidationError(f"알 수 없는 판정: {r.verdict!r}")
        if r.rank < 1:
            raise ValidationError(f"순위는 1부터다: {r.rank}")

        key = (r.dataset_id, r.method, r.candidate_id)
        if key in seen:
            raise ValidationError(f"같은 후보가 두 번 나왔다: {key}")
        seen.add(key)

        # **오류로 판정했는데 어느 오류인지 모르면 셀 수 없다.**
        if r.verdict == "hit" and not r.unique_error_id and r.label_index is None:
            raise ValidationError(
                f"고유 오류 id가 없다: {r.dataset_id}/{r.image_id}/{r.candidate_id}. "
                "누락 후보는 판정 단계가 unique_error_id를 정해 넘겨야 한다 "
                "— 후보 id로 대신하면 고유 오류 수가 부풀려진다.")
