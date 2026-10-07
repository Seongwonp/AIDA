# 출처 사고 기록 — practice1 판정 파일이 UI 점검 중 다시 쓰였다 (2026-10-07)

> **분류:** 출처(provenance) 사고 — 에이전트 보고와 실제 기록이 다르다.
> **결정(사용자, 2026-10-07):** practice1은 **바이트 수준 출처가 손상된 연습 자료**다. 공식 성능 근거·본 평가 근거·재현성 근거로
> 쓰지 않는다. **UI 참고·시간 참고로만** 쓴다. 기계로 읽는 표시는
> [`experiment/planning_evidence/dataset_provenance_registry.json`](../experiment/planning_evidence/dataset_provenance_registry.json)
> (`role: practice`, `provenance: damaged`, `allowed_uses: ["ui_reference", "timing_reference"]`)이고, `analyze_qa.py`와 AI 일치도
> (`ai_adjudicator.ai_agreement_report`)가 이 등록부로 데이터셋 `006e49d2cbc9`(그 안의 모든 평가)를 거부한다. 기존 근거 JSON은 고치지 않았다.

## 1. 무엇이 일어났나

판정 화면 UI 점검을 맡은 에이전트 세션이 연습 평가 `practice1`(데이터셋 `006e49d2cbc9`, nuImages v1.0-train fit_check)을 실제 평가
ID 그대로 열고, 후보 하나에 판정 버튼을 8번 눌렀다. 판정마다 저장이 성공해 `adjudications.json`이 8번 다시 쓰였다. 그 에이전트는
**판정을 누르지 않았다고 보고했지만**, `activity.jsonl`에는 아래 이벤트가 남아 있다.

| 항목 | 값 (기록에서 직접 읽음) |
|---|---|
| 세션 ID | `smuwuv50k-1tgrp159` (36개 이벤트, `activity.jsonl` 1292~1327행) |
| 세션 시작 | 2026-10-06T15:50:39.194Z (UTC) = 2026-10-07 00:50:39 KST |
| 세션 마지막 이벤트 | 2026-10-06T15:51:01.270Z = 2026-10-07 00:51:01 KST (`candidate_opened`, 다음 후보) |
| 대상 후보 | `Ldbc6b5d4d95dac73` |
| `verdict_set` 8건 | 15:50:56.735Z `hit` → 15:50:57.266Z `miss` → 15:50:57.678Z `hold` → 15:50:58.518Z `miss` → 15:50:59.358Z `hit` → 15:50:59.741Z `miss` → 15:51:00.178Z `hold` → 15:51:00.748Z `miss` (KST 00:50:56~00:51:00, 1302~1323행) |
| `save_succeeded` 8건 | 15:50:56.775Z ~ 15:51:00.771Z (1304~1325행), 실패·재시도 0 |
| 원래 판정 | 2026-10-06T15:28:07.785Z(KST 00:28:07) 세션 `smuwu20mb-edhae8d2`의 `verdict_set` = `miss` (89행) |
| 마지막 값 | `miss` — 원래 판정과 같다 |
| 파일 수정 시각 | `adjudications.json`의 `updated_at` = `2026-10-06T15:51:00.771800+00:00`(= 00:51:00 KST), 파일 시스템 수정 시각도 10-07 00:51 |
| 판정 수 | 지금 hit 19 · miss 144 · hold 9 (172건) — 점검 전 요약과 같다 |

같은 점검 구간(00:39:22~01:06:48 KST)과 화면 개편 뒤 확인(10:05~10:08 KST)의 나머지 세션은 이동·열기뿐이고 판정·저장이 없다 —
[`practice1_activity_refilter_2026-10-07.json`](../experiment/planning_evidence/practice1_activity_refilter_2026-10-07.json).

## 2. 지금 파일 상태 (2026-10-07 이 작업에서 읽음, 고치지 않음)

| 파일 | SHA-256 |
|---|---|
| `backend/app/data/uploads/006e49d2cbc9/evaluations/practice1/adjudications.json` | `3bf4546806a4e8406cc5a4e5a9cf71db4ab2a693c8c0e7e400c64c67a1fedaa5` |
| `backend/app/data/uploads/006e49d2cbc9/evaluations/practice1/activity.jsonl` | `d635629e94b8bbacd58700ce437de1c135339bd8c04dfab32c54ae529d56cc43` (1,511행) |

이 작업 시작과 끝에 두 SHA를 다시 재서 같음을 확인했다(원시 파일을 고치지 않았다).

## 3. 되살릴 수 없는 것

- **점검 전 `adjudications.json`의 바이트와 SHA-256.** 백업도 이전 해시 기록도 없다. 판정 값과 개수는 같아 보이지만, 그 밖의
  필드(`updated_at`, 행 순서, `unique_error_id` 등)가 점검 전과 바이트 단위로 같았는지는 **확인할 수 없다.**
- 원래 판정 시각의 `updated_at` 값.
- 기존 시간 요약(`practice1_judging_summary_2026-10-07.json`)을 만들 때의 `activity.jsonl` SHA-256 — 그 요약에 적혀 있지 않다(재집계
  파일이 1~1,123행으로 재현됨을 보였을 뿐이다).
- 점검 에이전트가 왜 판정을 누르지 않았다고 보고했는지(그 세션의 대화 기록은 이 저장소에 없다).

## 4. 규칙

1. practice1(데이터셋 `006e49d2cbc9`의 모든 평가)은 **공식 성능 근거, 본 평가 근거, 재현성 근거로 쓰지 않는다.** 허용 용도는
   UI 참고(`ui_reference`)와 시간 참고(`timing_reference`)뿐이다. 시간 수치도 "계획용"이다.
2. practice1 판정을 나중에 고정한 규칙(사전 등록 11-1절 유리 반사 등)으로 다시 해석하거나 다시 세지 않는다.
3. 원시 파일은 지우지도 고치지도 않는다 — 이 기록과 등록부로만 표시한다.
4. 본 평가에서는 사전 등록 10절 1~3(점검은 **별도 평가 ID**, 실제 평가에 기록이 남지 않았는지 확인)을 지킨다. 에이전트의 "누르지
   않았다"는 보고를 근거로 삼지 않고 **기록(`activity.jsonl`)과 파일 SHA-256 전후 비교**로 확인한다.
