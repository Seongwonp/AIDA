# AIDA 작업 안내

## 현재 상태 — 2026-09-13

> **`git pull` 직후 이것부터 읽는다.** 경위는
> [`docs/HANDOFF_2026-09-13.md`](docs/HANDOFF_2026-09-13.md) 12절.

**다음 산출물은 하나다 — AIDA와 단순 기준선(`1 − label_iou`)의 추천을 같은
기준으로 가림 판정한 작은 예비 비교 결과.** 도구를 더 만들지 않는다.
시간·표본 크기(`N_capacity`·`N_required`) 작업은 멈춰 두었다 — 순위 품질과
오류 비율 가정에 근거가 없어서이고, 이 예비 비교가 그 근거가 된다.

2026-09-13 노트북에서 비교를 막던 것을 고쳤다 (`8fbb09b`, **가짜 진단 결과로만
검사**).

- 평가가 AIDA를 **심각도**로 줄 세우던 것을 **제품 순위(`rank`)**로 바꿨다.
  재현 예제에서는 AIDA가 불리하게 세어졌지만, **실제 데이터에서 어느 쪽으로
  휘었는지는 모른다.**
- 진단이 잘리기 전 후보 전부(`all_candidates`)를 쓰고, 평가가 그것을 얼린다.
- 평가 시작 때 `judge_budget=N`을 주면 두 방법 상위 N건의 합집합만 판정한다.

### 데스크탑에서 할 일 — 이 순서로

> **진행 상태 (2026-09-13 밤).** 1~5번이 끝났다. 예비 데이터셋 **`30512dfcbfbb`**,
> 평가 **`prelim1`**(후보 331 전부 동결, 판정 186, `candidate_set_hash` `e996e262…`)을
> 만들고 [`docs/prelim1-preregistration.md`](docs/prelim1-preregistration.md)를 판정 전에
> 커밋했다. 정확한 파일은 `D:/AIDA-eval/prelim/prelim1_30512dfcbfbb/`, 해시는
> `experiment/planning_evidence/prelim1_manifest.json`. **판정 186건은 2026-09-14에 끝났고 집계는 [`docs/prelim1-results.md`](docs/prelim1-results.md)에 있다.**
> 화면 점검은 별도 평가 `inspect_ui1`로 했고(판정하지 않는다) prelim1에는 `snapshot.json`만
> 있다 — 사전 등록 문서 11절.
> 판정 주소: `http://localhost:5173/?evaluate=30512dfcbfbb:prelim1`
>
> **결과 요약 (탐색, 판정자 1인).** 기존 라벨 층 검수량 90에서 AIDA 제품 순위 4건 대 단순 기준선
> 14건, 차이 −10, 95% 구간 [−18, −2]. 이 조건에서는 기준선 순서가 판정자가 오류로 본 라벨을 더 많이
> 올렸다. Δ가 없어 성공·실패 판정은 아니다. 심각도 순서 같은 사전 등록에 없는 분석은 이 데이터로
> 하지 않는다 — 하려면 새 자료로 따로 사전 등록한다.
>
> **감사 (2026-09-14).** N=90이 유일한 1차 탐색 비교다(10~80은 사후 깊이 진단). 독립
> 산술 감사가 제품 집계와 같았다(hit 후보 = 고유 오류, 4 대 14). 판정 186 대 기록 185는
> 마지막 후보의 기록 전송 누락이었고, 세션 판정 결함을 고쳤다(`5cf0e998`) — prelim1
> 시간은 `N_capacity`에 쓰지 않는다. 사후 분석: 상대 문턱으로 승격된 width가 AIDA 상위
> 90을 전부 차지했다(가설일 뿐). prelim1은 **소비된 개발 데이터**다 —
> [`docs/prelim1-decision.md`](docs/prelim1-decision.md)·
> [`docs/prelim1-failure-analysis.md`](docs/prelim1-failure-analysis.md)·
> [`docs/evaluation-data.md`](docs/evaluation-data.md) 원장.
>
> **순위 분리 (2026-09-14, 사용자 결정 C안 + 임시 A안).** 데이터셋 진단과 후보 재검수 순위를
> 나눴다 — [`docs/adr-ranking-separation.md`](docs/adr-ranking-separation.md). 순위 버전
> `aida_v1_systematic_boost`(기본, 지금까지의 제품 순위)와 `aida_v2_candidate_iou`(시험, 기존 라벨
> `1 − label_iou`·누락 심각도, 층 분리)가 있다. 진단 파일은 버전별이고, 새 평가 묶음은 버전을
> 얼린다. **prelim1은 v1에 묶여 있고 지문이 그대로다.** v2는 **평가되지 않았다** — prelim1로
> 검증하지 않는다. 다음 평가는 제안만 있다:
> [`docs/next-evaluation-proposal.md`](docs/next-evaluation-proposal.md) (데이터셋·N 미정, 법률 검토 필요).

