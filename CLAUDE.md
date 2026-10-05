# AIDA 작업 안내

> **2026-10-06 데스크탑(2단계):** 재추론 1,023회 완료(49분) — 과거 순서로 seeded 값 **812/812·156/156** 재현, self·KITTI Car 지목·TP 29/29·26/26. 같은 k에서 AIDA 현재 순서는 8개 자 모두 전체 라벨 기준선(무작위·1−IoU·ObjectLab 0.27~0.35)보다 높다 — [명세 6절](docs/paper/controlled-baseline-spec.md), 근거표 A2. **사용자 결정:** 초안 수치를 legacy/current 중 어느 순서로 쓸지·기준선 표 반영(`docs/paper/open_items.md` 6절), 명세의 제안 규칙 2개(후보<k일 때 분모 k, 동점 키) 확정. 검사 experiment 608.

> **2026-10-06 데스크탑:** 통제 기준선 1단계 재현 확인 **통과** — 과거 순서 `legacy_severity_v0`로 자기 도메인 자·시드 42·29조건이 seeded 값과 **29/29 일치**. 09-05의 캐시↔seeded 불일치 원인은 신뢰도 프로파일(캐시 실행만 `reliability_profile_mc.json` 사용) — [명세](docs/paper/controlled-baseline-spec.md), `experiment/planning_evidence/controlled_baseline_stage1_repro_2026-10-06.json`. **2단계(재추론 약 1,023회·1.3~2.2시간)는 별도 승인 대기.** 검사 experiment 604.

> **2026-10-05 데스크탑:** 통제 기준선 읽기 전용 목록 조사 완료 — [데스크탑 목록](docs/paper/controlled-baseline-desktop-inventory.md). 자료 복구 필요 없음(확인 범위), 박스 단위 기준선은 기존 가중치 재추론 필요(약 1,023회·82k장·1.3~2.2시간, **미승인·미실행**). 캐시가 seeded 시드 42 값을 재현하지 못하는 조건이 많다(원인 미상). 검사 backend 370 · experiment 594 · frontend 191 · typecheck/lint/build 0. 다음: 노트북 기준선 명세(과거 순서 재현 여부·범위) → 재추론 승인.

> **2026-10-01 노트북:** 통제 기준선 읽기 조사 완료. [캐시·평가 단위 감사](docs/paper/controlled-baseline-audit.md). 다음은 데스크탑 상세 캐시 목록 확인과 비교 명세 확정. 기준선 실행·코드 수정은 미착수, val 미접근.

> **2026-09-27 노트북 인수인계:** [데스크탑 실행 절차](docs/desktop-handoff-2026-09-27.md). 전체 장면+크롭 입력, 가림 입력 검증, 원래 상위 N 미판정 거부를 보강했다. 다음은 데스크탑 환경 확인과 train 연습. 사전 등록 미확정·val 미개봉. 아래 과거 상태는 해당 날짜 기록이다.

## 현재 상태 — 2026-09-27

