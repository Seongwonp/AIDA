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
import json
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


def unjudged_in_fixed_resamples(adjudications: list[Adjudication], rankings: list[Ranking],
                                methods: list[str], budget: int, iterations: int, seed: int) -> dict:
    """고정 재표본들의 상위 N에 든 **미판정**(verdict None) 후보. 보류는 판정이다.

    최종 분석 전 점검용. 비어 있어야 `paired_cluster_bootstrap(require_judged_top_n=True)`가 통과한다.
    """
    by_key = {a.key: a for a in adjudications}
    found: dict[str, set[str]] = {m: set() for m in methods}
    for _i, _name, facts, ranks in iter_resamples(adjudications, rankings, iterations, seed):
        dk = {a.key: a for a in facts}
        for m in methods:
            mine = [r for r in ranks if r.method == m]
            for r in top_n(mine, dk, budget):
                if dk[r.candidate_key].verdict is None:
                    found[m].add(original_key(r.candidate_key))
    return {m: sorted(v) for m, v in found.items()}


def export_fingerprint(export: dict) -> str:
    """내보내기의 coverage 입력 지문. **백엔드 `_export_fingerprint`와 같은 식** — 모집단(후보 id·묶음)과
    순위(방법·후보·점수·동점 키)만. 판정은 들어가지 않는다."""
    material = {
        "adjudications": sorted((r["canonical_candidate_id"], r.get("group_id") or "")
                                for r in export["adjudications"]),
        "rankings": sorted((r["method"], r["canonical_candidate_id"], r["severity"], r.get("tie_key"))
                           for r in export["rankings"]),
    }
    return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def check_export_against_coverage(export: dict, budget: int, iterations: int, seed: int,
                                  methods: list[str]) -> dict:
    """최종 분석 입력이 묶음에 얼린 coverage 설정과 같은가. 다르면 `ValidationError`.

    보는 것: 묶음의 `bootstrap_coverage`(반복 수·씨앗·N·방법)와 분석 인자, 그리고 내보내기에서
    다시 계산한 입력 지문과 얼린 지문. **하나라도 다르면 분석을 시작하지 않는다.**
    """
    cov = export.get("bootstrap_coverage")
    if not cov:
        raise ValidationError("내보내기에 bootstrap_coverage가 없다 — 고정 재표본 합집합 없이 얼린 묶음이다")
    expected = {"iterations": iterations, "seed": seed, "budget": budget, "methods": sorted(methods)}
    frozen = {"iterations": cov.get("iterations"), "seed": cov.get("seed"), "budget": cov.get("budget"),
              "methods": sorted(cov.get("methods") or [])}
    if expected != frozen:
        raise ValidationError(f"분석 입력이 묶음의 coverage 설정과 다르다: 분석 {expected} / 묶음 {frozen}")
    if export.get("judge_budget") != budget:
        raise ValidationError(f"내보내기의 판정 예산({export.get('judge_budget')})이 N({budget})과 다르다")
    actual = export_fingerprint(export)
    if actual != cov.get("input_fingerprint"):
        raise ValidationError("내보내기에서 다시 계산한 입력 지문이 묶음에 얼린 지문과 다르다 — 모집단·순위·동점 키 중 무엇이 바뀌었다")
    return {"fingerprint": actual, **expected}
