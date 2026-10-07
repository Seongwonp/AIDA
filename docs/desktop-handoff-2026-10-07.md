# 데스크탑 인수인계 — 본 판정 직전 (2026-10-07)

> 다음 작업은 **사람 본 판정(사용자 직접)**이다. 같은 평가 `qa1b`를 이어서 쓴다. 이 문서는 실행 방법만 적는다 — 추가 개발·val 접근·
> 분석은 판정이 끝날 때까지 하지 않는다. 이전 인계는 [desktop-handoff-2026-09-27.md](desktop-handoff-2026-09-27.md).

## 1. 지금 상태 (종료 시점 확인값)

| 항목 | 값 |
|---|---|
| 데이터셋 | `dcdd1be32bd3` (nuImages v1.0-val 300장, 기록 32개) |
| **판정할 평가** | **`qa1b`** — 묶음 표시 포함. 판정 0건(폴더에 `snapshot.json`만) |
| qa1 | 판정하지 않는다(묶음 표시 전 고정본, 보존용). 판정 0건 |
| qa1b candidate_set_hash | `f88c38f37387aa4d09482b7d74ea797922dd6494a800732e14ee8cddb278900f` |
| qa1b 내용 해시(표시 계획 제외) | `92148bb3cb36730fc5a30eea6fe6a670b8e6dc778f5443610287fa24b32a8b47` (= qa1) |
| qa1b `snapshot.json` 파일 SHA-256 | `d5ea2ae6b1ec73b34ace121cbb6a01d2fbb0fbbceb479a2185d5fbde50a0a952` |
| qa1 `snapshot.json` 파일 SHA-256 | `8c42d1f2da18679c680f497581c241a98ae6791aaf914ff6373c8aa14f45aad0` |
| 사전 등록 | `docs/qa-preregistration.md`, 마지막 개정 커밋 `802a240b`, git 저장 바이트 SHA-256 `acbc50cfcab7baebb2d03000c6f8f37748b53757450a1d2e3d431ca0adaef9f1` |
| 고정 판정 화면 코드 | `3ba87e999ccf90c7e1c6c67ca6290950a2bf17ca` (개정 5) |
| 자 | `car_v1_e100`, SHA-256 `fffecf52…110cc` |
| AI 보조 판정 | `disabled` (5-4절) — 외부 전송 없음 |
| 실행 기록 | [qa-run-record.md](qa-run-record.md), `experiment/planning_evidence/qa_main_v1_freeze_2026-10-07.json`, `qa1b_display_plan_freeze_2026-10-07.json` |

**하지 않는다:** 원본 파일 삭제·초기화·재생성, `qa1`·`qa1b` 다시 만들기, val 다시 표집, 묶음·N·K·씨앗 변경. 브라우저 점검은
`inspect_` 평가에서만 한다(본 평가 주소를 점검용으로 열지 않는다).

## 2. 시작 전 확인 (1분)

```powershell
git status --short          # 비어 있어야 한다
git pull --ff-only
dir backend\app\data\uploads\dcdd1be32bd3\evaluations\qa1b   # snapshot.json 하나만 있어야 한다(첫 판정 전)
```

## 3. 실행 명령

Claude 앱에서는 `.claude/launch.json`의 **backend**·**frontend**를 `preview_start`로 띄운다. 직접 띄울 때(AIDA 루트에서, 창 두 개):

```powershell
cd backend; .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

```powershell
cd frontend; npm run dev
```

## 4. 판정 주소

**http://localhost:5173/?evaluate=dcdd1be32bd3:qa1b**

## 5. 묶음 구성 (총 474건)

| 순서 | 묶음 | 건수 | 질문 |
|---|---|---|---|
| 1 | 기존 라벨 묶음 1/4 | 96 | 이 라벨은 수정이 필요한가? |
| 2 | 기존 라벨 묶음 2/4 | 96 | 〃 |
| 3 | 기존 라벨 묶음 3/4 | 96 | 〃 |
| 4 | 기존 라벨 묶음 4/4 | 96 | 〃 |
| 5 | 누락 묶음 | 90 | 이 객체의 라벨이 누락됐는가? |

- 버튼: **오류 있음(1) · 오류 없음(2) · 판단 보류(3)**. 누락 묶음에서 오류 있음이면 객체 번호(M1·새 객체)를 고른 뒤 넘어간다.
- 저장되면 같은 묶음의 다음 미판정 후보로 자동 이동. 묶음이 끝나면 **묶음 완료 화면**에서 쉬고 "다음 묶음 시작".
- **휴식:** 묶음 경계에서 쉰다(약 150건 휴식 규칙과 별개로 기록된다). 묶음 완료 화면에 오래 머문 시간은 최대 60초까지 그 묶음 마지막 후보에
  붙는다(사전 등록 5-3절 한계).
- **중간에 닫아도 된다.** 판정은 누르는 즉시 저장된다. 다시 열면 가장 앞의 미완료 묶음에서 첫 미판정 후보로 돌아간다.
- 저장 실패가 뜨면 그 후보에 머문다 — "다시 시도"를 누른다. 마지막 판정 뒤 완료 화면이 뜬 것을 확인하고 창을 닫는다.
- 망설여지면 **판단 보류**. 유리 반사는 판정 지침 패널의 공식 원문·번역·보류 원칙만 따른다.

## 6. 재판정 절차 (D8-3, 판정자 내 일관성)

- **본 판정을 모두 마치고 7일 이상 지난 뒤**, 같은 보조 표본 143건을 `adjudicator=primary_retest`로 다시 판정한다. 자기 이전 판정은 보이지 않는다.
- **주의 — 아직 화면 경로가 없다.** 백엔드는 `adjudicator=primary_retest`(큐·저장)를 지원하지만, 판정 화면은 주소의
  `?evaluate=`만 읽고 판정자를 고르는 경로가 없다(2026-10-07 확인). 재판정 전(본 판정 7일 뒤)에 화면이 `primary_retest`로 큐를 받고 저장하는
  경로를 추가해야 한다 — 본 판정 화면(primary)과 판정 대상·점수를 바꾸지 않는 추가이지만, 판정 화면 고정(5-3절)과의 관계를 사전 등록 개정으로
  먼저 기록한다. **본 판정에는 영향이 없다.**
- 재판정은 1차 분석에 쓰지 않는다. 두 번째 사람 판정자는 없다(판정자 간 일치도 보고 없음).

## 7. 판정이 끝난 뒤 (Claude에게 맡길 일)

1. `qa1b`의 판정 474건 완료 확인(원래·재표본 상위 N 미판정 0) — 미완료면 분석하지 않는다.
2. 사전 등록 6절 절차대로 `experiment/analyze_qa.py`로 집계(`--adjudicator primary`), 결과 문서·논문 빈칸 반영.
3. 7일 뒤 재판정 안내.
