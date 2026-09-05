# 14. 대시보드 고도화 기록 — 상세 통계 표 + CSV 다운로드
<!-- 시점 표시 -->

> **끝난 일의 기록이다.** 2026 국방기술 창업경진대회는 2026-08-19에 2차 예선에서 탈락했고, 그 뒤로 프로젝트는 발표 준비가 아니라 기술 검증으로 방향을 바꿨다. 이 문서는 **당시 상태 그대로 두며 갱신하지 않는다** — 지금 시스템과 다른 것이 정상이다. 현재 상태는 저장소 README와 [21-next-plan.md](./21-next-plan.md)를 볼 것.


**상태: 구현 반영 완료.** 13개 조건 전체 실험 결과가 커밋된 뒤, 기존 1페이지
대시보드에 상세 통계 표, CSV 다운로드, IoU 감소율 컬럼, ROI 추정 카드를 추가했다.
기존 결과 CSV와 PDF 보고서는 보존한다.

## 배경 및 범위 판단

랜딩페이지·마케팅 사이트는 만들지 않기로 함(팀 논의 결과) — 2차 예선 배점은
"웹사이트가 예쁜가"가 아니라 "기술이 실제로 작동하고 결과가 진짜인가"를 보고,
그 스토리는 이미 PPT가 담당한다. 반면 **상세 통계 표·CSV 다운로드는 다르다** —
이건 이미 만든 실험 데이터의 깊이를 그대로 드러내는 것이라 "해결방안 및 MVP
구현 가능성"(2차 예선 배점 25점, 최고 배점)을 직접 뒷받침한다. `06-decisions.md`의
"MVP 데모는 결과 조회 대시보드 1페이지로 최소화" 결정과도 충돌하지 않음 —
새 페이지를 만드는 게 아니라 같은 페이지 안에서 깊이를 더하는 것이기 때문.

## 목표

1. 지금 차트에는 mAP@0.5 저하율만 보이는데, 13개 조건 전체의 상세 지표
   (map50, map50_95, precision, recall, performance_drop_pct)를 표로 펼쳐서 보여준다.
2. 그 데이터를 CSV로 그대로 다운로드할 수 있게 한다 — 심사위원이 "숫자 좀
   보여달라"고 하면 화면 캡처가 아니라 실제 파일을 건넬 수 있어야 신뢰감이 다르다.

## 구현 범위 (우선순위순)

### 1. [필수] 상세 통계 표 컴포넌트

- **위치**: `PerformanceChart` 아래, `ErrorReportTable` 위에 새 카드 섹션으로 추가.
- **데이터 출처**: 기존 `GET /api/conditions` 그대로 사용 — **백엔드 변경 불필요**
  (이미 `ConditionMetric`에 map50/map50_95/precision/recall/performance_drop_pct가
  다 있음, `frontend/src/types.ts` 참고).
- **구현**: `frontend/src/components/ConditionsTable.tsx` 신규 생성. 13행(clean
  포함) 전부 표시, 기존 `.report-table` CSS 클래스 재사용해 톤 통일. 정렬 기준은
  `config.CONDITIONS` 순서(clean → width → height → rotation) 그대로.
- **App.tsx**: `<ConditionsTable conditions={conditions} />`를 `PerformanceChart`와
  `ErrorReportTable` 사이에 추가.

### 2. [필수] CSV 다운로드 버튼

- **접근 방식**: 프론트엔드에서 이미 받아온 `conditions` 배열(JSON)을 CSV 문자열로
  변환해 `Blob` + `URL.createObjectURL`로 클라이언트 사이드 다운로드. **백엔드 변경
  불필요**, 새 의존성도 필요 없음(순수 문자열 조합으로 충분한 규모).
- **위치**: 상세 통계 표 카드 헤더 옆에 작은 버튼("CSV 다운로드"), 기존
  `.refresh-button`과 같은 스타일 톤으로.
- **파일명 제안**: `aida_conditions_{YYYYMMDD}.csv`.

### 3. [선택, 시간 남으면] IoU 감소율 컬럼 통합

- **왜**: `experiment/iou_table.csv`(교수님 피드백 대응으로 이미 생성됨,
  [11-professor-feedback.md](./11-professor-feedback.md) 3번)의 `mean_iou`,
  `mean_iou_drop_pct`를 같은 표에 합치면 "오류 강도(IoU) → 성능 저하"라는
  인과 스토리가 표 하나로 완성된다([13-ppt-visuals-checklist.md](./13-ppt-visuals-checklist.md)
  3번 항목과 동일한 데이터).
- **구현 필요 범위**: 이건 백엔드 변경이 필요하다 —
  `backend/app/routers/report.py`의 `get_conditions()`에서 `iou_table.csv`를
  추가로 읽어 `condition` 기준으로 join, `ConditionMetric` 모델에
  `mean_iou`/`mean_iou_drop_pct` 필드 추가. `iou_table.csv`를
  `backend/app/data/` 아래로 복사(또는 심볼릭)해와야 함 — 지금은
  `experiment/iou_table.csv`에만 있음.
- **시간이 부족하면 생략 가능** — 1, 2번만으로도 배점 대응은 충분하고, 이건
  "있으면 더 좋은" 항목이다.

## 실행 순서

1. CUDA 실험 완료 확인 — `backend/app/data/metrics.csv` 13행이 전부 동일 50epoch
   실측치인지 확인 (`docs/12-experiment-results.md` 갱신과 같은 타이밍)
2. `ConditionsTable.tsx` 작성 + `App.tsx`에 배치
3. CSV 다운로드 버튼 구현
4. `npx tsc -b` 통과 확인 → 브라우저에서 실제 클릭해 다운로드 파일 열어보고 검증
5. (여유 있으면) IoU 컬럼 통합

## 디자인 원칙 (기존 결정 유지)

- 흑백 + 형광(#CCFF00) 최소 사용 톤 유지 — `06-decisions.md` "발표자료 디자인"
  결정과 동일 원칙을 대시보드에도 적용
- 새 페이지가 아니라 기존 1페이지 안에서의 확장 — 스크롤 몇 번 더 내려가는 정도
- 표 헤더는 담백하게: "조건별 상세 지표" 정도, 과장된 카피 금지(교수님 피드백
  5번 톤 원칙과 동일선상)
