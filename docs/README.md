# AIDA Docs 인덱스

이 폴더는 AIDA 프로젝트를 처음 보는 사람(팀원, 멘토, 또는 AI 어시스턴트)이
별도 설명 없이도 프로젝트 배경·기술·구조·의사결정 이유를 파악할 수 있도록 만든 문서 모음이다.

## 읽는 순서

1. [00-overview.md](./00-overview.md) — 프로젝트가 뭔지, 왜 하는지 (1분 요약)
2. [01-technology.md](./01-technology.md) — 핵심 기술 원리, 특허 연계
3. [02-architecture.md](./02-architecture.md) — 시스템/코드 구조
4. [03-experiment-design.md](./03-experiment-design.md) — 기술 검증 실험 설계
5. [04-api-reference.md](./04-api-reference.md) — 백엔드 API 명세
6. [05-glossary.md](./05-glossary.md) — 용어 사전 (객체탐지 도메인 배경지식 없어도 이해 가능)
7. [06-decisions.md](./06-decisions.md) — 주요 의사결정과 이유 (ADR 로그)
8. [07-roadmap.md](./07-roadmap.md) — 사업화 로드맵
9. [08-professor-review-email.md](./08-professor-review-email.md) — 교수님 기술 검토 요청 메일 완성본
10. [09-getting-started.md](./09-getting-started.md) — **새 세션/새 개발자용 진입점**
11. [10-competition-brief.md](./10-competition-brief.md) — 공식 공고문 기준 대회 일정·평가기준·시상 요약
12. [11-professor-feedback.md](./11-professor-feedback.md) — 김성호 교수님 기술 검토 회신 및 대응 방안
13. [12-experiment-results.md](./12-experiment-results.md) — 핵심 7개 조건 실측 결과 및 분석
14. [13-ppt-visuals-checklist.md](./13-ppt-visuals-checklist.md) — 13개 조건 전체 결과 나온 후 PPT에 넣을 그래프·다이어그램 체크리스트
15. [14-dashboard-enhancement-plan.md](./14-dashboard-enhancement-plan.md) — 실험 완료 후 진행할 대시보드 고도화(상세 통계 표·CSV 다운로드) 계획
16. [15-non-technical-guide.md](./15-non-technical-guide.md) — 비전공자 팀원용 테스트 결과·프로그램 흐름 설명서
17. [16-obb-adoption-review.md](./16-obb-adoption-review.md) — OBB 도입 범위·비용·후속 로드맵 검토
18. [17-professor-feedback-response.md](./17-professor-feedback-response.md) — 교수님 피드백에 대한 답변 및 통합 실험 결과 보고서 (실측 결과 포함)
19. [../CHANGELOG.md](../CHANGELOG.md) — 개발 변경 이력

## 한 줄 요약

AIDA는 국방과학연구소 특허(10-2664201) 기반으로, 참값 바운딩박스에 통제된 오류를
주입해 만든 "가상 에러 데이터셋"으로 객체탐지 모델을 학습시키고, 그 성능 저하 패턴을
실제 고객 데이터셋의 성능과 비교해 라벨 오류 유형을 진단·인증하는 B2B 플랫폼이다.
