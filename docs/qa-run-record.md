# Q-A 실행 기록 — nuImages val, qa1 → qa1b (판정 전)

> **판정 0건.** 이 문서는 사전 등록([qa-preregistration.md](qa-preregistration.md)) 8절이 "묶음을 얼린 뒤 실행 기록에 채운다"고 한
> 칸과, 2절·5-3절·11절이 실행 기록에 남기라고 한 항목을 **이미 있는 증거 파일에서 옮겨 적은 것**이다. 새로 잰 값은 없다.
> 결과·집계가 아니다. 본 판정은 **`qa1b`**로 한다(사전 등록 개정 5). `qa1`은 판정하지 않는다.

## 1. 증거 파일

| 파일 | 내용 |
|---|---|
| [`experiment/planning_evidence/qa_main_v1_freeze_2026-10-07.json`](../experiment/planning_evidence/qa_main_v1_freeze_2026-10-07.json) | val 표집·압축 해제·변환·업로드·진단·**qa1** 묶음 얼리기, 8절 점검 17개, 보존본 |
| [`experiment/planning_evidence/qa1b_display_plan_freeze_2026-10-07.json`](../experiment/planning_evidence/qa1b_display_plan_freeze_2026-10-07.json) | **qa1b**(개정 5, 묶음 표시) 얼리기, qa1과의 내용 동일성 대조, 보호 파일 전후 SHA-256, 점검용 평가 `inspect_qa1b` 브라우저 확인 |

두 파일 모두 판정·작업 기록이 없는 상태에서 만들었다. qa1 얼림 기록은 이번 작업에서 고치지 않았다(SHA-256 전후 같음 — 아래 6절).

## 2. 실행 명세 (사전 등록 11절·5-3절)

| 항목 | 값 | 근거 |
|---|---|---|
| 사전 등록 커밋 (val 표집 시) | `2b220051546eef54ebe7595f48076da516764d7d` | qa1 얼림 기록 `preregistration.commit` |
| 자 `car_v1_e100` 가중치 SHA-256 | `fffecf529a6df1a87d5f10ec2f5613d55adaf69ec09fd48996ecd467584110cc` — 11절 값, 진단 응답과 같음 | qa1 얼림 기록 `ruler` |
| 판정 화면 코드 (qa1 얼림 시) | `bdb19432` 이후 frontend 변경 없음 | qa1 얼림 기록 `judging_screen_frontend` |
| 판정 화면 코드 (본 판정, 개정 5) | 사전 등록 5-3절 "고정 코드 커밋 (개정 5)" 칸의 커밋 | 개정 5 |
| 본 판정 평가 ID | **`qa1b`** — 판정 URL `?evaluate=dcdd1be32bd3:qa1b` | 개정 5 |
| AI 보조 판정 | `disabled` — 호출 0건, 외부 이미지 전송 0건 | 5-4절, 두 증거 파일 |
| 두 번째 사람 판정자 (D8-2) | **미실행** — 확보되지 않음(개정 4). 판정자 간 일치도 보고 없음 | 개정 4 |
| D8-3 주 판정자 재판정 | 보조 표본 143건, 본 판정 종료 7일 뒤 이후 `adjudicator=primary_retest` (판정자 내 일관성) | 5절 D8-3 |
| 판정 상한 C | 1,000 — 판정 목록 474 ≤ C | 11절, qa1 얼림 기록 `judging` |
| 환경 | experiment/venv: Python 3.14.0 · cleanlab 2.9.0 · ultralytics 8.4.90 · torch 2.12.1+cu126 · numpy 2.4.4. backend/venv: fastapi 0.139.0 · pydantic 2.13.4 | qa1 얼림 기록 `environment` |

## 3. 데이터 (사전 등록 2절)

