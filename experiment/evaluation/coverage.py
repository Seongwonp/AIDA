"""사전에 고정한 재표본들에서 상위 N에 드는 후보의 합집합 (판정 범위 검토용).

**무엇을 푸는가.** 기록 단위 부트스트랩은 재표본마다 상위 N을 다시 고른다. 원래 상위 N
합집합만 판정하면, 재표본에서 올라온 후보는 미판정이라 `summarise`가 수확 0으로 센다. 씨앗과
반복 수가 사전에 고정돼 있으므로 **어느 후보가 어느 재표본의 상위 N에 드는지는 판정 전에
전부 알 수 있다.** 여기서는 그 합집합과, 원래 판정 범위 밖의 추가 판정량을 센다.

**무엇을 풀지 않는가.** 이 합집합을 전부 판정하면 고정된 재표본 계산에서 미판정 후보가
사라진다 — 그뿐이다. 신뢰구간의 통계적 타당성(기록 수, 백분위 구간의 포함률, 재표본에서
검수량이 달라지는 문제)을 보장하지 않는다. 판정 없이 순위만으로 도는 계산이라 val을 열지
않고도 판정 목록을 만들 수 있지만, 분석 정의를 무엇으로 할지는 여기서 정하지 않는다.
"""
import hashlib
from collections import defaultdict

from .bootstrap import iter_resamples
from .ranking import top_n
from .schema import Adjudication, Ranking, ValidationError


def tie_key(tie_seed: int, candidate_id: str) -> str:
    """백엔드 `evaluation.tie_key`와 같은 식: sha256("{tie_seed}:{후보 id}")."""
    return hashlib.sha256(f"{tie_seed}:{candidate_id}".encode("utf-8")).hexdigest()


def original_key(drawn_key: str) -> str:
    """재표본 벌의 키(`ds/img#i/cand#i`)를 원래 키(`ds/img/cand`)로 되돌린다."""
    ds, img, cand = drawn_key.split("/", 2)
    return f"{ds}/{img.rsplit('#', 1)[0]}/{cand.rsplit('#', 1)[0]}"


def resample_top_n_union(adjudications: list[Adjudication], rankings: list[Ranking],
                         methods: list[str], budget: int, iterations: int, seed: int,
                         judged_pool: set[str] | None = None,
                         checkpoints: tuple[int, ...] = (100, 500, 1000, 2000)) -> dict:
    """방법마다 (원래 상위 N, 재표본들의 상위 N 합집합, 판정 범위 밖 추가분).

    `judged_pool`은 원래 판정 범위(방법별 상위 N 합집합 ∪ 무작위 K)의 후보 키다. 안 주면
    방법별 원래 상위 N 합집합으로 본다. 재표본 안에서 같은 원래 후보가 여러 벌 뽑혀도 한 번만
    센다. `checkpoints`마다 합집합 크기를 적어 반복 수에 따라 얼마나 늘어나는지 남긴다.
    """
    if not methods:
        raise ValidationError("방법이 하나도 없다")
    if not isinstance(budget, int) or budget < 1:
        raise ValidationError(f"검수 예산은 1 이상이다: {budget!r}")
    by_key = {a.key: a for a in adjudications}
    original: dict[str, set[str]] = {}
    for m in methods:
        mine = [r for r in rankings if r.method == m]
        if not mine:
            raise ValidationError(f"그 방법의 순위가 하나도 없다: {m!r}")
        original[m] = {r.candidate_key for r in top_n(mine, by_key, budget)}
    pool = set(judged_pool) if judged_pool is not None else set().union(*original.values())

    union: dict[str, set[str]] = {m: set(original[m]) for m in methods}
    per_iter_unjudged: dict[str, list[int]] = {m: [] for m in methods}
    curve: dict[str, dict[int, int]] = {m: {} for m in methods}
    for i, _name, facts, ranks in iter_resamples(adjudications, rankings, iterations, seed):
        drawn_by_key = {a.key: a for a in facts}
        for m in methods:
            mine = [r for r in ranks if r.method == m]
            picked = {original_key(r.candidate_key) for r in top_n(mine, drawn_by_key, budget)}
            union[m] |= picked
            per_iter_unjudged[m].append(sum(1 for k in picked if k not in pool))
        for m in methods:
            if (i + 1) in checkpoints:
                curve[m][i + 1] = len(union[m])
    all_union = set().union(*union.values())
    out = {"budget": budget, "iterations": iterations, "seed": seed,
           "judged_pool_size": len(pool),
           "required_total": len(all_union | pool),
           "additional_beyond_pool": len(all_union - pool),
           "additional_candidate_keys": sorted(all_union - pool),
           "methods": {}}
    for m in methods:
        vals = per_iter_unjudged[m]
        out["methods"][m] = {
            "original_top_n": len(original[m]),
            "union_over_resamples": len(union[m]),
            "beyond_original_top_n": len(union[m] - original[m]),
            "beyond_pool": len(union[m] - pool),
            "unjudged_in_top_n_per_resample": {
                "mean": sum(vals) / len(vals), "max": max(vals),
                "share_with_any": sum(1 for v in vals if v) / len(vals)},
            "union_size_at": {str(k): v for k, v in sorted(curve[m].items())},
        }
    return out
