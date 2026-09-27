"""미판정 후보 문제의 회귀 검사와 재표본 상위 N 합집합 (docs/unjudged-bootstrap-review-2026-09-27.md).

**고정하는 사실:** 기록 단위 재표집은 원래 상위 N 밖의 후보를 상위 N에 올릴 수 있고, 그 후보가
미판정이면 `summarise`는 예산에는 넣고 수확에는 0으로 센다. 이 검사는 그 동작을 **바꾸지 않고
드러낸다.** 합집합 계산이 부트스트랩과 정확히 같은 재표본을 보는 것도 고정한다.
"""
import hashlib
import random
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.bootstrap import iter_resamples, paired_cluster_bootstrap  # noqa: E402
from evaluation.coverage import original_key, resample_top_n_union, tie_key  # noqa: E402
from evaluation.ranking import top_n  # noqa: E402
from evaluation.schema import Adjudication, Ranking  # noqa: E402
from evaluation.summary import summarise  # noqa: E402

A, B = "aida", "all_label_iou"


def population():
    """묶음 3개(g0·g1·g2). g0에 점수 1.0 후보 둘, g1에 0.9 하나, g2에 0.8 하나.
    N=2면 원래 상위 2는 g0의 둘. g0이 빠진 재표본에서는 g1·g2 후보가 상위 2에 든다."""
    rows = [Adjudication("d", "i0", "c0", "", label_index=0, group_id="g0"),
            Adjudication("d", "i0", "c1", "", label_index=1, group_id="g0"),
            Adjudication("d", "i1", "c2", "", label_index=0, group_id="g1"),
            Adjudication("d", "i2", "c3", "", label_index=0, group_id="g2")]
    score = {rows[0].key: 1.0, rows[1].key: 1.0, rows[2].key: 0.9, rows[3].key: 0.8}
    ranks = [Ranking(m, a.key, score[a.key], tie_key=tie_key(1, a.candidate_id))
             for a in rows for m in (A, B)]
    return rows, ranks


def test_재표집은_원래_상위_N_밖의_후보를_상위_N에_올린다():
    rows, ranks = population()
    by_key = {a.key: a for a in rows}
    original = {r.candidate_key for r in top_n([r for r in ranks if r.method == A], by_key, 2)}
    assert original == {rows[0].key, rows[1].key}
    entered = set()
    for _i, _d, facts, drawn in iter_resamples(rows, ranks, iterations=50, seed=3):
        dk = {a.key: a for a in facts}
        picked = {original_key(r.candidate_key)
                  for r in top_n([r for r in drawn if r.method == A], dk, 2)}
        entered |= picked - original
    assert entered, "50번 재표집에서 원래 상위 2 밖의 후보가 한 번도 안 올라오면 검사가 뜻이 없다"


def test_미판정_후보는_예산은_쓰고_수확은_0으로_세어진다():
    """현재 동작을 고정한다 — 고친 것이 아니다."""
    rows, ranks = population()
    judged = {rows[0].key: "hit", rows[1].key: "miss"}          # 원래 상위 2만 판정
    adj = [replace(a, verdict=judged.get(a.key)) for a in rows]
    # g0을 뺀 재표본을 손으로 만든다: g1·g2만 남는다
    sub = [a for a in adj if a.group_id != "g0"]
    ranks_sub = [r for r in ranks if r.candidate_key in {a.key for a in sub}]
    s = summarise(sub, ranks_sub, A, budget=2)
    assert s.in_budget == 2 and s.judged == 0 and s.unique_error_yield == 0


def test_부트스트랩은_상위_N의_미판정_수를_보고한다():
    rows, ranks = population()
    judged = {rows[0].key: "hit", rows[1].key: "miss"}
    adj = [replace(a, verdict=judged.get(a.key)) for a in rows]
    r = paired_cluster_bootstrap(adj, ranks, B, A, budget=2, iterations=50, seed=3,
                                 require_same_candidates=False)
    u = r["unjudged_in_top_n"]
    assert u[A]["max"] >= 1 and u[A]["share_of_resamples_with_any"] > 0
    assert u[B]["max"] >= 1


def test_합집합은_부트스트랩과_같은_재표본을_본다():
    """생성기를 공유하므로 씨앗이 같으면 같은 재표본이다 — 여기서는 직접 대조한다."""
    rows, ranks = population()
    a = [(i, d, sorted(f.key for f in facts)) for i, d, facts, _ in iter_resamples(rows, ranks, 20, 5)]
    b = [(i, d, sorted(f.key for f in facts)) for i, d, facts, _ in iter_resamples(rows, ranks, 20, 5)]
    assert a == b
    cov = resample_top_n_union(rows, ranks, [A, B], budget=2, iterations=20, seed=5)
    entered = set()
    for _i, _d, facts, drawn in iter_resamples(rows, ranks, 20, 5):
        dk = {x.key: x for x in facts}
        entered |= {original_key(r.candidate_key) for r in top_n([r for r in drawn if r.method == A], dk, 2)}
    assert cov["methods"][A]["union_over_resamples"] == len(entered | {rows[0].key, rows[1].key})


def test_추가_판정량은_판정_범위_밖의_후보_수다():
    rows, ranks = population()
    pool = {rows[0].key, rows[1].key, rows[3].key}       # 상위 2 ∪ "무작위 K"로 c3
    cov = resample_top_n_union(rows, ranks, [A, B], budget=2, iterations=50, seed=3, judged_pool=pool)
    assert cov["judged_pool_size"] == 3
    assert cov["additional_beyond_pool"] == cov["required_total"] - 3
    assert set(cov["additional_candidate_keys"]) <= {rows[2].key}
    assert cov["methods"][A]["unjudged_in_top_n_per_resample"]["max"] <= 2


def test_원래_키_복원():
    assert original_key("d/img#3/L2#3") == "d/img/L2"
    assert original_key("d/a#b#7/c#7") == "d/a#b/c"


def test_동점_키_식은_백엔드와_같다():
    assert tie_key(7, "Labc") == hashlib.sha256(b"7:Labc").hexdigest()


def test_기존_부트스트랩_결과는_생성기_분리_전과_같은_재표본을_쓴다():
    """난수 소비 순서가 바뀌면 씨앗 42의 옛 결과를 재현할 수 없다. 손으로 같은 순서를 돌려 대조한다."""
    rows, ranks = population()
    from evaluation.bootstrap import _resample
    from collections import defaultdict
    grouped = defaultdict(list)
    for a in rows:
        grouped[a.cluster].append(a)
    rk = defaultdict(list)
    for r in ranks:
        rk[r.candidate_key].append(r)
    rng = random.Random(11)
    manual = [sorted(f.key for f in _resample(sorted(grouped), grouped, rk, rng)[0]) for _ in range(5)]
    gen = [sorted(f.key for f in facts) for _i, _d, facts, _ in iter_resamples(rows, ranks, 5, 11)]
    assert manual == gen