1. ~~**검사 공백부터.**~~ **끝 (2026-09-13 데스크탑).** frontend 176 passed ·
   typecheck·lint·build exit 0, backend 261 passed(건너뜀 0), experiment 408 passed,
   CI는 `8fbb09b` 이후 전부 success.
   [`docs/prelim-comparison-proposal.md`](docs/prelim-comparison-proposal.md) 1절.
2. **예비 데이터를 고른다 — 사용자 결정.** 제안: KITTI val 적격 413장 중 씨앗
   20260914로 뽑은 300장(제안 문서 4절). 최종 평가에 쓸 데이터와 **겹치지
   않아야 한다**([`docs/evaluation-data.md`](docs/evaluation-data.md)). 여기서 쓴
   데이터는 개발 데이터가 되어 최종 평가에 재사용하지 않는다. **파일럿 데이터셋
   `ffffffffff01`~`07`은 쓰지 않는다** — 다시 진단하면 그 `label_diagnosis.json`을
   덮어쓴다.
3. **실제 추론으로 확인한다.** 파일 점검 네 가지는 제안 표본을 `--dataset-dir`로
   돌려 **통과**했다(제안 문서 2절). **업로드 데이터셋과 화면에서는 아직 안 했다.** 고른 데이터셋을 화면에서 박스 단위로 다시
   진단한다. 그 뒤 `uploads/` 아래 그 데이터셋의 `label_diagnosis.json`에서
   - `all_candidates` 길이가 `total_in_queue`와 같은가
   - `all_candidates` 앞부분이 `review_queue`와 같은 후보·같은 `rank`인가
   - 재검수 화면 맨 위 몇 건이 `rank` 1, 2, 3과 같은 후보인가

   **하나라도 어긋나면 멈추고** 원인을 본다.
4. **N과 섞는 씨앗을 판정 전에 정한다 — 사용자 결정.** 판정 대상은 **두 방법**
   (기존 라벨 층 AIDA·기준선 합집합, 누락 층 AIDA만). 제안: N=90(186건, 두 번에
   나눠), `shuffle_seed` 20260915 — 제안 문서 3·5·6절. 판정할 양은 기존 라벨
   층에서 최대 2N건, 누락 층에서 최대 N건이다. timing5의 `s_plan` 5.02초로 치면
   N=60이 최대 180건, 약 15분이다(판정자 1인의 참고값). 정한 값은 **판정 전에**
   커밋한다.
5. **묶음을 고정한다.** 서버를 띄우고 http://localhost:8000/docs 에서
   `POST /api/datasets/{dataset_id}/evaluations`에 `evaluation_id`(예: `prelim1`),
   `shuffle_seed`, `judge_budget`을 보낸다. 판정 화면에는 이 값을 넣는 곳이 없다.
6. **가림을 확인하고 판정한다.** 브라우저에서
   `http://localhost:5173/?evaluate=데이터셋ID:prelim1`을 연다. 순위·점수·의심
   유형·추천 출처·진단 문구가 **안 보이는지**, 순서가 섞였는지 먼저 본다(누락
   검수인지 기존 라벨 검수인지는 원래 못 가린다). 판정 기준은
   [`docs/manual-timing-pilot.md`](docs/manual-timing-pilot.md).
7. **보고한다.** `GET .../evaluations/prelim1/export?methods=aida,iou_baseline`을
   `experiment/evaluation`(`importer.load_export` → `summary.summarise`)으로 N 이하
   예산에서 방법별로 집계한다. 방법별 고유 오류 수, 차이, 보류율, 판정 수를 적고
   누락 층은 따로 기술 통계로 적는다. **"개발자 1인의 탐색적 비교"로 명시한다** —
   판정자 간 불일치 조정 절차가 없다. 이 집계를 한 번에 돌리는 스크립트가 있는지는
   확인하지 않았다.

