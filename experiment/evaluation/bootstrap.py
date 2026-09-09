"""묶음 단위 짝지은 재표집 (docs/evaluation-protocol.md).

**세 가지가 요점이다.**

1. **재표집 단위가 후보가 아니라 묶음이다.** 같은 이미지(또는 같은 연속 장면)의
   후보들은 독립 표본이 아니다. 후보 단위로 뽑으면 표본이 실제보다 많은 척하게
   되어 구간이 좁아진다.
2. **두 방법에서 같은 묶음을 함께 뽑는다.** 따로 뽑으면 짝지음이 깨져 차이의
   분포가 아니라 두 독립 분포의 차이가 된다.
3. **각 재표본에서 순위·동점·중복 제거·지표를 처음부터 다시 계산한다.** 미리
   계산한 값을 다시 표집하면 상위 N이 바뀌는 효과를 놓친다.

**stdlib만 쓴다.** scipy는 이 환경에 없고 CI에는 numpy도 없다. 재표집 단위와
짝지음이 맞는지는 검사로 고정한다.
"""
import random
from collections import defaultdict

from .paired import paired_difference
from .schema import Judgement

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


def paired_cluster_bootstrap(
    rows: list[Judgement], method: str, baseline: str,
    budget: int | None = None,
    iterations: int = DEFAULT_ITERATIONS, seed: int = DEFAULT_SEED,
) -> dict:
    """(방법 − 기준선) 차이의 95% 구간.

    돌려주는 것에 **반복 수와 씨앗을 담는다** — 그것 없이는 결과를 다시 만들 수
    없다.
    """
    by_cluster: dict[str, list[Judgement]] = defaultdict(list)
    for r in rows:
        by_cluster[r.cluster].append(r)
    clusters = sorted(by_cluster)          # 씨앗이 같으면 결과가 같도록 정렬
    if not clusters:
        raise ValueError("재표집할 묶음이 없다")

    observed = paired_difference(rows, method, baseline, budget)["difference"]

    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(iterations):
        picked = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        resampled: list[Judgement] = []
        for i, name in enumerate(picked):
            # 같은 묶음이 두 번 뽑히면 **그 두 번이 서로 다른 관측이어야 한다.**
            #
            # 후보 id만 갈면 모자란다 — 고유 오류는 `unique_error_id`나
            # `dataset/image/label_index`로 세므로, 그것들이 겹치면 두 번 뽑힌
            # 묶음이 한 번으로 세어져 **차이가 실제보다 작아진다.** 처음에 그렇게
            # 짰고 손계산(차이 4)이 2로 나와서 잡혔다.
            #
            # **두 방법 모두에 같은 접미사를 붙여** 짝지음을 지킨다.
            for r in by_cluster[name]:
                changed = {**r.__dict__,
                           "candidate_id": f"{r.candidate_id}#{i}",
                           "image_id": f"{r.image_id}#{i}"}
                if r.unique_error_id:
                    changed["unique_error_id"] = f"{r.unique_error_id}#{i}"
                resampled.append(Judgement(**changed))
        # **처음부터 다시 계산한다** — 순위도 중복 제거도.
        draws.append(paired_difference(resampled, method, baseline, budget)["difference"])

    return {
        "method": method, "baseline": baseline, "budget": budget,
        "observed_difference": observed,
        "ci_low": _percentile(draws, 0.025),
        "ci_high": _percentile(draws, 0.975),
        "iterations": iterations, "seed": seed,
        "clusters": len(clusters),
    }


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
