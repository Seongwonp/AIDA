/**
 * 재검수 순위 버전 (docs/adr-ranking-separation.md).
 *
 * 이름은 backend `app/ranking.py`·experiment `label_diagnosis.py`와 같다.
 * v1은 지금까지의 제품 순서, v2는 층마다 후보 단위 신호만 쓰는 시험 버전이다.
 */
export const RANKING_V1 = "aida_v1_systematic_boost";
export const RANKING_V2 = "aida_v2_candidate_iou";
export const RANKING_VERSIONS = [RANKING_V1, RANKING_V2] as const;

const LABELS: Record<string, string> = {
  [RANKING_V1]: "v1 · 기존 제품 순서",
  [RANKING_V2]: "v2 · 후보 단위 순서 (시험)",
};

const SHORT: Record<string, string> = { [RANKING_V1]: "v1", [RANKING_V2]: "v2" };

/** 사람이 읽는 이름. 모르는 버전은 ID를 그대로 보여 준다 — 지어내지 않는다. */
export const rankingLabel = (version: string) => LABELS[version] ?? version;
export const rankingShort = (version: string) => SHORT[version] ?? version;
