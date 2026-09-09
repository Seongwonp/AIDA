"""입력 검증과 자료 구조 (docs/evaluation-protocol.md).

**잘못된 상태를 표현하기 어렵게 만든다.**

처음엔 `Judgement` 하나에 방법·순위·판정을 다 담았다. 그러면 **같은 후보가
AIDA에서는 오류이고 기준선에서는 아닌** 상태를 만들 수 있다. 가림 판정은
방법과 무관한 **하나의 사실**이라 그럴 수 없다.

그래서 둘로 나눈다.

    Adjudication   후보 하나에 대한 사실 — 판정, 어느 오류를 가리키는가
    Ranking        방법이 그 후보에 매긴 점수. 방법마다 다른 것은 이것뿐이다

`Judgement`는 편의를 위해 남긴다. 두 구조로 쪼개면서 **방법 간 판정이 어긋나면
거부한다.**
"""
import math
from dataclasses import dataclass, replace

VERDICTS = ("hit", "miss", "hold")
# 판정 없음은 None이다. "아직 안 봤다"와 "보류"는 다른 것이다.


class ValidationError(ValueError):
    """입력이 규약을 어겼다. 집계를 멈춘다."""


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field}는 비어 있으면 안 된다: {value!r}")
    return value


@dataclass(frozen=True)
class Adjudication:
    """후보 하나에 대한 **방법과 무관한** 사실.

    `candidate_id`는 **데이터셋 안에서 고유하다.** 이미지 안에서만 고유하면
    다른 이미지의 같은 id가 섞이므로, 키를 만들 때 이미지도 함께 쓴다.
    """
    dataset_id: str
    image_id: str
    candidate_id: str
    suspicion: str
    verdict: str | None = None
    label_index: int | None = None
    unique_error_id: str | None = None
    # 연속 장면 묶음. 없으면 이미지 하나가 곧 묶음이다.
    group_id: str | None = None

    @property
    def key(self) -> str:
        """데이터셋 안에서 이 후보를 가리키는 값."""
        return f"{self.dataset_id}/{self.image_id}/{self.candidate_id}"

    @property
    def cluster(self) -> str:
        """재표집 단위.

        **데이터셋 이름을 앞에 붙인다** — 다른 데이터셋의 같은 `scene7`이 한
        묶음으로 합쳐지면 재표집이 틀린다.
        """
        return f"{self.dataset_id}/{self.group_id or self.image_id}"

    @property
    def error_key(self) -> str | None:
        """이 후보가 가리키는 **실제 오류**의 id. 판정이 hit가 아니면 없다.

        **데이터셋 이름을 앞에 붙인다** — 다른 데이터셋의 같은
        `unique_error_id`가 한 오류로 세어지면 고유 오류 수가 줄어든다.
        """
        if self.verdict != "hit":
            return None
        if self.unique_error_id:
            return f"{self.dataset_id}/{self.unique_error_id}"
        return f"{self.dataset_id}/{self.image_id}/L{self.label_index}"


@dataclass(frozen=True)
class Ranking:
    """방법이 후보에 매긴 점수. **방법마다 다른 것은 이것뿐이다.**"""
    method: str
    candidate_key: str
    severity: float


