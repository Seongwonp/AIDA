"""재검수 순위 버전 (docs/adr-ranking-separation.md).

backend는 experiment 코드를 가져오지 않는다(torch 경계). 그래서 이름을 여기 따로 적고,
검사가 `experiment/label_diagnosis.py`와 대조한다 — 한쪽만 바뀌면 그 검사가 깨진다.

| ID | 무엇 |
|---|---|
| `aida_v1_systematic_boost` | 지금까지의 제품 순위. 기본값 |
| `aida_v2_candidate_iou` | 층마다 후보 단위 신호만 쓰는 시험 버전. 검증되지 않았다 |
"""

RANKING_V1 = "aida_v1_systematic_boost"
RANKING_V2 = "aida_v2_candidate_iou"
RANKING_VERSIONS = (RANKING_V1, RANKING_V2)
# 버전 기록이 없는 옛 결과·묶음·내보내기는 v1이 만든 것이다 — v2 전에는 v1뿐이었다.
LEGACY_RANKING_VERSION = RANKING_V1


class RankingVersionError(ValueError):
    """모르는 순위 버전이거나, 파일에 적힌 버전이 기대와 다르다."""


def require_version(version) -> str:
    if version not in RANKING_VERSIONS:
        raise RankingVersionError(
            f"모르는 순위 버전입니다: {version!r} (아는 것: {', '.join(RANKING_VERSIONS)})")
    return version


def diagnosis_filename(version: str) -> str:
    """버전마다 다른 진단 결과 파일. v1은 옛 이름 그대로다."""
    require_version(version)
    return "label_diagnosis.json" if version == RANKING_V1 else f"label_diagnosis.{version}.json"


def ruler_filename(version: str) -> str:
    """버전마다 다른 자 기록 파일. v1은 옛 이름(`ruler.json`) 그대로다.

    진단 결과가 버전마다 따로인데 자 기록만 데이터셋에 하나면, 다른 프로파일로 v2를 돌린
    뒤 v1 결과를 열 때 **v2의 자가 붙어 나온다**(docs/next-work-2026-09-15.md S3).
    """
    require_version(version)
    return "ruler.json" if version == RANKING_V1 else f"ruler.{version}.json"


def ranking_version_of(data) -> str:
    """진단 결과가 어느 버전으로 만들어졌나. 기록이 없으면 옛 v1."""
    if not isinstance(data, dict):
        raise RankingVersionError("진단 결과가 사전이 아닙니다.")
    ranking = data.get("ranking")
    if ranking is None:
        return LEGACY_RANKING_VERSION
    return require_version(ranking.get("ranking_version") if isinstance(ranking, dict) else None)


def legacy_metadata() -> dict:
    """버전 기록이 없는 옛 결과에 붙이는 설명. v1이 실제로 하던 일 그대로다."""
    rule = ("계통 유형(present_types) 후보를 먼저, 그 안에서 severity 내림차순. "
            "계통 유형은 severity도 다시 매긴다(rescore)")
    return {
        "ranking_version": RANKING_V1,
        "ranking_scope": "mixed_queue",
        "ranking_signal": {"labelled_candidates": rule, "missing_candidates": rule},
        "dataset_boost_affects_order": True,
        "tie_break_rule": "안정 정렬 — 키가 같으면 진단이 낸 순서(이미지 이름순, 이미지 안에서는 판정 단계 순)",
    }