> **2026-09-29:** 논문 초안 `docs/paper/` 작성됨(Q-A 결과 대기) — 연구 작업 시 아래 "논문 연동 규칙" 절을 따른다.
>
> **방향을 정했다 — 연구 논문으로 정리한다.** 창업·제품 목표는 접는다(라이선스 차단점과
> prelim1 결과). 주장은 하나로 좁힌다: *데이터셋 단위 유형 역진단은 박스 단위 재검수
> 순위를 개선하지 못하고, 진단 품질은 자의 도메인 적합이 지배한다.* 남은 실험은
> nuImages Q-A 하나다(W5 사전 등록 → 사람 1인 + AI 보조 30% → 집계). 비교 방법에 **Cleanlab ObjectLab
> 기준선을 추가**했다(박스 단위 적응 기준선).
>
> 2026-09-27 노트북 작업: 라벨 파일의 깨진 줄 하나가 진단 전체를 죽이던 결함을 고쳤다
> (`label_diagnosis.parse_yolo_labels`, 이미지 단위로 건너뛰고 `summary.skipped_images`에
> 기록). 인수인계·조언·대회 문서 20개를 [`docs/archive/`](docs/archive/README.md)로 옮기고
> 링크 371개를 검사했다(깨진 것 0). **ObjectLab 기준선을 구현했다** — `experiment/objectlab_baseline.py`가
> 진단 모집단 행에 `objectlab_score`·`objectlab_overlooked`를 붙이고, 백엔드 방법
> `all_label_objectlab`·`unmatched_objectlab`이 그것으로 줄 세운다(cleanlab 없으면 방법이 안 생긴다).
> D1~D9 제안값은 [`docs/qa-preregistration-proposal-2026-09-27.md`](docs/qa-preregistration-proposal-2026-09-27.md).
> D8(사람 전량 + AI 보조 30%)·D9(가: IoU 0 포함, 고정 씨앗 동점)는 사용자 검토로 정리됐다.
> **확정 전 구현 4개는 끝났다(2026-09-27 밤):** 높이 필터(D2, `min_label_height_px`), 판정자 분리·보조 표본·일치도(D8,
> `adjudicator`·`auxiliary_sample_*`·`GET .../agreement`), 동점 씨앗(D9, `tie_seed`·`tie_key`), 외부 자 선택
> (`?ruler=nuimages_car_v1_e100`, SHA-256 대조). 남은 것은 **확정본의 실행 명세**(자 SHA, AI 판정자 식별자·프롬프트)와
> 사용자의 확정 커밋이다 — 제안 문서 "확정본에 남은 실행 명세". **val은 확정본 커밋 전까지 열지 않는다.**
> Codex 검토 반영(2026-09-27 밤): v2 기존 라벨 층의 AIDA 평가 순서는 `1 − label_iou`+공통 `tie_key`(제품 순위 아님),
> 누락 층은 세 방법 기술통계 내보내기 허용. 실행 순서: **연습 → 지침·프롬프트 고정 → 확정본 커밋 → val 표집·진단 →
> 묶음 고정·점검(실제 건수는 실행 기록에) → 본 판정.**
> **새 보류 사유(2026-09-27 밤):** 부트스트랩 재표본의 상위 N에 **미판정 후보**가 들어 수확 0으로 세어진다.
> 회귀 검사·합성 시뮬레이션·고정 재표본 합집합 도구(`evaluation/coverage.py`, `sim_unjudged.py`)를 더했고 분석
> 방식은 **정하지 않았다** — [`docs/unjudged-bootstrap-review-2026-09-27.md`](docs/unjudged-bootstrap-review-2026-09-27.md).
> Codex가 **안 (a)**(고정 재표본 합집합 전량 판정)를 추천했고 연결 구현을 끝냈다(`coverage_iterations`·`coverage_seed` →
> `bootstrap_coverage` 지문 고정 → 판정 목록·저장·내보내기 → `require_judged_top_n`). 사전 등록 확정·val 개봉은 **아직 보류.**
> 최종 분석 경로 `experiment/analyze_qa.py`가 `require_judged_top_n=True`를 강제하고 묶음의 coverage 설정·입력 지문과
> 다르면 중단한다. 연습 자료: `docs/practice-judging-plan.md`, 프롬프트 초안 `docs/ai-adjudicator-prompt-draft.md`,
> `check_run_environment.py`(자 SHA·버전 — 데스크탑에서), `render_adjudication_images.py`. 판정 상한 C는 연습 뒤 사용자가 정한다.
> 아래 09-16 상태는 그대로 유효하다.

## 그 전 상태 — 2026-09-16

