/**
 * 오류 유형의 한글 이름 — 화면 전체가 여기 하나만 본다.
 *
 * 예전에는 ConditionsTable과 PerformanceChart가 각자 사본을 들고 있었고,
 * 주석으로 "한 곳에만 새 유형을 추가하면 다른 화면엔 영어 타입명이 그대로
 * 노출됨"이라고 경고해 뒀다. 경고에 기대는 대신 사본을 없앤다 — 같은 목록이
 * 여러 곳에 있다가 조용히 어긋나는 건 이 프로젝트에서 반복해서 나온 사고다.
 *
 * 백엔드에도 같은 이름의 표가 둘 있다(report.py의 TYPE_LABELS는 조건 type
 * 기준, upload.py의 SUSPICION_LABELS는 박스 단위 판정 기준). 그쪽은 API가
 * 이미 label을 함께 내려주므로 화면이 직접 매핑할 일이 없다. 여기 표는
 * label을 안 주는 응답(조건별 지표)에만 쓴다.
 */
export const TYPE_LABELS: Record<string, string> = {
  none: "기준선",
  width: "가로 오류",
  height: "세로 오류",
  rotation: "회전각 오류",
  translation_x: "가로이동 오류",
  translation_y: "세로이동 오류",
  scale: "스케일 오류",
  missing: "라벨 누락",
  duplicate: "라벨 중복",
  class_swap: "클래스 오기입",
};

/** 모르는 유형이면 원래 값을 그대로 보여준다 — 빈칸보다는 낫다. */
export function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type;
}
