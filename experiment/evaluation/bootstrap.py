"""묶음 단위 짝지은 재표집 (docs/evaluation-protocol.md).

**네 가지가 요점이다.**

1. **재표집 단위가 후보가 아니라 묶음이다.** 같은 이미지(또는 같은 연속 장면)의
   후보들은 독립 표본이 아니다. 후보 단위로 뽑으면 표본이 실제보다 많은 척하게
   되어 구간이 좁아진다.
2. **두 방법에서 같은 묶음을 함께 뽑는다.** 따로 뽑으면 짝지음이 깨져 차이의
   분포가 아니라 두 독립 분포의 차이가 된다.
3. **각 재표본에서 순위·동점·중복 제거·지표를 처음부터 다시 계산한다.** 미리
   계산한 값을 다시 표집하면 상위 N이 바뀌는 효과를 놓친다.
4. **데이터셋별로 재표집하고 그 차이를 동등 가중한다.** 모든 묶음을 한 통에서
   뽑으면 묶음이 많은 데이터셋이 더 큰 가중치를 갖는다 — 전체 집계는 동등
   가중인데 구간만 크기 가중이면 둘이 어긋난다.

**stdlib만 쓴다.** scipy는 이 환경에 없고 CI에는 numpy도 없다. 재표집 단위와
짝지음이 맞는지는 검사로 고정한다.
"""
import random
from collections import defaultdict
from dataclasses import replace
from statistics import mean

from .paired import check_same_candidate_set, paired_difference
from .schema import Adjudication, Ranking, ValidationError

DEFAULT_ITERATIONS = 2000
DEFAULT_SEED = 42


def _percentile(values: list[float], q: float) -> float:
    """선형 보간 분위수. numpy 없이."""
    if not values:
        raise ValueError("빈 분포에서 분위수를 낼 수 없다")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


def _resample(clusters: list[str], by_cluster: dict[str, list[Adjudication]],
              rankings_by_key: dict[str, list[Ranking]],
              rng: random.Random) -> tuple[list[Adjudication], list[Ranking]]:
    """묶음을 복원추출하고, 뽑힌 각 벌을 **서로 다른 관측**으로 만든다.

    후보 id만 갈면 모자란다 — 고유 오류는 `unique_error_id`나 라벨 인덱스로
    세므로, 그것들이 겹치면 두 번 뽑힌 묶음이 한 번으로 세어져 **차이가 실제보다
    작아진다.** 처음에 그렇게 짰고 손계산(차이 4)이 2로 나와서 잡혔다.
    """
    picked = [clusters[rng.randrange(len(clusters))] for _ in clusters]
    facts: list[Adjudication] = []
    rankings: list[Ranking] = []

    for i, name in enumerate(picked):
        for a in by_cluster[name]:
            drawn = replace(
                a,
                image_id=f"{a.image_id}#{i}",
                candidate_id=f"{a.candidate_id}#{i}",
                unique_error_id=(f"{a.unique_error_id}#{i}"
                                 if a.unique_error_id else None),
                group_id=(f"{a.group_id}#{i}" if a.group_id else None))
            facts.append(drawn)
            # **두 방법 모두** 같은 벌을 가리키게 해 짝지음을 지킨다.
            for r in rankings_by_key[a.key]:
                rankings.append(replace(r, candidate_key=drawn.key))
    return facts, rankings


def paired_cluster_bootstrap(
    adjudications: list[Adjudication], rankings: list[Ranking],
    method: str, baseline: str, budget: int | None = None,
    iterations: int = DEFAULT_ITERATIONS, seed: int = DEFAULT_SEED,
) -> dict:
    """(방법 − 기준선) 차이의 95% 구간.

    **데이터셋이 여럿이면 데이터셋별로 재표집하고 차이를 동등 가중한다.**

    돌려주는 것에 **반복 수와 씨앗을 담는다** — 그것 없이는 결과를 다시 만들 수
    없다.
    """
    if not isinstance(iterations, int) or iterations < 1:
        raise ValidationError(f"반복 수는 1 이상이다: {iterations!r}")
    check_same_candidate_set(rankings, method, baseline)

    observed = equal_weight_difference(adjudications, rankings, method,
                                       baseline, budget)

    by_dataset: dict[str, list[Adjudication]] = defaultdict(list)
    for a in adjudications:
        by_dataset[a.dataset_id].append(a)
    rankings_by_key: dict[str, list[Ranking]] = defaultdict(list)
    for r in rankings:
        rankings_by_key[r.candidate_key].append(r)

    datasets = sorted(by_dataset)
    clusters_of: dict[str, tuple[list[str], dict[str, list[Adjudication]]]] = {}
    for name in datasets:
        grouped: dict[str, list[Adjudication]] = defaultdict(list)
        for a in by_dataset[name]:
            grouped[a.cluster].append(a)
        clusters_of[name] = (sorted(grouped), grouped)
        if not grouped:
            raise ValidationError(f"재표집할 묶음이 없다: {name}")

    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(iterations):
        per_dataset: list[float] = []
        for name in datasets:
            clusters, grouped = clusters_of[name]
            facts, ranks = _resample(clusters, grouped, rankings_by_key, rng)
            # **처음부터 다시 계산한다** — 순위도 중복 제거도.
            per_dataset.append(
                paired_difference(facts, ranks, method, baseline, budget)["difference"])
        draws.append(mean(per_dataset))          # 데이터셋 동등 가중

    return {
        "method": method, "baseline": baseline, "budget": budget,
        "observed_difference": observed,
        "ci_low": _percentile(draws, 0.025),
        "ci_high": _percentile(draws, 0.975),
        "iterations": iterations, "seed": seed,
        "datasets": datasets,
        "clusters": {name: len(clusters_of[name][0]) for name in datasets},
        "weighting": "데이터셋 동등 가중",
    }


def equal_weight_difference(adjudications: list[Adjudication],
                            rankings: list[Ranking], method: str, baseline: str,
                            budget: int | None = None) -> float:
    """데이터셋별 차이의 단순 평균. 큰 데이터셋이 결론을 끌지 않게."""
    by_dataset: dict[str, list[Adjudication]] = defaultdict(list)
    for a in adjudications:
        by_dataset[a.dataset_id].append(a)

    diffs = []
    for name in sorted(by_dataset):
        keys = {a.key for a in by_dataset[name]}
        subset = [r for r in rankings if r.candidate_key in keys]
        diffs.append(paired_difference(by_dataset[name], subset, method,
                                       baseline, budget)["difference"])
    return mean(diffs) if diffs else 0.0


def verdict_against_delta(result: dict, delta: float | None) -> str:
    """성공·불확실·실패. **Δ가 없으면 판정하지 않는다.**

    규약이 Δ를 `TBD`로 두었다. 근거 없이 숫자를 넣으면 그것은 기준이 아니라
    사후 설명이 된다.
    """
    if delta is None:
        return "미정"                      # Δ가 정해지기 전에는 판정 없음
    if result["ci_low"] > delta:
        return "성공"
    if result["ci_high"] < delta:
        return "실패"
    return "불확실"
