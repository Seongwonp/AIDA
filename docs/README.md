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
| [25-advancement-roadmap.md](./25-advancement-roadmap.md) | **현재 실행 계획.** 저장 신뢰성 → 독립 평가 → 선택적 개선 → 사용자 검증. 다음 작업은 R1 |
| [../CLAUDE.md](../CLAUDE.md) | 데스크탑 작업 인수인계. R1 재현 절차·검증·완료 보고 원칙 |
| [24-development-plan.md](./24-development-plan.md) | 기존 장기 계획과 A·B·C 산출물 기록. 후속 검증과 우선순위는 25번을 따른다 |
| [23-plan.md](./23-plan.md) | 이전 연구 계획. 실험 배경과 미완료 과제의 기록 |
| [22-plan.md](./22-plan.md) | 앞 계획 (2026-09-05). 항목이 거의 다 닫혔다 — 무엇을 왜 했는지 남긴다 |
| [testing-boundary.md](./testing-boundary.md) | **검사가 무엇을 잡고 무엇을 못 잡는가.** 가짜와 진짜 추론의 경계 (docs/24 B) |
| [evaluation-protocol.md](./evaluation-protocol.md) | **평가 규약 초안.** 25번에 따른 독립성·통계·중단 기준 보완과 데이터 확정 후 최종 고정 필요 |
| [evaluation-data.md](./evaluation-data.md) | **독립 평가 데이터 후보와 겹침 확인.** 무엇을 빼야 하고 겹침을 어떻게 재는가 (docs/24 C1) |
| [review-model.md](./review-model.md) | **검수 판정의 식별·보관 규칙.** 무엇이 후보를 구분하고 서버/브라우저가 엇갈리면 누가 이기는가 (docs/24 B1) |
| [reproduction.md](./reproduction.md) | **무엇이 저장소에 있고 무엇이 없는가.** 환경·명령·복원 불가 항목·대회와 개인 개발의 구분 (docs/24 A2) |
| [current-evidence.md](./current-evidence.md) | **지금 유효한 주장과 근거 파일의 대응표.** 수치를 인용하기 전에 여기부터 본다 (docs/24 A1) |
| [21-next-plan.md](./21-next-plan.md) | **실험 기록의 본체.** 결론이 뒤집힌 이력과 정정 표시를 보존한다 |
| [../CHANGELOG.md](../CHANGELOG.md) | 날짜별 변경 이력 |
| [09-getting-started.md](./09-getting-started.md) | 새 세션·새 개발자용 진입점 |

## 배경과 원리 (대체로 유효)

| 문서 | 무엇 | 주의 |
|---|---|---|
| [00-overview.md](./00-overview.md) | 프로젝트가 뭔지, 왜 하는지 | 2026-09 기준으로 갱신됨 |
| [01-technology.md](./01-technology.md) | 핵심 기술 원리, 특허 연계 | 현재 수치·한계는 current-evidence, 세부 이력은 21번 참고 |
| [02-architecture.md](./02-architecture.md) | 시스템·코드 구조 | 큰 틀은 유효. 파일 목록은 늘었다 |
| [05-glossary.md](./05-glossary.md) | 용어 사전 | 유효 |
| [06-decisions.md](./06-decisions.md) | 주요 의사결정과 이유 (ADR) | 2026-07까지의 결정만 |
| [04-api-reference.md](./04-api-reference.md) | 백엔드 API 명세 | 엔드포인트가 추가됐다 — 코드가 최신 |

## 실험 (21번이 최신, 나머지는 그 시점 기록)

| 문서 | 무엇 | 주의 |
|---|---|---|
| [03-experiment-design.md](./03-experiment-design.md) | 검증 실험 설계 | **7개 조건 시절.** 현재 조건·시드 수는 실험마다 다름 |
| [12-experiment-results.md](./12-experiment-results.md) | 13개 조건 실측 결과 | **13개 조건 시절.** 현재 수치는 current-evidence 참고 |
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
| [20-local-claude-handoff.md](./20-local-claude-handoff.md) | 과거 OBB 작업 인수인계. 현재 지시는 루트 CLAUDE.md 참고 |

## 문서 관리 기준

현재 작업 상태는 25번, 성능 주장은 current-evidence, 검사 범위는 testing-boundary에서 관리한다. 다른 문서는 해당 문서로 연결하고 테스트 수나 작업 상태를 중복 기재하지 않는다. 과거 실험과 대회 기록은 보존하며 정정은 날짜와 후속 근거를 붙인다.

## 프로젝트 요약

AIDA는 국방과학연구소 특허(10-2664201) 기반으로, 참값 바운딩박스에 통제된 오류를
주입해 만든 "가상 에러 데이터셋"으로 객체탐지 모델을 학습시키고, 그 성능 저하
패턴을 고객 데이터셋의 성능과 비교해 라벨 오류 유형을 진단한다. 산출물은
**재검수 우선순위 목록**이다.

현재 실험에서 **기준 모델의 적합성이 진단 품질에 큰 영향을 주었다.** COCO 평가에서는 자기 도메인 모델 82.4%, KITTI 모델 26.0%였다. KITTI 실험의 94.0%는 별도 조건의 결과이므로 직접 전후 비교하지 않는다. 조건과 한계는 [현재 근거표](current-evidence.md)를 따른다. 자연 오류와 실제 사용자 효과는 미검증이다.
