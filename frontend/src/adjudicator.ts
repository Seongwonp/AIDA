/**
 * 판정자 구분 (사전 등록 D8, 개정 6).
 *
 * 주 판정자(`primary`)의 요청은 예전 주소 그대로 보낸다 — 쿼리를 붙이지 않는다. 보조 판정자(D8-3
 * 재판정 `primary_retest` 등)는 `?adjudicator=`를 붙이고, 서버가 보조 표본만 주 판정 화면 순서에서
 * 추려 보내며 판정·작업 기록을 그 판정자의 파일에 따로 저장한다.
 */
export const PRIMARY_ADJUDICATOR = "primary";

/** 서버(`ADJUDICATOR_PATTERN`)와 같은 규칙. 형식이 틀리면 화면을 열지 않는다. */
export const isAdjudicatorId = (value: string): boolean => /^[a-z0-9_-]{1,20}$/.test(value);

export const adjudicatorQuery = (adjudicator: string = PRIMARY_ADJUDICATOR): string =>
  adjudicator === PRIMARY_ADJUDICATOR ? "" : `?adjudicator=${encodeURIComponent(adjudicator)}`;
