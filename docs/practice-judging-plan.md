# 연습 판정 계획 — train fit_check (2026-09-27, val을 열지 않는다)

> 목적: **지침·입력·화면·프롬프트 점검.** 분석에 쓰지 않는다. 일치율 합격선을 두지 않는다. 연습 뒤 사용자가
> 판정 상한 C를 정한다. 연습 데이터는 train 쪽 `fit_check`(620장)이고 val이 아니다.

## 1. 준비 (데스크탑, `experiment/venv`)

```
& .\experiment\venv\Scripts\python.exe experiment/check_run_environment.py --out experiment/planning_evidence/env_2026-09-XX.json
```
자 `car_v1_e100`의 SHA-256·cleanlab·ultralytics·torch 버전을 실행 기록에 적는다. **이 노트북에는 가중치가
없어 sha256이 None이다** — 데스크탑 값을 쓴다.

## 2. 연습 묶음 만들기 (본 판정과 같은 경로, 값만 작게)

1. fit_check 폴더(images/·labels/·classes.txt·groups.json)를 zip으로 업로드.
2. `POST /api/datasets/{id}/diagnose-labels?ranking=aida_v2_candidate_iou&ruler=nuimages_car_v1_e100`
   — 응답의 `ruler.weights_sha256`이 1의 값과 같은지 본다.
3. 묶음:
```json
{"evaluation_id": "practice1", "judge_budget": 20, "ranking_version": "aida_v2_candidate_iou",
 "min_label_height_px": 30, "tie_seed": 1, "random_sample_size": 10, "random_sample_seed": 2,
 "coverage_iterations": 200, "coverage_seed": 3, "auxiliary_sample_fraction": 0.3, "auxiliary_sample_seed": 4}
```
   연습 씨앗은 본 판정 씨앗(20260927~30, 42)과 **다르게** 둔다.
4. `GET .../export?...`의 `judging`으로 원래 상위 N 합집합·K·재표본 추가 후보 수를 본다. 이 비율이 본 판정
   판정량 가늠의 첫 근거다(합성 시뮬레이션에서는 +22~30%였다).

## 3. 사람 연습 판정

- `queue`로 20~60건을 지침대로 판정한다(`hit`/`miss`/`hold`). 헷갈린 사례를 적어 지침·프롬프트에 반영한다.
- 작업 기록(`activity.jsonl`)의 후보당 시간으로 C의 근거를 만든다. **C는 사용자가 정한다.**

## 4. AI 입력 점검

```
GET .../queue?adjudicator=ai  → practice_ai_queue.json
python experiment/render_adjudication_images.py --queue practice_ai_queue.json --images <ds>/images --labels <ds>/labels --out practice_ai/
```
- 전체 장면(`full_file`)과 크롭(`file`) 두 그림에 점수·순위가 없는지, amodal 상자가 잘 보이는지, crop 여백이 충분한지 본다.
- 프롬프트 초안([`ai-adjudicator-prompt-draft.md`](ai-adjudicator-prompt-draft.md))으로 몇 건을 보내 **형식만** 점검한다
  (모델 식별자는 이때 정해 적는다). 일치율은 보되 합격선으로 쓰지 않는다.
- AI 판정 저장: `PUT .../adjudications?adjudicator=ai` (표본 밖은 거부된다).

## 5. 연습이 끝나면

- 지침·프롬프트 원문을 고정하고 확정본 초안에 붙인다.
- 판정 상한 C(건)를 정해 실행 계획에 적는다.
- **그 뒤에** 사전 등록 확정본 커밋 → val 표집. 연습 묶음·판정은 분석에 쓰지 않고 실행 기록에만 남긴다.

상세 환경 경계와 인수인계는 [데스크탑 실행 절차](desktop-handoff-2026-09-27.md)를 따른다.
