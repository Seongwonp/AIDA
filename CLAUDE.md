# AIDA 작업 안내

## 현재 상태 — 2026-09-15

> **`git pull` 직후 이것부터 읽는다.** 할 일 순서표는
> [`docs/next-work-2026-09-15.md`](docs/next-work-2026-09-15.md), 최근 경위는
> [`docs/HANDOFF_2026-09-14.md`](docs/HANDOFF_2026-09-14.md).

**예비 비교(prelim1)는 끝났고, 현재 제품 순서가 단순 IoU 순서보다 나빴다.** 기존 라벨 후보
상위 90건에서 판정자가 오류로 본 라벨이 AIDA 제품 순서 4건, 단순 기준선(`1 − label_iou`)
14건, 차이 −10, 95% 구간 [−18, −2]. 판정자 1인(개발자)·KITTI Car 300장·탐색이고, 독립 산술
감사로 숫자를 확인했다 — [`docs/prelim1-results.md`](docs/prelim1-results.md).

그 뒤 사용자가 정한 것:

- **순위 분리 (C안 구조 + 임시 A안).** 데이터셋 진단이 후보 순서를 바꾸지 않게 나눴다.
  `aida_v1_systematic_boost`(기본, 기존 순서)와 `aida_v2_candidate_iou`(시험, 기존 라벨은
  `1 − label_iou`, 누락은 심각도)가 있다. **v2는 평가하지 않았다** —
  [`docs/adr-ranking-separation.md`](docs/adr-ranking-separation.md).
- **목적 A — 비상업 연구 시제품.** `ultralytics`가 AGPL-3.0, 자의 학습 데이터 KITTI는 비상업
  조건이다 — [`docs/evaluation-data.md`](docs/evaluation-data.md) "이 단계의 목적".

**v2를 쓰면 기존 라벨 순서에서 AIDA 고유의 몫은 0이다** (v2 순서가 곧 기준선). 남은 가치
후보인 **후보 생성·누락 탐지·유형 설명은 아직 재지 않았다.** 지금 막힌 곳은 코드가 아니라
**다음 평가 데이터셋의 라이선스 확인**이다.

### 데스크탑에서 할 일 — 순서표 요약

자세한 완료 조건은 [`docs/next-work-2026-09-15.md`](docs/next-work-2026-09-15.md). **[사용자]**
항목을 Claude가 대신 정하지 않는다.

| ID | 무엇 | 누가 |
|---|---|---|
| **W0** | 시작 점검 — 세 층 검사 직접 실행, `46cffbd` 이후 CI, 보호 자료 해시 대조 | Claude |
| **W1** | 평가 데이터셋(우선 BDD100K)·`yolov8n.pt`·KITTI 라이선스 원문 확인 | **[사용자]** (Claude는 확인 목록만) |
| **W2** | 1차 비교 질문 하나 — Q-A 후보 생성 포함 / Q-B v1 대 v2 / Q-C 누락 층 기준선 | **[사용자]** |
| **W2** | ~~1차 비교 질문~~ **정했다 — Q-A 1차 + Q-C 보조** | 끝 |
| W3 | 최소 구현 — 모집단·방법별 예산·비교 모드·무작위 표본 | **끝 (2026-09-16)** |
| W4 | 소비된 개발 데이터로 실제 추론 → 합성 판정 → 집계 드라이런 | Claude, W3 뒤 |
| W5 | 데이터셋·개발/최종 경계·N·K·씨앗·1차 지표 결정, 사전 등록 커밋 | **[사용자]** + Claude 문서 |
| W6 | 받기·진단·묶음·가림 점검·판정 | **[사용자]** 승인·판정 |
| W7 | 집계·감사·결과 문서 | Claude |

**W0부터 시작하고, 사용자에게 W1·W2를 묻는다.** W2가 정해지기 전에는 새 기능을 만들지 않는다.
노트북 검토 의견은 Q-A가 먼저라는 것이다(결정 아님 — 순서표 W2 절).

### 넘지 말아야 할 선

- **prelim1과 그 300장은 소비된 개발 데이터다.** v2나 새 순서를 그것으로 검증하지 않고, 결과를
  본 뒤 그 데이터로 순서를 바꿔 다시 세지 않는다.