### 넘지 말아야 할 선

- 예비 비교 결과를 보고 **N·Δ·성공 기준을 사후에 정하지 않는다.** 가정의
  근거로만 쓴다.
- 예비 데이터를 **최종 평가에 재사용하지 않는다.**
- 주 비교는 **AIDA 후보 안의 재정렬 효과**다. 후보 생성까지 포함한 전체 제품
  효과로 부르지 않는다.
- **실제 후보에는 정답이 없다.** 판정을 정답으로 부르거나 accuracy를 계산하지
  않는다.
- 한 사람의 판정은 **일관성**을 보여줄 뿐 정확성이 아니다. 외부 사용자로
  일반화하지 않는다.
- **파일럿 원본을 지우거나 고치지 않는다** — `uploads/ffffffffff01`~`07`의
  snapshot·adjudications·activity·metadata·answer key. SHA-256은
  [`docs/HANDOFF_2026-09-12.md`](docs/HANDOFF_2026-09-12.md)에 있다.

### 멈춰 둔 것 — 시간·표본 크기

`s_plan = 5.02초`(timing5, 120건 연속 판정 1회)로 `N_capacity`는 계산되지만,
`N_required`는 Δ·목표 검정력·순위 품질 근거가 없어 민감도 표뿐이다. `D`·`T`·Δ·
`N_final`은 **하나도 정하지 않았다.** `N_capacity`를 최종 표본 크기로 읽지 않는다.
이어갈 때는 [`docs/capacity-vs-sample-size.md`](docs/capacity-vs-sample-size.md) →
[`docs/n-required-plan.md`](docs/n-required-plan.md) → 09-12·09-13 인계 문서 순서로
읽는다.

### 노트북과 데스크탑

`backend/app/data/uploads/`, `experiment/data/`, `experiment/runs/`는 gitignore라
`git pull`로 안 따라온다. **노트북에서는 문서·코드·검사만** 하고, 추론·판정·
파일럿은 데스크탑에서 한다.

## 먼저 읽을 문서

1. [`docs/HANDOFF_2026-09-13.md`](docs/HANDOFF_2026-09-13.md) 12절 — 최신 경위
2. [`docs/evaluation-adjudication-design.md`](docs/evaluation-adjudication-design.md) — 가림 판정, AIDA 순서, 모집단, 상위 N 합집합, 판정자 간 불일치(미설계)
3. [`docs/25-advancement-roadmap.md`](docs/25-advancement-roadmap.md) — 맨 아래 "첫 실행 순서"와 목표 산출물
4. [`docs/evaluation-protocol.md`](docs/evaluation-protocol.md) — 평가 규약(동점·보류·층)
5. [`docs/testing-boundary.md`](docs/testing-boundary.md) — 검사 경계와 미검증 항목
6. [`docs/current-evidence.md`](docs/current-evidence.md) — 수치를 인용하기 전에

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

최근 통과 수는 experiment 440 · backend 279(데스크탑 건너뜀 0) · frontend 183이다 (2026-09-14 데스크탑, 순위 버전 추가 뒤).
experiment·backend는 2026-09-13 노트북에서 CI와 같은 의존성 목록만 깐 가상환경으로
직접 돌린 결과다(backend의 건너뜀 1건은 `test_uploads_dir_agreement.py:100`
"외부 드라이브가 없는 환경"이다 — 노트북에만 해당하고, 데스크탑 기록은 252 통과였다).
frontend 176은 이전 데스크탑 기록이고, 이번 `api.ts` 변경 뒤에는 노트북에
`node_modules`가 없어 **안 돌렸다.**

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

`docs/25-advancement-roadmap.md`의 해당 작업 상태와 완료 근거를 갱신하고, 저장 규약·테스트 경계가 바뀌면 관련 문서도 맞춘다. 계획 전체를 완료 처리하지 않는다.

최종 보고에는 다음만 간결하게 남긴다:

1. 재현된 문제와 수정한 동작
2. 실행한 검사와 통과·실패·미실행 범위
3. 커밋 ID와 푸시 결과
4. 남은 위험과 다음 작업 ID

사용자가 다음 검토에서 이 기록만으로 구현 결과와 근거를 확인할 수 있어야 한다.