@dataclass(frozen=True)
class Judgement:
    """한 방법의 한 후보 — 사실과 점수를 함께 적은 편의용 입력.

    `split_judgements()`가 `Adjudication`과 `Ranking`으로 쪼개면서 방법 간
    판정이 어긋나는지 확인한다.
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
    group_id: str | None = None

    @property
    def cluster(self) -> str:
        return f"{self.dataset_id}/{self.group_id or self.image_id}"


def validate_adjudications(rows: list[Adjudication]) -> None:
    """후보에 대한 사실이 규약을 지키는가."""
    seen: set[str] = set()
    for r in rows:
        _require_text(r.dataset_id, "dataset_id")
        _require_text(r.image_id, "image_id")
        _require_text(r.candidate_id, "candidate_id")

        if r.verdict is not None and r.verdict not in VERDICTS:
            raise ValidationError(f"알 수 없는 판정: {r.verdict!r}")
        if r.label_index is not None and r.label_index < 0:
            raise ValidationError(f"라벨 인덱스는 0 이상이다: {r.label_index}")

        if r.key in seen:
            raise ValidationError(f"같은 후보가 두 번 나왔다: {r.key}")
        seen.add(r.key)

        # **오류로 판정했는데 어느 오류인지 모르면 셀 수 없다.**
        if r.verdict == "hit" and not r.unique_error_id and r.label_index is None:
            raise ValidationError(
                f"고유 오류 id가 없다: {r.key}. 누락 후보는 판정 단계가 "
                "unique_error_id를 정해 넘겨야 한다 — 후보 id로 대신하면 "
                "고유 오류 수가 부풀려진다.")

        # 라벨을 가리키는데 다른 오류 id를 달면 둘 중 무엇이 맞는지 모른다.
        if (r.label_index is not None and r.unique_error_id
                and r.unique_error_id != f"{r.image_id}/L{r.label_index}"):
            raise ValidationError(
                f"라벨 인덱스와 고유 오류 id가 어긋난다: {r.key} "
                f"(label_index={r.label_index}, unique_error_id={r.unique_error_id!r})")


def validate_rankings(rankings: list[Ranking], known: set[str]) -> None:
    for r in rankings:
        _require_text(r.method, "method")
        if r.candidate_key not in known:
            raise ValidationError(f"모르는 후보에 순위가 붙었다: {r.candidate_key}")
        if not isinstance(r.severity, (int, float)) or not math.isfinite(r.severity):
            raise ValidationError(f"심각도가 유한한 수가 아니다: {r.severity!r}")

    seen: set[tuple[str, str]] = set()
    for r in rankings:
        pair = (r.method, r.candidate_key)
        if pair in seen:
            raise ValidationError(f"같은 방법이 한 후보에 두 번 점수를 줬다: {pair}")
        seen.add(pair)


def split_judgements(rows: list[Judgement]) -> tuple[list[Adjudication], list[Ranking]]:
    """편의용 입력을 사실과 점수로 쪼갠다.

    **같은 후보의 판정이 방법마다 다르면 거부한다.** 가림 판정은 방법과 무관한
    하나의 사실이다 — 방법별로 다르면 그것은 판정이 아니라 방법의 의견이다.
    """
    facts: dict[str, Adjudication] = {}
    rankings: list[Ranking] = []

    for r in rows:
        _require_text(r.dataset_id, "dataset_id")
        _require_text(r.image_id, "image_id")
        _require_text(r.candidate_id, "candidate_id")
        _require_text(r.method, "method")

        fact = Adjudication(
            dataset_id=r.dataset_id, image_id=r.image_id,
            candidate_id=r.candidate_id, suspicion=r.suspicion,
            verdict=r.verdict, label_index=r.label_index,
            unique_error_id=r.unique_error_id, group_id=r.group_id)

        existing = facts.get(fact.key)
        if existing is None:
            facts[fact.key] = fact
        elif replace(existing, group_id=fact.group_id) != fact:
            raise ValidationError(
                f"같은 후보의 판정이 방법마다 다르다: {fact.key}. "
                "판정은 방법과 무관한 하나의 사실이어야 한다 "
                f"({existing.verdict!r} vs {fact.verdict!r})")

        rankings.append(Ranking(method=r.method, candidate_key=fact.key,
                                severity=r.severity))

    adjudications = list(facts.values())
    validate_adjudications(adjudications)
    validate_rankings(rankings, {a.key for a in adjudications})
    return adjudications, rankings


def validate(rows: list[Judgement]) -> None:
    """편의용 입력 전체 검증. 쪼개지면 규약을 지킨다는 뜻이다."""
    split_judgements(rows)
