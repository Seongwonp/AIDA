"""데이터셋 동등 가중 (docs/evaluation-protocol.md).

**큰 데이터셋이 결론을 끌지 않게 한다.** 후보 수로 가중하면 표본이 많은 쪽의
성질이 전체 결론이 된다.
"""
from statistics import mean

from .paired import paired_difference
from .schema import Judgement


def equal_weight_overall(rows: list[Judgement], method: str, baseline: str,
                         budget: int | None = None) -> dict:
    """데이터셋별로 먼저 재고, 전체는 그 값들의 **단순 평균**.

    데이터셋별 결과를 **먼저 보존한다** — 뭉친 평균이 원인을 숨긴 적이 있다
    (docs/21 AR·AV).
    """
    datasets = sorted({r.dataset_id for r in rows})
    per_dataset = {}
    for name in datasets:
        subset = [r for r in rows if r.dataset_id == name]
        per_dataset[name] = paired_difference(subset, method, baseline, budget)

    diffs = [d["difference"] for d in per_dataset.values()]
    return {
        "per_dataset": per_dataset,
        "datasets": datasets,
        "overall_difference": mean(diffs) if diffs else None,
        "weighting": "데이터셋 동등 가중",
    }
