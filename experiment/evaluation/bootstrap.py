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


def _drawn_error_id(a: Adjudication, image: str, i: int) -> str | None:
    """재표본 벌의 고유 오류 id. **벌마다 달라야 하고, 스키마 규칙도 지켜야 한다.**

    서버는 기존 라벨 hit에 `<이미지>/L<라벨>`을 붙이고, 스키마는 그 id가 후보의
    이미지·라벨과 맞는지 본다. 처음에는 id 뒤에 `#i`만 붙여서 이미지는
    `a.jpg#0`, id는 `a.jpg/L0#0`이 되어 규칙에 걸렸다 — 실제 내보내기로는
    부트스트랩이 돌지 않았다(prelim1 판정 전 합성 판정으로 잡았다). 라벨을 가리키는
    id는 **바뀐 이미지 이름으로 다시 만든다.** 이미지 이름에 `#i`가 들어 있으니
    벌마다 여전히 다르다.
    """
    if not a.unique_error_id:
        return None
    if a.label_index is not None and a.unique_error_id == f"{a.image_id}/L{a.label_index}":
        return f"{image}/L{a.label_index}"
    return f"{a.unique_error_id}#{i}"


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
            image = f"{a.image_id}#{i}"
            drawn = replace(
                a,
                image_id=image,
                candidate_id=f"{a.candidate_id}#{i}",
                unique_error_id=_drawn_error_id(a, image, i),
                group_id=(f"{a.group_id}#{i}" if a.group_id else None))
            facts.append(drawn)
            # **두 방법 모두** 같은 벌을 가리키게 해 짝지음을 지킨다.
            for r in rankings_by_key[a.key]:
                rankings.append(replace(r, candidate_key=drawn.key))
    return facts, rankings


def iter_resamples(adjudications: list[Adjudication], rankings: list[Ranking],
                   iterations: int, seed: int):
    """사전에 고정된 재표본 열. `(반복 번호, 데이터셋, facts, rankings)`를 낸다.

    **`paired_cluster_bootstrap`과 `coverage.resample_top_n_union`이 이 생성기를 같이 쓴다.**
    같은 씨앗·반복 수면 두 곳이 정확히 같은 재표본을 본다 — 난수를 소비하는 순서(반복마다
    데이터셋 이름순)가 여기 한 곳에만 있기 때문이다.
    """
    if not isinstance(iterations, int) or iterations < 1:
        raise ValidationError(f"반복 수는 1 이상이다: {iterations!r}")
    by_dataset: dict[str, list[Adjudication]] = defaultdict(list)
    for a in adjudications:
        by_dataset[a.dataset_id].append(a)
    rankings_by_key: dict[str, list[Ranking]] = defaultdict(list)
    for r in rankings:
        rankings_by_key[r.candidate_key].append(r)
    datasets = sorted(by_dataset)
    clusters_of = {}
    for name in datasets:
        grouped: dict[str, list[Adjudication]] = defaultdict(list)
        for a in by_dataset[name]:
            grouped[a.cluster].append(a)
        if not grouped:
            raise ValidationError(f"재표집할 묶음이 없다: {name}")
        clusters_of[name] = (sorted(grouped), grouped)
    rng = random.Random(seed)
    for i in range(iterations):
        for name in datasets:
            clusters, grouped = clusters_of[name]
            facts, ranks = _resample(clusters, grouped, rankings_by_key, rng)
            yield i, name, facts, ranks