> **`git pull` 직후 이것부터 읽는다.** 최근 경위는
> [`docs/archive/HANDOFF_2026-09-16.md`](docs/archive/HANDOFF_2026-09-16.md), 할 일 순서표는
> [`docs/next-work-2026-09-15.md`](docs/next-work-2026-09-15.md).
>
> **W1은 정했다 — nuImages(비상업 연구·포트폴리오).** train 분할·Car 자 `car_v1` 학습·적합도 확인까지
> 끝났다(fit_check 69.9%, 작은 차 맹점 — [`docs/nuimages-data-plan.md`](docs/nuimages-data-plan.md) 5절). 100에폭 재학습
> `car_v1_e100`도 끝났다(ruler_val fitness 0.504→0.516, fit_check 71.6%) — **어느 자를 쓸지는 사용자 결정.**
> W5 조언([`docs/archive/advice-w5-2026-09-16.md`](docs/archive/advice-w5-2026-09-16.md))으로 기록 단위 묶음(`groups.json`)·높이
> 층별 집계·사전 등록 뒤에만 도는 val 표집을 구현했다. 업로드 진단에서 nuImages 자를 고르는 길은
> 2026-09-29에 프론트까지 이었다(자 선택 칸·`listRulers`·결과에 자 ID/가중치 해시 앞 12자). **남은 구현 없음** (AI 보조 판정자·묶음 설정은 API/CLI 경로만 있고 화면은 없다 — 의도한 범위).
> **지금 막힌 곳은 W5 사전 등록(사용자 결정)이다.** val은 그 커밋 전까지 열지 않는다.
> **2026-09-29 데스크탑:** 환경 확인(자 SHA `fffecf52…`, cleanlab 2.9.0)·연습 묶음 `practice1`(train fit_check, 판정 대상 172 = 상위N∪K 89 + 재표본 추가 83, 판정 0건) 완료 —
> `experiment/planning_evidence/practice1_bundle_2026-09-29.json`. **새 사용자 결정:** Q-C의 `unmatched_objectlab` 모집단이 0건(cleanlab 문턱 0.95, 자 최대 확신도 0.93) — **사용자가 (a) 측정 불가 보고로 정했다**(사전 등록 4절에 기록). 다음은 사용자 연습 판정(20~60건).
> W2~W4(1차 질문 선택·최소 구현·경로 드라이런)는 2026-09-16에 끝났다. 같은 날 저녁에 결정이
> 필요 없는 일을 마쳤다 — **자 기록 버전별 분리(S3), access violation 조사(S4), 판정 API 부하 측정,
> 사전 등록 초안** [`docs/qa-preregistration-draft.md`](docs/qa-preregistration-draft.md)(값은 전부 빈칸),
> **판정자 둘 이상 설계 초안** [`docs/multi-adjudicator-design.md`](docs/multi-adjudicator-design.md).

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
**W5 사전 등록의 사용자 결정(D1~D9)**이다 — 특히 **D9 `all_label_iou`의 동점·IoU 0 라벨 처리**를
판정 전에 정해야 한다([`docs/qa-preregistration-draft.md`](docs/qa-preregistration-draft.md) 0절·6절).

### 데스크탑에서 할 일 — 순서표 요약

자세한 완료 조건은 [`docs/next-work-2026-09-15.md`](docs/next-work-2026-09-15.md). **[사용자]**
항목을 Claude가 대신 정하지 않는다.

| ID | 무엇 | 누가 |
|---|---|---|
| **W0** | 시작 점검 — 세 층 검사 직접 실행, `46cffbd` 이후 CI, 보호 자료 해시 대조 | Claude |
| W1 | ~~라이선스 원문 확인~~ **정했다 — nuImages** (BDD100K 공식 배포 중단) | 끝 (2026-09-16) |
| **W2** | ~~1차 비교 질문~~ **정했다 — Q-A 1차 + Q-C 보조** | 끝 (2026-09-16) |
| W3 | 최소 구현 — 모집단·방법별 예산·비교 모드·무작위 표본 | **끝 (2026-09-16)** |
| **W5** | 자·경계·N·K·씨앗·1차 지표·Δ 방침·**동점 규칙(D9)**, 사전 등록 커밋 | **[사용자] — 여기서 막힌다** |
| W4 | 경로 드라이런 — 실제 추론·묶음·합성 판정·집계 | **끝 (2026-09-16)** |
| W6 | 받기·진단·묶음·가림 점검·판정 | **[사용자]** 승인·판정 |
| W7 | 집계·감사·결과 문서 | Claude |

**W5가 정해지기 전에는 새 기능을 만들지 않는다.** 예외는 사용자가 D9 등에서 고른 규칙에 구현이
필요할 때뿐이다(그때도 판정 전에). 판정량 가늠은 드라이런 수치로 한다 — N=90·K=50이면 판정 대상
388건이었다(`experiment/planning_evidence/w4_dryrun.json`).

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
  [`docs/archive/HANDOFF_2026-09-12.md`](docs/archive/HANDOFF_2026-09-12.md)).

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

`docs/archive/20-local-claude-handoff.md`는 과거 OBB 작업 기록이므로 **현재 실행 지시로
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

