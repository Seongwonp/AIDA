# AIDA 작업 안내

## 현재 상태 — 2026-09-12

> **`git pull` 직후 이것부터 읽는다.** 자세한 것은
> [`docs/HANDOFF_2026-09-12.md`](docs/HANDOFF_2026-09-12.md).

**시간 파일럿 다섯 번(timing1~5)을 끝내 `s_plan`이 나왔다. 그런데 남은 것은
`D`·`T`를 정하는 일만이 아니다** — `s_plan`으로 나오는 것은 *처리 가능량*
(`N_capacity`)이고, 최종 검수량(`N_final`)을 정하려면 *필요량*
(`N_required`)이 있어야 하는데 그 입력이 하나도 없다.

| | |
|---|---|
| 계획값 | `s_plan = 5.02초` (timing5, 120건 연속 판정) |
| 계산되는 것 | `N_capacity` — 시간 예산으로 **처리 가능한** 후보 수 |
| **미정** | **`D` · `T` · `N_required` · `N_final` · `Δ`** |

> **`N_capacity`를 최종 표본 크기로 읽지 않는다.** 표가 답하는 질문은 "시간
> 안에 몇 개를 볼 수 있는가"이고, 평가에 필요한 것은 "결론을 내려면 몇 개를
> 봐야 하는가"다. 둘의 차이는
> [`docs/capacity-vs-sample-size.md`](docs/capacity-vs-sample-size.md)에
> 비전공자용으로 적어 두었다. **시간이 남는다는 것은 N을 정할 근거가 아니다.**

### 노트북에서 이어받을 때 — **먼저 알아야 할 것**

**`backend/app/data/uploads/`는 `.gitignore` 대상이라 `git pull`로 안 따라온다.**
파일럿 기록(timing1~5)과 사용자 데이터셋 5개가 전부 거기 있다.

| 하려는 것 | 되는가 |
|---|---|
| 문서 읽기, 코드 수정, 검사 실행 | **된다** |
| timing5 기록으로 N 계산 | **안 된다** — 데스크탑에서 하거나 폴더를 옮겨야 한다 |
| 새 파일럿 만들기 | 개발 데이터(`experiment/data/`)와 가중치(`experiment/runs/`)도 gitignore라 **안 된다** |

즉 **노트북에서는 문서·코드 작업만** 하고, 파일럿 실행과 N 계산은 데스크탑에서
한다.

### 지금 할 일

1. 사용자에게 **`D`(최종 평가 데이터셋 수)와 `T`(전체 활동 시간 상한, 분)** 를
   받는다.
2. 데스크탑에서 아래를 돌린다. **`3`과 `180` 자리에 받은 숫자를 넣는다** —
   PowerShell에서 `<D>` 같은 꺾쇠를 그대로 두면 파서 오류가 난다.

```
./experiment/venv/Scripts/python.exe experiment/timing_report.py --dataset ffffffffff07 --evaluation timing5 --sustained --sustained-block 120 --datasets 3 --total-minutes 180 --reviewed
```

3. **`--reviewed`는 확인 버튼이 아니다.** 구간별 속도와 anchor 결과를 사람이
   보고 받아들였다는 표시다.
4. 나오는 것은 `N_capacity`다. **`N_final`이 아니다.** `N_required`를 정하려면
   Δ·주지표·검정력·군집 구조·paired bootstrap 시뮬레이션이 필요한데 **하나도
   없다**(docs/capacity-vs-sample-size.md의 체크리스트).
5. 지금 고를 수 있는 것은 세 가지뿐이다 — **A** 가장 작은 비외삽 운영안
   (데이터셋당 120건), **B** 반복 지속 블록을 더 재고 결정, **C** Δ와 검정력
   시뮬레이션을 먼저 정해 `N_required` 계산. **사용자 승인 없이 `N_final`로
   확정하지 않는다.**

시간 예산별 처리 용량 예시만 보려면 `--capacity-table`을 붙인다. `D`·`T` 없이
돌아간다.

### 넘지 말아야 할 선

- **관측한 지속 한계는 120건 1회다.** 1000건을 이어서 할 수 있다는 근거가
  아니고, **반복 블록 간 분산도 관측하지 않았다.** 전체 10블록 이상을 가정하는
  조합은 `strongly_extrapolated`로 찍히고 보고서가 채택을 막는다.
- **`T`는 활동 판정 시간이지 일정이 아니다.** 휴식·탭 전환·저장 대기·데이터셋
  교체는 `s_plan`에 없다. wall-clock 완료 시각을 표로 보장하지 않는다.
- **실제 후보에는 정답이 없다.** accuracy를 계산하지 않는다.
- anchor는 **주의력 가드레일**이지 AIDA의 효능이 아니다.
- **품질 허용 기준은 사전 등록돼 있지 않다.** 결과를 보고 만들지 않는다.
- 판정자가 한 명이고 다섯 번째다. **외부 사용자 속도로 일반화하지 않는다.**
- `s_plan`은 **보수적 참고값**이지 확률 보장이 아니다.

### 파일럿 원본을 지우거나 고치지 않는다

`uploads/ffffffffff01`~`07`의 snapshot·adjudications·activity·metadata·
answer key. 44개 파일의 SHA-256이 인계 문서에 있다.

## 먼저 읽을 문서

1. [`docs/HANDOFF_2026-09-12.md`](docs/HANDOFF_2026-09-12.md) — **현재 상태와 다음 작업**
2. [`docs/capacity-vs-sample-size.md`](docs/capacity-vs-sample-size.md) — **처리 용량과 표본 크기의 차이, A·B·C 선택지**
3. `docs/sustained-pilot-protocol.md` — timing5 규약과 결과, `s_plan`의 근거 한계
3. `docs/pilot-evaluation-plan.md` — 계측 계약, N·Δ 결정 절차
4. `docs/testing-boundary.md` — 검사 경계와 미검증 항목
5. `docs/21-next-plan.md` — BC~BN 절에 최근 경위
6. `docs/25-advancement-roadmap.md` — 단계별 상태

`docs/20-local-claude-handoff.md`는 과거 OBB 작업 기록이므로 **현재 실행 지시로
쓰지 않는다.** R1~R6(docs/25 1단계)은 **전부 끝났다** — 그 절을 지금 할 일로
읽지 않는다.

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

데스크탑 기준 최근 통과 수는 experiment 288 · backend 252 · frontend 176이다.

프론트 변경 시 `frontend`에서 관련 검사와 `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`를 실행한다. 백엔드 변경 시 해당 가상환경으로 `backend`의 pytest를 실행한다. 화면 통합 검사 도구가 없으면 기존 구성을 확인한 뒤 필요한 최소 구성을 추가한다. 실제 브라우저 확인과 자동 테스트 결과를 구분한다.

**가짜 진단 결과로 검사한 것을 실제 모델 추론 검증으로 표현하지 않는다.**
파일럿 후보에는 두 종류가 있고 섞어 읽으면 안 된다 — `injected_synthetic`(라벨에
오류를 주입한 것, 시간이 **하한**으로 나온다)과 `actual_diagnosis`(자를 돌려 나온
실제 후보). 코드가 `candidate_source`로 구분하고 하한이면 N 채택을 막는다.

**GPU는 파일럿 후보를 만들 때만 쓴다**(추론 1분 미만, 학습 없음). 그 외에는
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