def paired_cluster_bootstrap(
    adjudications: list[Adjudication], rankings: list[Ranking],
    method: str, baseline: str, budget: int | None = None,
    iterations: int = DEFAULT_ITERATIONS, seed: int = DEFAULT_SEED,
    require_same_candidates: bool = True,
    require_judged_top_n: bool = False,
) -> dict:
    """(방법 − 기준선) 차이의 95% 구간.

    `require_judged_top_n=True`면 **어느 재표본의 상위 N에라도 미판정(`verdict=None`) 후보가 있으면
    구간을 내지 않고 거부한다.** 보류(`hold`)는 완료된 판정이라 미판정이 아니다. 고정 재표본 합집합을
    전부 판정했을 때만 통과한다 — 통과가 구간의 통계적 타당성을 뜻하지는 않는다
    (docs/unjudged-bootstrap-review-2026-09-27.md).

    **데이터셋이 여럿이면 데이터셋별로 재표집하고 차이를 동등 가중한다.**

    돌려주는 것에 **반복 수와 씨앗을 담는다** — 그것 없이는 결과를 다시 만들 수
    없다.

    `require_same_candidates=False`는 후보 생성까지 포함한 비교라고 밝힌 것이다. 재표집
    단위는 그때도 **이미지 묶음**이라 짝지음은 그대로 지켜진다 — 같은 이미지 벌에서 두
    방법이 각자 상위 N을 고른다. 그 사실을 결과에 남긴다.
    """
    if not isinstance(iterations, int) or iterations < 1:
        raise ValidationError(f"반복 수는 1 이상이다: {iterations!r}")
    check_same_candidate_set(rankings, method, baseline, require_same_candidates)

    observed = equal_weight_difference(adjudications, rankings, method, baseline,
                                       budget, require_same_candidates)

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

    draws: list[float] = []
    # 재표본 상위 N에 든 **미판정** 후보 수 (방법별). 원래 상위 N 밖에 있던 후보가 재표집으로
    # 올라오면 `summarise`는 그것을 예산에는 넣고 판정에는 못 넣는다 — 그 자리는 수확 0으로
    # 세어진다. 그 수를 여기서 남긴다(docs/unjudged-bootstrap-review-2026-09-27.md). **처리를
    # 바꾸지는 않는다.**
    unjudged = {method: [], baseline: []}
    per_dataset: list[float] = []
    current = -1
    for i, name, facts, ranks in iter_resamples(adjudications, rankings, iterations, seed):
        if i != current:
            if per_dataset:
                draws.append(mean(per_dataset))      # 데이터셋 동등 가중
            per_dataset = []
            current = i
        # **처음부터 다시 계산한다** — 순위도 중복 제거도.
        diff = paired_difference(facts, ranks, method, baseline, budget,
                                 require_same_candidates)
        per_dataset.append(diff["difference"])
        for m, key in ((method, "method_summary"), (baseline, "baseline_summary")):
            summ = diff[key]
            missing = summ["in_budget"] - summ["judged"]
            if require_judged_top_n and missing:
                raise ValidationError(
                    f"재표본 {i}({name})의 '{m}' 상위 {budget} 안에 미판정 후보가 {missing}건 있다. "
                    "고정 재표본 합집합을 전부 판정하기 전에는 구간을 내지 않는다.")
            unjudged[m].append(missing)
    if per_dataset:
        draws.append(mean(per_dataset))

    def _stats(values: list[int]) -> dict:
        return {"mean": (sum(values) / len(values)) if values else 0.0,
                "max": max(values, default=0),
                "share_of_resamples_with_any": (sum(1 for v in values if v) / len(values)) if values else 0.0}

    return {
        "method": method, "baseline": baseline, "budget": budget,
        "observed_difference": observed,
        "ci_low": _percentile(draws, 0.025),
        "ci_high": _percentile(draws, 0.975),
        "iterations": iterations, "seed": seed,
        # 무엇을 짝지었는가 — 같은 후보면 정렬 효과, 다르면 후보 생성까지 포함한 효과다.
        "same_candidate_set": require_same_candidates,
        "datasets": datasets,
        "clusters": {name: len(clusters_of[name][0]) for name in datasets},
        "weighting": "데이터셋 동등 가중",
        # 재표본 상위 N에 든 미판정 후보(데이터셋·재표본 단위). 0이 아니면 구간에 "미판정 =
        # 수확 0" 처리가 들어가 있다. 이 값은 보고용이고 구간 계산을 바꾸지 않는다.
        "unjudged_in_top_n": {m: _stats(v) for m, v in unjudged.items()},
        "judged_top_n_required": require_judged_top_n,
    }


def equal_weight_difference(adjudications: list[Adjudication],
                            rankings: list[Ranking], method: str, baseline: str,
                            budget: int | None = None,
                            require_same_candidates: bool = True) -> float:
    """데이터셋별 차이의 단순 평균. 큰 데이터셋이 결론을 끌지 않게.

    `require_same_candidates`는 그대로 `paired_difference`에 넘긴다 — 여기서 기본값으로
    되돌리면 후보 생성까지 포함한 비교가 데이터셋 단위에서 다시 막힌다.
    """
    by_dataset: dict[str, list[Adjudication]] = defaultdict(list)
    for a in adjudications:
        by_dataset[a.dataset_id].append(a)

    diffs = []
    for name in sorted(by_dataset):
        keys = {a.key for a in by_dataset[name]}
        subset = [r for r in rankings if r.candidate_key in keys]
        diffs.append(paired_difference(by_dataset[name], subset, method, baseline,
                                       budget, require_same_candidates)["difference"])
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
