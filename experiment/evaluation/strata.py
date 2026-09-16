"""층별 기술통계 — 상자 높이 등 (docs/advice-w5-2026-09-16.md).

**비교 결론을 내리는 곳이 아니다.** 1차 지표는 전체에서 한 번 센다. 여기서는 **각 방법의 상위 N을
먼저 고르고**, 고른 것을 층으로 나눠 센다. 층 안에서 상위 N을 다시 고르면 층마다 다른 질문이 된다.

왜 필요한가: 자가 작은 차를 절반쯤 못 본다(nuImages fit_check). 그러면 `all_label_iou` 상위가
"자가 못 본 멀쩡한 작은 라벨"로 찰 수 있다. 전체 숫자만 보면 그걸 라벨 오류로 읽는다.

층 경계는 **판정 전에 정한다.** 결과를 본 뒤 경계를 옮기지 않는다.
"""
from collections import defaultdict

from .ranking import top_n
from .schema import Adjudication, Ranking, ValidationError, validate_adjudications

# 상자 높이(픽셀) 경계. 위쪽 None은 끝이 없다는 뜻이다. nuImages fit_check 보고와 같은 경계다.
HEIGHT_BANDS: tuple[tuple[float, float | None], ...] = ((0, 30), (30, 60), (60, 120), (120, None))
UNKNOWN = "unknown"


def band_name(lo: float, hi: float | None) -> str:
    return f"{lo:g}-{hi:g}" if hi is not None else f"{lo:g}+"


def height_band(box, bands=HEIGHT_BANDS) -> str:
    """상자 [x1, y1, x2, y2]의 높이가 드는 층. 상자가 없거나 모양이 틀리면 `unknown`."""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return UNKNOWN
    try:
        height = float(box[3]) - float(box[1])
    except (TypeError, ValueError):
        return UNKNOWN
    for lo, hi in bands:
        if height >= lo and (hi is None or height < hi):
            return band_name(lo, hi)
    return UNKNOWN


def height_strata_from_export(export: dict, dataset_id: str | None = None,
                              bands=HEIGHT_BANDS) -> dict[str, str]:
    """내보내기 JSON → {후보 키: 높이 층}. 키는 `load_export`가 만드는 것과 같다."""
    name = dataset_id or export.get("dataset_id")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(f"dataset_id가 비어 있다: {name!r}")
    out = {}
    for row in export.get("adjudications") or []:
        key = Adjudication(dataset_id=name, image_id=row["image"],
                           candidate_id=row["canonical_candidate_id"], suspicion="").key
        out[key] = height_band(row.get("box"), bands)
    return out


def summarise_by_stratum(adjudications: list[Adjudication], rankings: list[Ranking],
                         method: str, stratum_of: dict[str, str],
                         budget: int | None = None) -> dict[str, dict]:
    """방법의 상위 N(전체에서 고른 것)을 층으로 나눠 센다.

    세는 것은 `summary.summarise`와 같은 이름이다 — 보류는 예산을 쓰지만 정밀도 분모에서 빠진다.
    층 합계는 전체와 같아야 한다(`in_budget`, `hit_candidates`). 고유 오류는 층마다 따로 세므로
    같은 오류를 두 층의 후보가 가리키면 합이 전체보다 클 수 있다.
    """
    validate_adjudications(adjudications)
    by_key = {a.key: a for a in adjudications}
    mine = [r for r in rankings if r.method == method]
    if not mine:
        raise ValidationError(f"그 방법의 순위가 하나도 없다: {method!r}")
    unknown_keys = [r.candidate_key for r in mine if r.candidate_key not in stratum_of]
    if unknown_keys:
        raise ValidationError(f"층이 정해지지 않은 후보가 있다: {unknown_keys[0]}")

    groups: dict[str, list[Adjudication]] = defaultdict(list)
    for r in top_n(mine, by_key, budget):
        groups[stratum_of[r.candidate_key]].append(by_key[r.candidate_key])

    out = {}
    for name in sorted(groups):
        picked = groups[name]
        judged = [a for a in picked if a.verdict is not None]
        holds = [a for a in judged if a.verdict == "hold"]
        decided = [a for a in judged if a.verdict in ("hit", "miss")]
        hits = [a for a in decided if a.verdict == "hit"]
        out[name] = {
            "in_budget": len(picked), "judged": len(judged), "holds": len(holds),
            "decided": len(decided), "hit_candidates": len(hits),
            "unique_error_yield": len({a.error_key for a in hits}),
            "candidate_precision": (len(hits) / len(decided)) if decided else None,
        }
    return out