| 항목 | 값 | 근거 |
|---|---|---|
| 표본 | 300장, 기록 32개, 기록당 최대 10장, 씨앗 20260927, 부족 0 | qa1 얼림 기록 `sampling.summary` |
| 소비한 val 기록 / 남은 기록 | 32 / 50 (val 기록 82개) — 토큰 목록은 `sample_summary.json`의 `consumed_log_tokens` | 같은 곳 |
| 제외 | 0장 — 2절 제외 대상은 전부 train/KITTI 소속, 소비한 val 기록과 train 기록의 교집합 0 | qa1 얼림 기록 `sampling.exclusions` |
| `sample_summary.json` SHA-256 | `15935629d0f1d8ab2b846193f773dc599767bfc33ffb2d0d763bc1ff13c79406` (이번 작업 전후 같음) | 두 증거 파일 |
| **이미지 이름 부록** | `AIDA-eval/nuimages/splits/eval_v1/sample_image_names.json` (새 파일, 읽기 전용). **300개**, 토큰·로그·카메라와 함께. SHA-256 `0b11779a975818af47d1f2f19c20dd1c1fdf5cc4afde3c3e7405ca3dbeb6e0ae`. 이름만의 SHA-256(정렬해 LF로 잇고 끝에 LF, UTF-8) `9838723dca13b13581746b65be14886320d17a2962bfea73303f777f4f1b8096`. 대조: `eval_tokens.txt` 토큰, qa1 얼림 기록의 `sampled_images`, 보존본 `images/`, `groups.json` 키와 모두 같음 | qa1b 기록 `image_name_appendix` |
| 보존본 | `AIDA-eval/nuimages/qa1_dcdd1be32bd3/` — 605개 파일, 목록 `SHA256SUMS.json`(SHA-256 `0ddda0c244dde77bb31f47c49dadcae1fe42c4131422a4968fa45c6db65fb88a`). 이번 작업 뒤 다시 대조해 불일치 0 | qa1 얼림 기록 `preservation_copy`, qa1b 기록 `preservation_copy` |

**2절과 다른 점.** 2절은 "이미지 이름 전부를 `sample_summary.json`에 남긴다"고 적었지만 `nuimages_eval_sample.py`는 토큰만 쓴다.
`sample_summary.json`은 고치지 않고 이름 부록을 위 새 파일로 남겼다. nuImages 파일 이름은 데이터셋 메타데이터라 이 저장소에는
이름 대신 SHA-256과 수만 적는다. (참고: qa1 얼림 기록에는 이미 이름 목록이 들어 있다 — 그 파일은 바꾸지 않았다.)

## 4. 8절 판정 전 점검

qa1 묶음에서 한 점검이다. qa1b는 같은 후보·같은 판정 대상·같은 씨앗이라(5절) 아래 값이 그대로 qa1b에도 해당하고, 묶음 지문과
판정 목록 필드만 다르다(마지막 두 줄).

