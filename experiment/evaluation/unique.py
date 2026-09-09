"""고유 오류 중복 제거 (docs/evaluation-protocol.md).

**같은 잘못된 박스를 여러 유형으로 지목해도 고유 오류는 하나다.** `width`와
`scale`이 같은 박스를 지목하면 후보 2, 고유 오류 1이다.

**여기서 IoU로 묶지 않는다.** 그 규칙은 한 문장으로 정해지지 않는다(연쇄 겹침,
동점, 클래스). 판정 단계가 `unique_error_id`를 정해 넘긴다.
"""
from .schema import Judgement


def error_key(row: Judgement) -> str:
    """이 후보가 가리키는 **실제 오류**의 id.

    라벨을 가리키면 `dataset/image/label_index`로 만들 수 있다. 누락 객체는
    가리킬 라벨이 없어 판정 데이터의 `unique_error_id`를 쓴다.
    """
    if row.unique_error_id:
        return row.unique_error_id
    return f"{row.dataset_id}/{row.image_id}/L{row.label_index}"


def unique_error_ids(rows: list[Judgement]) -> set[str]:
    """오류로 판정된 후보들이 가리키는 **서로 다른** 오류의 집합."""
    return {error_key(r) for r in rows if r.verdict == "hit"}
