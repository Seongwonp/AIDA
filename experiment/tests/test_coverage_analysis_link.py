"""확장 목록만 판정한 결과 = 전량 판정 결과 (고정 재표본 전부에서), 미판정 거부 (안 (a)).

합성 모집단에서 (1) 원래 상위 N 합집합 ∪ K만 판정하면 부트스트랩이 거부하고, (2) 고정 재표본
합집합까지 판정하면 통과하며 전량 판정과 **모든 재표본에서** 같은 차이를 내는지 본다.
"""
import random
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.bootstrap import iter_resamples, paired_cluster_bootstrap  # noqa: E402
from evaluation.coverage import resample_top_n_union, tie_key, unjudged_in_fixed_resamples  # noqa: E402
from evaluation.paired import paired_difference  # noqa: E402
from evaluation.ranking import top_n  # noqa: E402
from evaluation.schema import Adjudication, Ranking, ValidationError  # noqa: E402

A, B = "aida", "all_label_iou"
N, ITER, SEED = 5, 60, 9


def population(seed=4, logs=8, per_log=4):
    rng = random.Random(seed)
    rows, ranks, truth = [], [], {}
    for g in range(logs):
        for i in range(per_log):
            a = Adjudication("d", f"g{g}i{i}", "L0", "", label_index=0, group_id=f"g{g}")
            rows.append(a)
            truth[a.key] = rng.random() < 0.4
            s = round(rng.random(), 3)
            tk = tie_key(1, a.image_id)
            ranks.append(Ranking(B, a.key, s, tie_key=tk))
            if rng.random() < 0.7:
                ranks.append(Ranking(A, a.key, s, tie_key=tk))
    return rows, ranks, truth


def judged_view(rows, truth, keys):
    return [replace(a, verdict=("hit" if truth[a.key] else "miss")) if a.key in keys else a for a in rows]


def test_원래_상위_N만_판정하면_거부하고_합집합까지_판정하면_전량_판정과_같다():
    rows, ranks, truth = population()
    by_key = {a.key: a for a in rows}
    base = set()
    for m in (A, B):
        base |= {r.candidate_key for r in top_n([r for r in ranks if r.method == m], by_key, N)}
    cov = resample_top_n_union(rows, ranks, [A, B], N, ITER, SEED, judged_pool=base)
    extra = set(cov["additional_candidate_keys"])
    assert extra, "합성 조건에서 추가 후보가 없으면 검사가 뜻이 없다"

    partial = judged_view(rows, truth, base)
    assert unjudged_in_fixed_resamples(partial, ranks, [A, B], N, ITER, SEED)[A] or \
        unjudged_in_fixed_resamples(partial, ranks, [A, B], N, ITER, SEED)[B]
    with pytest.raises(ValidationError, match="미판정"):
        paired_cluster_bootstrap(partial, ranks, B, A, N, ITER, SEED,
                                 require_same_candidates=False, require_judged_top_n=True)

    expanded = judged_view(rows, truth, base | extra)
    oracle = judged_view(rows, truth, set(by_key))
    assert unjudged_in_fixed_resamples(expanded, ranks, [A, B], N, ITER, SEED) == {A: [], B: []}
    r1 = paired_cluster_bootstrap(expanded, ranks, B, A, N, ITER, SEED,
                                  require_same_candidates=False, require_judged_top_n=True)
    r2 = paired_cluster_bootstrap(oracle, ranks, B, A, N, ITER, SEED, require_same_candidates=False)
    assert (r1["ci_low"], r1["ci_high"], r1["observed_difference"]) == \
        (r2["ci_low"], r2["ci_high"], r2["observed_difference"])
    # 재표본마다 같은 차이
    for (_, _, f1, k1), (_, _, f2, k2) in zip(iter_resamples(expanded, ranks, ITER, SEED),
                                              iter_resamples(oracle, ranks, ITER, SEED)):
        d1 = paired_difference(f1, k1, B, A, N, require_same_candidates=False)["difference"]
        d2 = paired_difference(f2, k2, B, A, N, require_same_candidates=False)["difference"]
        assert d1 == d2


def test_보류는_판정이라_거부되지_않는다():
    rows, ranks, truth = population()
    by_key = {a.key: a for a in rows}
    all_hold = [replace(a, verdict="hold") for a in rows]
    r = paired_cluster_bootstrap(all_hold, ranks, B, A, N, 10, SEED,
                                 require_same_candidates=False, require_judged_top_n=True)
    assert r["judged_top_n_required"] is True and r["unjudged_in_top_n"][A]["max"] == 0