최근 기록: **2026-09-27 밤 노트북(CI와 같은 의존성)** backend **367** 통과·1 건너뜀 · experiment **541** 통과(프론트는 `types.ts` 선택 필드만 — 타입체크 미실행). 그 전 **2026-09-16 밤 데스크탑** backend **318** · experiment **500** 통과. 그 전 **저녁** backend **308** 통과(건너뜀 0) · experiment **459** 통과 ·
frontend **183** 통과 · typecheck·lint·build exit 0 · 보호 자료 해시 전부 일치.
노트북(CI와 같은 의존성만 깐 환경)에서는 backend의 외부 드라이브 검사 1건
(`test_uploads_dir_agreement.py:100`)이 건너뛰어진다.
실험 검사 중 가끔 `faulthandler`가 "Windows fatal exception: access violation"을 찍지만 검사는
통과한다 — 찍히는 자리가 실행마다 달라 처리된 네이티브 예외로 추정하고 조치하지 않았다
([`docs/testing-boundary.md`](docs/testing-boundary.md) 해당 절). **이 출력과 검사 실패가 같이
나오면** 그때 본다.

프론트 변경 시 `frontend`에서 관련 검사와 `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`를 실행한다. 백엔드 변경 시 해당 가상환경으로 `backend`의 pytest를 실행한다. 화면 통합 검사 도구가 없으면 기존 구성을 확인한 뒤 필요한 최소 구성을 추가한다. 실제 브라우저 확인과 자동 테스트 결과를 구분한다.

**가짜 진단 결과로 검사한 것을 실제 모델 추론 검증으로 표현하지 않는다.**
파일럿 후보에는 두 종류가 있고 섞어 읽으면 안 된다 — `injected_synthetic`(라벨에
오류를 주입한 것, 시간이 **하한**으로 나온다)과 `actual_diagnosis`(자를 돌려 나온
실제 후보). 코드가 `candidate_source`로 구분하고 하한이면 N 채택을 막는다.

**GPU는 진단 후보를 만들 때만 쓴다**(추론 1분 미만, 학습 없음). 그 외에는
필요 없다.

## 논문 연동 규칙

논문 초안은 `docs/paper/`의 네 파일이다 — `draft_ko.md`(초안), `claims_to_evidence.md`(수치↔결과 파일), `references.md`(출처·확인 상태), `open_items.md`(빈칸·결정·예상 지적).

- **언제:** 실험·판정·집계·재학습을 하거나, 결과 파일이 새로 생기거나 바뀌거나, 기존 수치가 정정되거나, 사전 등록·설계 결정이 바뀔 때. 코드 리팩터링·UI 수정처럼 결과와 무관한 작업에는 적용하지 않는다.
- **무엇을:** 논문에 쓸 만한 새 수치는 `claims_to_evidence.md`에 한 행 추가한다(결과 파일 경로, 파일에서 직접 읽은 값, 조건) — 문서에 적힌 값을 옮겨 적지 않는다. 초안의 해당 절이나 빈칸 `【…】`에 영향이 있으면 `draft_ko.md`를 최소 편집으로 고치고, 판단이 필요하면 고치지 말고 `open_items.md`에 "초안 반영 필요"로 적는다. 기존 수치가 정정되면 `draft_ko.md`와 `claims_to_evidence.md`의 같은 수치도 함께 고친다. 새로 드러난 한계·예상 지적은 `open_items.md` 6절에, 사용자 결정 항목(U1~U7)의 상태 변화는 3절에 적는다.
- **지킬 것:** Q-A 결과는 사전 등록 뒤 `experiment/analyze_qa.py` 산출에서만 초안에 넣는다 — 그 전에는 빈칸을 유지하고 예상이나 방향도 쓰지 않는다. 연습(practice) 자료의 수치는 "계획용"으로만 쓰고 결과처럼 쓰지 않는다. 새 출처는 원문으로 확인한 것만 `references.md`에 넣고 확인 상태를 적는다. 논문 파일 수정은 해당 작업 커밋에 함께 넣되 커밋 메시지에 `docs(paper)`를 붙여 구분한다.
- **지금 남은 논문 할 일:** `open_items.md` 7절.

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
