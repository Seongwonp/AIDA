"""데이터셋 동등 가중 (docs/evaluation-protocol.md).

**큰 데이터셋이 결론을 끌지 않게 한다.** 후보 수로 가중하면 표본이 많은 쪽의
성질이 전체 결론이 된다.

**예산 N은 데이터셋마다 적용된다.** 데이터셋이 셋이면 총 검수량은 3N이다 —
규약에 그렇게 적었다. 전체를 N으로 나눠 쓰면 작은 데이터셋에서 볼 것이 거의
없어져 동등 가중의 뜻이 사라진다.
"""
from collections import defaultdict
from statistics import mean

from .paired import paired_difference
from .schema import Adjudication, Ranking


def equal_weight_overall(adjudications: list[Adjudication], rankings: list[Ranking],
                         method: str, baseline: str,
                         budget: int | None = None) -> dict:
    """데이터셋별로 먼저 재고, 전체는 그 값들의 **단순 평균**.

    데이터셋별 결과를 **먼저 보존한다** — 뭉친 평균이 원인을 숨긴 적이 있다
    (docs/21 AR·AV).
    """
    by_dataset: dict[str, list[Adjudication]] = defaultdict(list)
    for a in adjudications:
        by_dataset[a.dataset_id].append(a)

    datasets = sorted(by_dataset)
    per_dataset = {}
    for name in datasets:
        keys = {a.key for a in by_dataset[name]}
        subset = [r for r in rankings if r.candidate_key in keys]
        per_dataset[name] = paired_difference(by_dataset[name], subset,
                                              method, baseline, budget)

    diffs = [d["difference"] for d in per_dataset.values()]
    return {
        "per_dataset": per_dataset,
        "datasets": datasets,
        "overall_difference": mean(diffs) if diffs else None,
        "weighting": "데이터셋 동등 가중",
        "budget_per_dataset": budget,
        "total_reviewed": None if budget is None else budget * len(datasets),
    }