- 순위·규칙을 바꾸면 **새 버전 ID**를 붙인다. 승격 상한·문턱을 prelim1을 보고 고르지 않는다.
- 다음 비교는 **손대지 않은 데이터셋**과 **판정 전에 커밋한 사전 등록**이 있어야 한다. N·방법·씨앗·
  1차 지표·Δ 방침은 결과를 본 뒤 바꾸지 않는다.
- v2 묶음을 `iou_baseline`과 견주지 않는다 — 같은 순서라 차이 0이 "대등"으로 읽힌다(코드가 막는다).
- **실제 후보에는 정답이 없다.** 판정을 정답으로 부르거나 accuracy를 계산하지 않는다. 한 사람의
  판정은 **일관성**을 보여줄 뿐 정확성이 아니다.
- 이 단계의 결과를 **상업적 주장·영업 자료에 쓰지 않는다.** 법적 판단을 하지 않는다.
- 대용량 다운로드는 **용량·시간을 먼저 적고 사용자 승인 후** 한다.
- **보호 자료를 지우거나 고치지 않는다** — `uploads/30512dfcbfbb`(prelim1),
  `D:/AIDA-eval/prelim/prelim1_30512dfcbfbb/`, `uploads/ffffffffff01`~`07`(시간 파일럿, SHA-256은
  [`docs/HANDOFF_2026-09-12.md`](docs/HANDOFF_2026-09-12.md)).

### 멈춰 둔 것 — 시간·표본 크기

`s_plan = 5.02초`(timing5)로 `N_capacity`는 계산되지만 `N_required`는 근거가 없어 민감도 표뿐이다.
`D`·`T`·Δ·`N_final`은 **하나도 정하지 않았다.** prelim1의 작업 시간은 기록 끝이 잘려 쓰지 않는다.
새 판정 자료가 나올 때까지 멈춘다 —
[`docs/capacity-vs-sample-size.md`](docs/capacity-vs-sample-size.md) →
[`docs/n-required-plan.md`](docs/n-required-plan.md).

### 노트북과 데스크탑

`backend/app/data/uploads/`, `experiment/data/`, `experiment/runs/`는 gitignore라
`git pull`로 안 따라온다. **노트북에서는 문서·코드·검사만** 하고, 추론·판정·
파일럿은 데스크탑에서 한다.

## 먼저 읽을 문서

1. [`docs/next-work-2026-09-15.md`](docs/next-work-2026-09-15.md) — **다음 작업 순서표**
2. [`docs/prelim1-results.md`](docs/prelim1-results.md) · [`docs/prelim1-failure-analysis.md`](docs/prelim1-failure-analysis.md) — 결과와 사후 가설
3. [`docs/adr-ranking-separation.md`](docs/adr-ranking-separation.md) — 순위 버전 결정과 뒤집을 조건
4. [`docs/next-evaluation-proposal.md`](docs/next-evaluation-proposal.md) — 다음 평가 설계 틀·데이터셋 후보·법적 위험
5. [`docs/evaluation-data.md`](docs/evaluation-data.md) — 소비된 데이터 원장, 목적 A
6. [`docs/evaluation-adjudication-design.md`](docs/evaluation-adjudication-design.md) — 가림 판정·모집단·상위 N 합집합·판정자 간 불일치(미설계)
7. [`docs/prelim1-preregistration.md`](docs/prelim1-preregistration.md) — 다음 사전 등록의 형식
8. [`docs/testing-boundary.md`](docs/testing-boundary.md) — 검사 경계와 미검증 항목

`docs/20-local-claude-handoff.md`는 과거 OBB 작업 기록이므로 **현재 실행 지시로
쓰지 않는다.** R1~R5(docs/25 1단계)는 **끝났다** — 그 절을 지금 할 일로 읽지 않는다. **R6은
부분 완료**다: jsdom 흐름 검사는 CI에서 돌지만 계획이 요구한 **브라우저 통합
검사(Playwright 등)는 미완**이다. 경계는 [`docs/testing-boundary.md`](docs/testing-boundary.md).

## 환경과 검증

먼저 `git status`와 현재 브랜치를 확인한다. 사용자의 미커밋 변경은 보존한다. 최신 변경 수신은 `git pull --ff-only`를 사용하며 충돌을 강제 덮어쓰지 않는다.

Python 환경은 **둘로 나뉘어 있다.** 섞으면 없는 패키지를 찾게 된다.