| 점검 | 기대 | 관찰 | 통과 |
|---|---|---|---|
| `ruler.weights_sha256` = 11절 값 | 같다 | 같다 (`fffecf52…10cc`) | 예 |
| `all_candidates` 길이 = `total_in_queue` | 같다 | 360 = 360 | 예 |
| `all_labels` 길이 = 진단 요약의 `total_labels` | 같다 | 1075 = 1075 | 예 |
| `unmatched_predictions`·`objectlab` 항목 | 있다 | 미매칭 231, objectlab 있음(cleanlab 2.9.0 기본값) | 예 |
| 묶음이 얼려졌다(상자 중복 거부 없음) | 200 | qa1 200, qa1b 200 | 예 |
| 높이 30px 미만 제외 수 | 기록 | AIDA 후보 108 · 규칙 밖 라벨 165 제외, 범위 내 기존 라벨 802, K 풀 564. 누락 층 미적용 | 예 |
| 출처별 후보 수 | 기록 | `aida_candidate` 252 (기존 라벨 238 + 누락 14) · `label` 564 · `unmatched_prediction` 217 — 합 1,033 | 예 |
| 판정 대상 = 원래 상위 N 합집합 ∪ K ∪ 추가 후보 | 손으로 다시 센 수와 같다 | 상위 N 합집합 316 (기존 라벨 226 · 누락 90) · K 50 (합집합과 겹침 9) · 기준 풀 357 · 재표본 추가 117 → 474. 독립 재계산 = 백엔드 | 예 |
| `judging.total_judging_list` ≤ C | 넘으면 5-2절 | 474 ≤ 1,000 | 예 |
| IoU 0 라벨 수·상위 90 중 IoU 0·높이 층 | 기록 | 범위 내 IoU 0 라벨 60, `all_label_iou` 상위 90 중 60. 범위 내 높이 층 30-60: 357 · 60-120: 292 · 120+: 153. 세 방법 모두 90·91번째 점수가 달라 상위 90 구성은 동점 규칙에 좌우되지 않음 | 예 |
| 표본 K건이 `source=label`·규칙 밖·30px 이상 | 맞다 | 50건 전부, 씨앗 20260928로 다시 뽑아 같음 | 예 |
| 보조 표본 수(올림)·id 목록 | 기록 | ceil(0.3×474) = 143, 전부 판정 목록 안, 씨앗 20260930로 다시 뽑아 같음 | 예 |
| 판정 목록에 점수·순위·유형·출처·표본 여부·`coverage_extra`가 없다 | 없다 | qa1 필드 `box, canonical_candidate_id, class_name, image, label_index, unique_error_id, verdict`. **qa1b는 여기에 `bundle`(묶음 자리)만 더해진다** — 층과 위치로만 정해지며 계획을 섞인 순서·층만으로 다시 만들어 같음을 확인 | 예 |
| 섞인 순서가 씨앗대로 같은가 | 두 번 만들어 같다 | qa1: 메모리 2회 같음. qa1b: 섞인 순서가 qa1과 같고, 같은 입력으로 메모리에서 다시 만든 qa1b 지문이 저장본과 같음 | 예 |
| `bootstrap_coverage`(2000·42·입력 지문)가 묶음 지문에 있다 | 있다 | 있다 — 입력 지문 `27e1e5b0…12eb1`. qa1b의 `bootstrap_coverage`는 qa1과 같음 | 예 |
| cleanlab·ultralytics·torch 버전 | 기록 | 2절 표 "환경" | 예 |
| 합성 판정 → 내보내기 → 집계 → 부트스트랩 (메모리, 판정 파일 없음) | 통과 | qa1에서 통과(수치는 버림). qa1b는 후보·대상·coverage가 qa1과 같아 다시 하지 않았다 | 예 |

## 5. qa1 → qa1b (사전 등록 개정 5)

