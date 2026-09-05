# AIDA Docs 인덱스

이 폴더는 AIDA 프로젝트를 처음 보는 사람(팀원, 멘토, 또는 AI 어시스턴트)이
별도 설명 없이도 배경·기술·구조·의사결정 이유를 파악할 수 있도록 만든 문서
모음이다.

> **문서마다 시점이 다르다.** 2026-08-19에 대회에서 떨어지면서 프로젝트
> 방향이 발표 준비에서 기술 검증으로 바뀌었다. 그 전에 쓴 문서는 **그때의
> 기록**이고 지금 시스템과 다를 수 있다. 아래 표에 성격을 적어뒀으니 그것부터
> 보고 읽을 것.

## 지금 상태를 알고 싶다면

| 문서 | 무엇 |
|---|---|
| [../README.md](../README.md) | **여기부터.** 무엇이 되고 무엇이 안 되는지, 실행 방법, 환경변수 |
| [22-plan.md](./22-plan.md) | **다음에 뭘 할지.** 비용순, 실측 GPU 시간 포함. 낡으면 갈아엎는다 |
| [21-next-plan.md](./21-next-plan.md) | **실험 기록의 본체.** 절 36개, 결론이 뒤집힌 이력까지. 목차에 정정 표시가 있다 |
| [../CHANGELOG.md](../CHANGELOG.md) | 날짜별 변경 이력 |
| [09-getting-started.md](./09-getting-started.md) | 새 세션·새 개발자용 진입점 |

## 배경과 원리 (대체로 유효)

| 문서 | 무엇 | 주의 |
|---|---|---|
| [00-overview.md](./00-overview.md) | 프로젝트가 뭔지, 왜 하는지 | 2026-09 기준으로 갱신됨 |
| [01-technology.md](./01-technology.md) | 핵심 기술 원리, 특허 연계 | 원리는 유효. **조건 수·수치는 21번이 최신** |
| [02-architecture.md](./02-architecture.md) | 시스템·코드 구조 | 큰 틀은 유효. 파일 목록은 늘었다 |
| [05-glossary.md](./05-glossary.md) | 용어 사전 | 유효 |
| [06-decisions.md](./06-decisions.md) | 주요 의사결정과 이유 (ADR) | 2026-07까지의 결정만 |
| [04-api-reference.md](./04-api-reference.md) | 백엔드 API 명세 | 엔드포인트가 추가됐다 — 코드가 최신 |

## 실험 (21번이 최신, 나머지는 그 시점 기록)

| 문서 | 무엇 | 주의 |
|---|---|---|
| [03-experiment-design.md](./03-experiment-design.md) | 검증 실험 설계 | **7개 조건 시절.** 지금은 27개 |
| [12-experiment-results.md](./12-experiment-results.md) | 13개 조건 실측 결과 | **13개 조건 시절.** 지금은 27개 + 시드 7개 |
| [16-obb-adoption-review.md](./16-obb-adoption-review.md) | OBB 도입 검토 | 유효 |

## 끝난 일의 기록 (고치지 않는다)

대회는 2026-08-19에 2차 예선에서 탈락했다. 아래는 그 준비 과정의 기록이라
**당시 상태 그대로 둔다.** 지금 시스템과 다른 것이 정상이다.

| 문서 | 무엇 |
|---|---|
| [07-roadmap.md](./07-roadmap.md) | 사업화 로드맵 (사업계획서 기준) |
| [08-professor-review-email.md](./08-professor-review-email.md) | 교수님 기술 검토 요청 메일 |
| [10-competition-brief.md](./10-competition-brief.md) | 대회 일정·평가기준 요약 |
| [11-professor-feedback.md](./11-professor-feedback.md) | 교수님 검토 회신과 대응 |
| [13-ppt-visuals-checklist.md](./13-ppt-visuals-checklist.md) | PPT 그래프 체크리스트 |
| [14-dashboard-enhancement-plan.md](./14-dashboard-enhancement-plan.md) | 대시보드 고도화 계획 |
| [15-non-technical-guide.md](./15-non-technical-guide.md) | 비전공자 팀원용 설명서 |
| [17-professor-feedback-response.md](./17-professor-feedback-response.md) | 교수님 피드백 답변 + 통합 결과 보고서 |
| [18-presentation-material-guide.md](./18-presentation-material-guide.md) | 발표자료 제작 가이드 |
| [19-report-sections-6-12-draft.md](./19-report-sections-6-12-draft.md) | 보고서 6~12장 초안 |
| [20-local-claude-handoff.md](./20-local-claude-handoff.md) | 원격↔로컬 작업 인수인계 방식 |

## 한 줄 요약

AIDA는 국방과학연구소 특허(10-2664201) 기반으로, 참값 바운딩박스에 통제된 오류를
주입해 만든 "가상 에러 데이터셋"으로 객체탐지 모델을 학습시키고, 그 성능 저하
패턴을 고객 데이터셋의 성능과 비교해 라벨 오류 유형을 진단한다. 산출물은
**재검수 우선순위 목록**이다.

지금까지 확인된 가장 중요한 사실: **진단 품질을 정하는 건 알고리즘이 아니라
기준 모델이 그 데이터에 맞는가**다. 같은 데이터를 자만 바꿔 진단하면 상위 10%
정밀도가 94.0% ↔ 26.0%로 갈린다 (21번 AG·AI).