| | 무엇이 있나 |
|---|---|
| `backend/venv` | FastAPI. **torch 없음** |
| `experiment/venv` | torch·ultralytics. **FastAPI 없음** |

`experiment/`의 스크립트와 `evaluation/` 모듈은 `experiment/venv`로 돌린다.
경로나 설치 여부를 추측하지 않고 먼저 확인한다. **문서에 적힌 검사 수를 이번
실행 결과로 보고하지 않는다** — 직접 돌려 보고 그 숫자를 쓴다.

최근 기록: **2026-09-16 데스크탑** experiment 451 · backend 300(건너뜀 0), 프론트 미변경 · 그 전 **2026-09-14** experiment 442 · backend 282(건너뜀 0) · frontend 183 ·
typecheck·lint·build exit 0. **2026-09-15 노트북**(CI와 같은 의존성만 깐 임시 환경) backend 281 통과·
1 건너뜀(`test_uploads_dir_agreement.py:100`, 외부 드라이브 없음) · experiment 442 통과, frontend
미실행, CI 미확인. 실험 검사 중 `test_config.py` 하위 프로세스가 `faulthandler` "access violation"을
찍지만 통과한다 — 원인 미확인(순서표 S4).
**2026-09-16 데스크탑** experiment 442 · backend 282(건너뜀 0) · frontend 183 · typecheck·lint·build exit 0,
CI는 `c1e3ac28`까지 전부 success, 보호 자료 해시 전부 일치 (W0 완료).

프론트 변경 시 `frontend`에서 관련 검사와 `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`를 실행한다. 백엔드 변경 시 해당 가상환경으로 `backend`의 pytest를 실행한다. 화면 통합 검사 도구가 없으면 기존 구성을 확인한 뒤 필요한 최소 구성을 추가한다. 실제 브라우저 확인과 자동 테스트 결과를 구분한다.

**가짜 진단 결과로 검사한 것을 실제 모델 추론 검증으로 표현하지 않는다.**
파일럿 후보에는 두 종류가 있고 섞어 읽으면 안 된다 — `injected_synthetic`(라벨에
오류를 주입한 것, 시간이 **하한**으로 나온다)과 `actual_diagnosis`(자를 돌려 나온
실제 후보). 코드가 `candidate_source`로 구분하고 하한이면 N 채택을 막는다.

**GPU는 진단 후보를 만들 때만 쓴다**(추론 1분 미만, 학습 없음). 그 외에는
필요 없다.

## 사용자 작업 원칙

- 설명은 한국어로 짧게 한다. 결과·검증·남은 문제 위주로 보고한다.
- 완료한 작업은 변경 범위를 검토하고 관련 파일만 커밋·푸시한다. 커밋 메시지는 변경 내용만 쓰고 AI 이름, `Co-Authored-By`, `Generated with` 같은 공동작성·생성 표기를 넣지 않는다. 기존 사용자 작성자 설정을 사용하며 임의의 신원을 만들지 않는다.
- 데이터·가중치·비밀값·로컬 사용자 경로를 새 문서나 커밋에 넣지 않는다. 기존 실험 결과를 지우거나 덮어쓰지 않는다.
- 장시간 GPU 작업·대용량 다운로드·유료 서비스는 예상 시간·용량·금액 상한을 제시하고 사용자 확인 후 실행한다. 외부 연락도 사용자 승인 후 한다. 일반 코드 수정·작은 테스트는 진행한다.

## 끝날 때 남길 인수인계

[`docs/next-work-2026-09-15.md`](docs/next-work-2026-09-15.md)의 순서표 상태와 `docs/25-advancement-roadmap.md`의 해당 작업 상태·완료 근거를 갱신하고, 저장 규약·테스트 경계가 바뀌면 관련 문서도 맞춘다. 계획 전체를 완료 처리하지 않는다. **이 파일 맨 위 "현재 상태"도 같이 고친다** — 진행 기록을 아래에 덧붙이기만 하면 처음 읽는 사람이 끝난 일을 할 일로 읽는다.

최종 보고에는 다음만 간결하게 남긴다:

1. 재현된 문제와 수정한 동작
2. 실행한 검사와 통과·실패·미실행 범위
3. 커밋 ID와 푸시 결과
4. 남은 위험과 다음 작업 ID

사용자가 다음 검토에서 이 기록만으로 구현 결과와 근거를 확인할 수 있어야 한다.