| 항목 | 값 |
|---|---|
| 이유 | qa1을 얼린 뒤 판정 화면에 D5(기존 라벨 층 묶음 나누기)·D6(누락 층 별도 묶음) 표시가 없었다(qa1 기록 `judging_plan.ui_gap`). 5-3절에 따라 화면이 바뀌면 새 평가 ID |
| 새 표집·추론·후보 선정·재표본 재실행 | 없음 — 같은 얼린 입력(진단 파일 `fabeb119…9b75`, 자 기록, `groups.json` `b7427aa6…770f6a`)을 읽어 묶음 코드가 결정론적으로 다시 계산 |
| 본문 | 3절 본문(`evaluation_id`만 `qa1b`) + `"display_plan": {"version": "layer_bundles_v1", "labelled_bundles": 4}` — qa1 본문에 계획만 더한 것과 같음(확인) |
| 묶음 | 기존 라벨 384 → 96 · 96 · 96 · 96, 누락 90 → 1묶음, 기존 라벨 묶음 넷 뒤. 층 안 순서는 qa1 가림 순서 그대로 |
| 지문 | qa1 `92148bb3cb36730fc5a30eea6fe6a670b8e6dc778f5443610287fa24b32a8b47` → qa1b `f88c38f37387aa4d09482b7d74ea797922dd6494a800732e14ee8cddb278900f`. 계획을 뺀 qa1b 내용 지문 `92148bb3…8b47` = qa1 |
| 직접 대조 | 후보 1,033개 전부(id·상자·점수·출처·순위·표본 표시·묶음) 같음 · 판정 대상 474 같음 · 재표본 추가 117 같음 · 보조 표본 143 같음 · 무작위 표본 50 같음 · 그 밖 얼린 설정(자·씨앗·예산·높이 필터·coverage 등) 같음 · 섞인 순서 같음 · 층별 상대 순서 같음 |
| qa1b 묶음 파일 SHA-256 | `d5ea2ae6b1ec73b34ace121cbb6a01d2fbb0fbbceb479a2185d5fbde50a0a952` |
| `snapshot.code_commit` | `58b6e4b2…` — 묶음을 만든 순간의 HEAD. 묶음 표시 코드는 그 순간 커밋 전 작업 트리였다. qa1b 기록 `code.git_blob_at_creation`의 blob 해시가 5-3절 고정 커밋의 같은 경로 blob과 같으면 그 커밋의 코드다 |
| 점검용 평가 | `inspect_qa1b`(같은 본문 + 계획)에서 브라우저 확인 — 머리글, 묶음 끝 멈춤·묶음 완료 화면, 다시 열기, 묶음 경계의 이전/다음, 앞 묶음 고치기, 누락 묶음 질문, 마지막 묶음 → 완료 화면. 판정은 점검용 평가에만 남았다 |

## 6. 판정 전 상태 (이번 작업 뒤)

| 대상 | 상태 |
|---|---|
| `qa1/snapshot.json` | SHA-256 `8c42d1f2da18679c680f497581c241a98ae6791aaf914ff6373c8aa14f45aad0` — 전후 같음. 폴더에 `snapshot.json`뿐(판정 파일·작업 기록 없음) |
| `qa1b/` | `snapshot.json`뿐(판정 파일·작업 기록 없음) |
| qa1 얼림 기록 | SHA-256 `cab1008baec3b949367347cab799da1c839f9d9ddbfc4d0b700ecb6f8b0889c4` — 전후 같음 |
| 진단 파일 | SHA-256 `fabeb119d1e89435adc2c6d822f0b07742d630ff34fe37c83da7b5b16f669b75` — 전후 같음 |
| 보존본 목록 `SHA256SUMS.json` | 전후 같음, 파일 605개 다시 대조해 불일치 0 |

## 7. 본 판정 중 문제 처리 원칙 (2026-10-07, 판정 시작 전)

- 본 판정 중 문제(화면 표시·저장 실패·이동 오류·후보 그림 이상 등)를 발견하면 **시각, 평가 ID, 증상, 영향받은 후보 id**를 이 문서에
  기록한다. 화면·코드를 그 자리에서 고치지 않는다.
- 판정이나 기록(판정 파일·작업 기록)의 신뢰성을 해칠 가능성이 있으면 **판정을 중단**한다.
- 화면이나 판정 로직을 바꿔야 하면 사전 등록 5-2절 4·5-3절의 규칙(개정 → 새 평가 ID로 다시 얼림)을 따른다. `qa1b`에 남은 판정은
  지우거나 고치지 않는다.

## 8. 남은 것 (판정 전)

- 사전 등록 10절 3·4: 본 판정 전에 점검 탭을 닫고 `qa1b`에 판정 파일·작업 기록이 없는지 다시 본다. 마지막 판정 뒤 기록 전송이 끝났는지 본다.
- 본 판정(사람 1인 전량) — `qa1b`. 묶음 경계에서 쉴 수 있다(묶음 표시 규칙). 5-2절의 약 150건 휴식 계획은 별개의 운영 규칙이다.
- 판정 뒤: `experiment/analyze_qa.py`로 집계 — 사전 등록 6절. 이 문서에 결과를 적지 않는다.
