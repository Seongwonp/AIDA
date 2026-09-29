# Q-A 사전 등록 — 확정본 (후보 생성 포함 비교, nuImages val)

> **상태 (2026-09-28): D1~D9 확정.** 값은 [qa-preregistration-proposal-2026-09-27.md](qa-preregistration-proposal-2026-09-27.md)의
> 제안값을 **그대로** 받아들였다(사용자 결정). 형식은 [qa-preregistration-draft.md](qa-preregistration-draft.md)와
> [prelim1-preregistration.md](prelim1-preregistration.md)를 따른다.
>
> **아직 커밋하지 않는다.** 11절 "실행 명세"의 네 칸(자 SHA-256, AI 판정자 식별자, 프롬프트 원문, 판정 상한 C)은
> 연습 판정 뒤에 채운다. **네 칸이 다 채워진 뒤 커밋·푸시하고, 그 커밋이 있어야 `nuimages_eval_sample.py`가
> val을 연다.** 빈칸이 남은 채로 val을 열거나 판정 화면을 열지 않는다.
>
> 이 문서를 커밋한 뒤에는 **판정을 본 뒤 N·K·방법·씨앗·판정 규칙·1차 지표·구간 방법을 바꾸지 않는다**(7절).
> 바꿔야 하면 판정 전에 개정하고 새 평가 ID로 다시 얼린다(5-2절).

## 0. 결정 요약

| # | 결정 | 값 |
|---|---|---|
| D1 | 데이터셋·경계 | nuImages **v1.0-val**, Car. 소비한 기록(log) 목록을 `sample_summary.json`의 `consumed_log_tokens`로 남기고, 남은 기록은 최종 몫 |
| D2 | 클래스·범위 | `vehicle.car` → Car 하나. **원본 픽셀 높이 30px 미만 기존 라벨은 1차 비교 범위 밖**(`min_label_height_px=30`). 누락 층에는 걸지 않는다 |
| D3 | 표본 | **300장**, 기록마다 최대 **`per_log=10`**, 표집 씨앗 **20260927**. 묶음 = 주행 기록(`groups.json`) |
| D4 | AIDA 순위 버전 | **`aida_v2_candidate_iou`** |
| D5 | 예산·표본·씨앗 | **N=90, K=50**, `shuffle_seed=20260927`, `random_sample_seed=20260928`. 세 묶음(약 130건씩), 400건을 넘으면 넷 |
| D6 | 누락 층 | 같은 세션, **별도 묶음** |
| D7 | 1차 지표·구간 | N=90에서 고유 오류 수 차이 `all_label_iou − aida`. 방향 예측 없음. 기록 묶음 짝지은 부트스트랩 **씨앗 42·2000회**, 표본 층 Wilson. **Δ 없음** |
| D8 | 판정자 | **사람 1인(개발자) 전량 판정이 1차 분석.** 판정 대상 확정 뒤 **30% 단순 무작위**(씨앗 20260930, 올림) 보조 표본 하나를 뽑고, 그 **같은 표본**을 AI 보조 판정자·**두 번째 사람 판정자**(D8-2)·**주 판정자 재판정**(D8-3)이 각각 독립 판정. 일치도는 보고만 (개정 2026-09-29) |
| D9 | 동점·IoU 0 | **(가)** 높이 30px 이상 범위에서 **IoU 0 라벨 포함**, 동점은 **고정 씨앗 무작위**(`tie_seed=20260929`, `sha256(tie_seed:후보 id)`). 두 방법에 똑같이 적용 |
| 부트스트랩 판정 범위 | **안 (a)** | 고정 재표본 합집합 전량 판정. `coverage_iterations=2000`, `coverage_seed=42`. 최종 분석 `require_judged_top_n=True` |

## 1. 목적

| | |
|---|---|
| **1차 (Q-A)** | AIDA 규칙이 만든 후보를 v2 순서로 본 것 대 **모든 기존 라벨**을 `1 − label_iou`로 본 것 — 같은 검수량 N=90에서 판정자가 오류로 본 고유 라벨 수 |
| **기준선 추가** | cleanlab 박스 단위 badloc·swap 점수를 라벨마다 min으로 합친 **이 연구의 적응**(`all_label_objectlab`). ObjectLab 공식 산출물(이미지 단위 점수)이 아니며, Car 단일 클래스에서는 사실상 `1 − badloc`이다 |
| **보조 (Q-C)** | AIDA 누락 후보 대 필터 전 미매칭 예측 전부(확신도순) 대 ObjectLab overlooked — **기술 통계만** |
| **표본 층** | AIDA 규칙 밖 기존 라벨의 무작위 표본 K=50에서 판정 오류 비율 — 규칙이 놓친 비율의 추정 |

**이 비교가 재는 것.** D4가 v2이므로 기존 라벨 층에서 AIDA 순서는 곧 `1 − label_iou`다. 두 방법의 차이는
"AIDA 규칙으로 거른 뒤 IoU 순" 대 "거르지 않고 IoU 순"뿐이다 — 즉 **후보 생성(규칙 필터)의 효과**이지 순위
알고리즘의 검증이 아니다. 논문에서도 그렇게 부른다.

**탐색적 한계.** 판정자가 개발자 1인이므로 사전 등록된 비교이되 **성공·실패를 주장하지 않는다.** 구간이 0을
포함해도 "차이 없음"으로 단정하지 않고, 포함하지 않아도 이 판정자·이 데이터·이 자 범위의 차이로만 해석한다.

## 2. 데이터 — D1·D2·D3

| 항목 | 값 | 비고 |
|---|---|---|
| 데이터셋 | nuImages **v1.0-val**, 카메라 6방향 전부 | W1 결정([evaluation-data.md](evaluation-data.md) "사용자 결정 — W1") |
| 라이선스 확인 기록 | nuScenes Terms of Use — CC BY-NC-SA 4.0, 비상업 연구·포트폴리오 용도. 원본 이미지·라벨 재배포 금지, 자 가중치 비공개 | [evaluation-data.md](evaluation-data.md) "포트폴리오로 공개할 때 지킬 것". 법적 판단 아님 |
| 개발/최종 경계 | 이번 표본이 **소비한 val 기록 목록**을 `sample_summary.json`의 `consumed_log_tokens`로 남긴다. `unconsumed_logs`는 최종 몫. 다음 평가는 소비한 기록을 다시 쓰지 않는다 | `nuimages_eval_sample.py` |
| 클래스 범위 | `vehicle.car` → **Car 하나**. nuImages 정의대로 밴·SUV 포함 | [nuimages-data-plan.md](nuimages-data-plan.md) 3절 |
| 높이 범위 (D2) | **원본 픽셀 높이 30px 미만 기존 라벨은 1차 비교 범위 밖.** 묶음을 얼릴 때 AIDA 후보·`all_label_iou`·`all_label_objectlab` 모집단·무작위 표본 K에 같은 범위를 걸고 제외 수를 기록한다. 진단·원본 라벨은 손대지 않는다. **누락 층(예측)에는 걸지 않는다** | fit_check에서 30px 미만의 절반을 자가 못 본다(같은 문서 5절). **결과는 30px 이상 차량에 대한 것이다** — 논문 한계 절 |
| 표본 이미지 수·표집 | **300장**, 기록마다 최대 **10장**, 씨앗 **20260927** | 이미지 이름 전부를 `sample_summary.json`에 남긴다 |
| 연속 프레임 묶음 | 주행 기록(`groups.json`) | `nuimages_to_yolo.py`가 쓴다. 부트스트랩·coverage의 재표집 단위 |
| 제외 | 소비된 개발 데이터 전부 — prelim1 300장, 파일럿, fit_check·ruler_val·ruler_train(전부 train 소속) | [evaluation-data.md](evaluation-data.md) 원장 |
| 자 | **`car_v1_e100`**(best=93에폭). fit_check 짚은 비율 71.6%, ruler_val fitness 0.516. 진단 시 `?ruler=nuimages_car_v1_e100` | 가중치 SHA-256은 11절 |

**자는 평가 데이터와 같은 데이터셋(nuImages train)으로 학습했다 — AIDA에게 가장 좋은 조건이다.** 결과를
"고객 데이터에서도 그렇다"로 옮기지 않는다(7절).

**보존.** 판정에 쓰는 정확한 파일(이미지·라벨·`classes.txt`·`groups.json`·`ruler.*.json`·진단·`snapshot.json`)을
`D:/AIDA-eval/nuimages/qa1_<dataset_id>/`에 읽기 전용으로 복사하고 파일마다 SHA-256을 실행 기록에 남긴다.

## 3. 제품 경로 — D4

| 단계 | 경로 |
|---|---|
| 표집 | `nuimages_eval_sample.py --version v1.0-val --images 300 --per-log 10 --seed 20260927 --preregistration docs/qa-preregistration.md` (커밋이 없으면 열리지 않는다) |
| 업로드 | `POST /api/datasets/upload` |
| 진단 | `POST /api/datasets/{id}/diagnose-labels?ranking=aida_v2_candidate_iou&ruler=nuimages_car_v1_e100` — `experiment/venv`(cleanlab 설치). 응답의 `ruler.weights_sha256`이 11절 값과 같아야 한다. 결과에 `all_labels`·`unmatched_predictions`·`objectlab`이 있어야 한다 |
| 묶음 | `POST .../evaluations` — 아래 본문 |

```json
{"evaluation_id": "qa1",
 "ranking_version": "aida_v2_candidate_iou",
 "judge_budget": 90,
 "shuffle_seed": 20260927,
 "random_sample_size": 50,
 "random_sample_seed": 20260928,
 "min_label_height_px": 30,
 "tie_seed": 20260929,
 "coverage_iterations": 2000,
 "coverage_seed": 42,
 "auxiliary_sample_fraction": 0.3,
 "auxiliary_sample_seed": 20260930}
```

**D4 — `aida_v2_candidate_iou`.** v1은 prelim1에서 졌고, 지면 생성인지 순서인지 갈리지 않는다. v2는
평가되지 않은 시험 버전이며 이 비교는 v2의 순서를 검증하지 않는다(1절).

## 4. 방법 — 고정

| 층 | 방법 | 모집단 | 평가 순서 | 상태 |
|---|---|---|---|---|
| 기존 라벨 (1차) | `aida` | AIDA 후보 (v2) | 점수 `1 − label_iou` + 공통 `tie_key` (`order_basis=score_1_minus_label_iou`) | 1차 |
| 기존 라벨 (1차) | `all_label_iou` | 모든 기존 라벨 (30px 이상) | `1 − label_iou` + 공통 `tie_key` | 1차 |
| 기존 라벨 (1차) | `all_label_objectlab` | ObjectLab이 점수를 낸 기존 라벨 (30px 이상) | `1 − min(badloc, swap)` + 공통 `tie_key`, cleanlab 기본값 | 1차 표에 함께. **1차 지표는 `all_label_iou − aida` 하나**이고 ObjectLab 대비 차이는 같은 방법으로 낸 **보조 비교** |
| 누락 (보조) | `aida` | AIDA 누락 후보 | 제품 순위(심각도) | `descriptive_only` |
| 누락 (보조) | `unmatched_confidence` | 필터 전 미매칭 예측 전부 | 확신도 | `descriptive_only` |
| 누락 (보조) | `unmatched_objectlab` | overlooked 점수가 있는 미매칭 예측 | `1 − overlooked` | `descriptive_only` |

**`unmatched_objectlab` — 사용자 결정 (a), 2026-09-29.** cleanlab 기본 `high_probability_threshold=0.95`를 넘는 미매칭 예측이 연습 묶음(train fit_check)에서 0건이었다(자 예측 최대 확신도 0.93). 문턱을 낮추면 ObjectLab 기본값 기준선이 아니므로 **바꾸지 않는다.** val에서도 모집단이 0건이면 이 방법은 **"측정 불가"로 보고**하고 Q-C는 `aida` 대 `unmatched_confidence` 기술 통계만 낸다. 0건이 아니면 그대로 센다. `experiment/planning_evidence/practice1_bundle_2026-09-29.json`.

- **판정 뒤에 방법을 더하거나 빼지 않는다.** `iou_baseline`(AIDA 후보 안 재정렬)은 넣지 않는다 — v2에서는 같은 순서라 코드가 막는다.
- ObjectLab은 예측이 없는 라벨을 깨끗(1.0)으로 두고 `all_label_iou`는 맨 위에 둔다. 셋을 한 표에서 견주면 "자가 못 본 라벨"의 몫이 드러난다.
- cleanlab 버전과 "기본값 그대로"를 실행 기록에 적는다(진단 결과의 `objectlab` 항목).

### D9 — 동점과 IoU 0 라벨: **(가)**

- 높이 30px 이상 범위(D2)에서 **IoU 0 라벨도 포함**한다. 빼면 1차 비교가 "자가 본 라벨 안"으로 좁아진다.
- 동점은 **고정 씨앗 무작위**로 자른다: `tie_key = sha256("20260929:" + 후보 id)`. 후보 선정(`_top`)·판정 화면 대상·
  내보내기(`tie_key`)·집계(`rank_candidates`)·부트스트랩·coverage가 **같은 키**를 쓴다. 파일 이름순은 쓰지 않는다.
- **두 방법(과 ObjectLab)에 똑같이 적용**한다. v2 AIDA 층도 제품 순위가 아니라 점수 + `tie_key`로 선정한다.
- 보고: 범위 내 IoU 0 라벨 수, `all_label_iou` 상위 90 중 IoU 0 수, 높이 층 분포(8절·실행 기록).

## 5. 판정 규칙 — D5·D6·D8

**고정 (코드 규칙):**

- 판정 대상 = 층마다 **방법별 상위 N=90의 합집합** ∪ 무작위 표본 K=50 ∪ **고정 재표본 추가 후보**(5-1절). 겹치면 한 번만 판정한다.
- 방법의 모집단이 N보다 작으면 남는 예산을 안 쓴다.
- 무작위 표본 K는 **AIDA 규칙 밖·30px 이상 라벨에서만** 뽑고, 어느 방법의 상위 N도 바꾸지 않는다. `random_sample=true` 표시와 분모를 유지하고 추가 후보와 합치지 않는다.
- 상자가 같은 미매칭 예측이 둘 이상이면 묶음이 얼려지지 않는다 — 그때는 진단부터 본다.
- 가림: 점수·순위·유형·출처·표본 여부·`coverage_extra`를 판정 화면에 보내지 않는다. 기존 라벨인지 누락인지는 과제가 달라 가리지 않는다.
- 판정 지침: [manual-timing-pilot.md](manual-timing-pilot.md) + nuImages 규칙([nuimages-data-plan.md](nuimages-data-plan.md) 6절, amodal·잘림·사이드미러 제외·10px·20% 가시). `hit`/`miss`/`hold`. 연습에서 헷갈린 사례는 11절 지침 부록에 고정한다.

**D5.** N=90, K=50. `shuffle_seed=20260927`, `random_sample_seed=20260928`. 기존 라벨 층은 **세 묶음**(약 130건씩)으로
나눠 판정하고, 묶음을 얼린 뒤 `judging.total_judging_list`가 **400건을 넘으면 넷**으로 나눈다. 묶음 나누기는 화면
표시 단위이고 판정 대상·순서에는 영향이 없다.

**D6.** 누락 층은 **같은 세션, 별도 묶음**으로 판정한다(판정자 피로 분리). 예산 N=90 공용.

**D8.**

- **1차 분석은 사람 판정자 1인(개발자)의 전량 판정 원본 그대로**다. 사람은 지침대로 `hit`/`miss`/`hold`를 쓰고, AI와의 불일치를 이유로 수정하지 않는다.
- 판정 대상이 확정된 뒤·판정 시작 전에 **확장된 최종 판정 목록**(원래 상위 N 합집합 ∪ K ∪ 추가 후보)에서 **30%를 단순 무작위 추출**(씨앗 20260930, **올림**, 대상·최종 id 목록을 `auxiliary_sample.candidate_ids`에 저장)한다.
- AI 판정자는 **독립 판정**한다 — 새 세션, 방법·점수·순위·사람 판정 비노출, 입력은 `?adjudicator=ai` 목록(전체 장면 + 크롭 + 상자 좌표·클래스 이름)과 11절의 프롬프트 원문. 응답 원문을 전부 보존하고 거부·형식 위반은 `hold`로 사상한다.
- 보고: 양측 `hold` 수, 단순 일치율, κ(계산 대상과 분모 명시), 낮아도 공개. **AI 판정자는 사람 판정자와 교환 가능한 평정자가 아니다** — κ는 사람–사람 신뢰도의 대체물도 정확도도 아니다([literature-review-2026-09-27.md](literature-review-2026-09-27.md) §2).
- **민감도 분석(사전 계획, 1차와 나란히·대체 아님):** 사람–AI 불일치 건을 `hold`로 돌린 뒤 같은 집계를 한 번 더 낸다.
- 연습 판정(train fit_check)은 지침·입력 점검용이며 일치율 합격선은 두지 않는다.

**D8-2 두 번째 사람 판정자 (개정 2026-09-29, val 개봉 전).** 위 보조 표본(AI와 **같은 후보**)을 두 번째 사람 판정자
(`adjudicator=human2`, 이름은 실행 기록에)가 독립 판정한다 — 같은 지침·같은 가림 화면, 주 판정자·AI 판정 비노출(판정자별
파일 분리, 코드가 표본 밖 판정을 거부). 판정 전에 연습 판정(train fit_check)을 주 판정자와 같은 규칙으로 한 번 한다(분석에 쓰지
않는다). 보고: 사람–사람 단순 일치율, κ, 양성/음성 일치(p_pos·p_neg), 분모, 양측 `hold` 수, 3×3 혼동표. **1차 분석은 주 판정자
전량 판정 원본 그대로**이며 불일치로 수정하지 않는다. 민감도 분석(사전 계획): 주 판정자–human2 불일치 건을 `hold`로 돌린 뒤
같은 집계를 한 번 더 — 1차와 나란히, 대체하지 않는다. human2를 확보하지 못하면 실행 기록에 "D8-2 미실행"으로 남기고 1차
분석은 바뀌지 않는다.

**D8-3 주 판정자 재판정 (개정 2026-09-29).** 주 판정자가 본 판정을 모두 마치고 **7일 이상 지난 뒤**, 같은 보조 표본을
`adjudicator=primary_retest`로 다시 판정한다 — 자기 이전 판정 비노출. 보고: 재판정 일치율, κ, p_pos·p_neg, 분모. 1차 분석에
쓰지 않는다(판정자 내 일관성 보고용). 섞인 순서가 본 판정과 같으므로 순서 기억 효과가 남을 수 있음을 한계로 적는다.

**세 보조 판정의 관계.** AI·human2·primary_retest는 **같은 보조 표본**을 판정하므로 사람–사람, 사람–AI, 판정자 내 일치를 같은
후보에서 비교한다. 추가 구현은 필요 없다(판정자별 파일·표본 제한·`GET .../agreement?secondary=` 기존 구현).

### 5-1. 부트스트랩 판정 범위 — 안 (a)

- 기록 단위 재표집에서 원래 상위 N 밖의 후보가 재표본 상위 N에 들어올 수 있다. 미판정이면 예산은 쓰고 수확은 0으로 세어지므로, **고정 재표본(씨앗 42·2000회)에서 어느 방법의 상위 N에라도 드는 후보의 합집합을 전량 판정**한다.
- `coverage_iterations=2000`·`coverage_seed=42`를 묶음의 `bootstrap_coverage`에 얼리고 **묶음 지문에 넣는다.** 최종 분석(`experiment/analyze_qa.py`)은 같은 값을 쓰고 다르면 중단한다.
- **비교 예산 N=90**(점 추정치·1차 지표의 검수량)과 **연구용 총 판정량**(상위 N 합집합 ∪ K ∪ 추가 후보)을 갈라 적는다. 추가 후보는 부트스트랩 계산용이며 원래 상위 N·점 추정치를 바꾸지 않는다.
- 최종 분석은 `paired_cluster_bootstrap(require_judged_top_n=True)` — 어느 재표본의 상위 N에라도 `verdict=None`이 있으면 구간을 내지 않는다.
- 이 방식은 고정 재표본의 판정 누락만 없앤다. **구간의 포함률·통계적 타당성은 보장하지 않는다**(기록 수가 적을 때의 백분위 구간 등) — 결과 문서 한계 절.

### 5-2. 판정 상한 C와 중단·재계획 절차

1. 묶음을 얼리기 **전에** 판정 상한 C(건)를 11절에 적는다(연습의 후보당 시간 × 계획 세션 수).
2. 묶음을 얼린 뒤 `judging.total_judging_list`가 C를 넘으면 **그 묶음으로 본 판정을 시작하지 않는다.** 얼린 묶음과 수치는 실행 기록에 남기고 지우지 않는다.
3. **하지 않는 것:** 추가된 후보를 본 뒤 씨앗·반복 수를 바꾸기, 추가 후보를 임의로 잘라내기, 미판정을 0으로 세거나 재표본을 버리기.
4. **하는 것:** 이 문서를 개정(N·반복 수·표본 수·방법 수 중 무엇을 줄일지와 이유)하고 커밋한 뒤 **새 평가 ID**로 다시 얼린다. 개정 전후 묶음 지문을 둘 다 기록한다.

## 6. 판정 뒤 분석 — D7

**절차 (고정):**

1. 내보내기 — 기존 라벨 층 `?methods=aida,all_label_iou,all_label_objectlab&scope=labelled_candidates&mode=candidate_generation_included`,
   누락 층 `?methods=aida,unmatched_confidence,unmatched_objectlab&scope=missing_candidates&mode=candidate_generation_included`.
2. `experiment/analyze_qa.py` — `importer.load_export` → `summary.summarise`로 방법마다 N=90에서 **고유 오류 수**·hit 후보 수·보류 수·결정된 수·`method_population`.
3. 기존 라벨 층의 짝지은 차이와 구간은 `require_same_candidates=False`(기록 묶음 짝지음)로 낸다. `same_candidate_set: false`를 보고서에 그대로 적는다 — **정렬 효과로 부르지 않는다.**
4. 표본 층: `random_sample: true`인 줄만으로 판정 오류 비율과 Wilson 95% 구간. 방법별 고유 오류 수와 합치지 않는다.
5. 누락 층: 세 방법의 hit·보류 수. `descriptive_only`.
6. 높이 층별 보고(경계 30-60·60-120·120+, 30px 미만은 범위 밖): 방법의 상위 N을 전체에서 고른 뒤 층으로 나눈 기술통계.

**D7 확정값.**

| 항목 | 값 |
|---|---|
| 1차 지표 | **N=90에서 고유 오류 수의 차이 `all_label_iou − aida`.** 방향 예측은 적지 않는다(prelim1 방향은 v1 것이라 v2에 근거가 없다) |
| 1차 검수량 | **N=90 하나.** 다른 깊이(10~80)는 사후 진단이며 구간을 따로 확인된 결과로 읽지 않는다 |
| 구간 | 기록 묶음 짝지은 부트스트랩, **씨앗 42·2000회**, 백분위 95% |
| 표본 층 구간 | **Wilson 95%** |
| Δ 방침 | **Δ 없음.** 성공·실패를 적지 않는다 |
| 재표집 단위 | 주행 기록(`group_id`) |
| 동점·IoU 0 | D9 (가) |
| 보조 비교 | `all_label_objectlab − aida`, `all_label_objectlab − all_label_iou`를 같은 방법으로. 1차 지표가 아니다 |
| 민감도 | 사람–AI 불일치 건 `hold` 처리 후 재집계(5절 D8) |

## 7. 지키는 약속

- 판정을 본 뒤 **N·K·방법·씨앗·판정 규칙·1차 지표·Δ 방침·coverage 설정을 바꾸지 않는다.**
- 결과가 불리해도 **이 데이터로 순서·문턱을 다시 세지 않는다.** 판정 뒤 이 300장은 소비된 개발 데이터가 된다.
- **판정을 정답으로 부르지 않는다.** 한 사람의 판정은 일관성을 보일 뿐 정확성이 아니다. accuracy를 계산하지 않는다.
- 후보 생성 포함 비교를 **정렬 효과**로, 표본 층 비율을 **참 오류 비율**로, 사람–AI 일치도를 **신뢰도나 정확도**로 부르지 않는다.
- 자는 평가 데이터와 같은 데이터셋으로 학습했다 — 결과를 고객 조건으로 옮기지 않는다.
- 이 결과는 30px 이상 차량에 대한 것이다. 작은 차의 라벨 오류 탐지에 대해서는 말하지 않는다.
- 이 단계의 결과를 **상업적 주장·영업 자료에 쓰지 않는다**(목적 A). nuImages 출처와 CC BY-NC-SA 4.0을 적고 원본·가중치를 재배포하지 않는다.

## 8. 판정 전 점검 — 묶음을 얼린 뒤 실행 기록(`docs/qa-run-record.md`)에 채운다

이 문서는 고치지 않는다. 얼린 뒤에만 알 수 있는 실제 수는 실행 기록에 묶음 지문과 함께 적는다.

| 점검 | 기대 |
|---|---|
| `ruler.weights_sha256` = 11절 값 | 같다 |
| `all_candidates` 길이 = `total_in_queue` | 같다 |
| `all_labels` 길이 = 진단 요약의 `total_labels` | 같다 |
| `unmatched_predictions`·`objectlab` 항목이 있다 | 있다 |
| 묶음이 얼려졌다(상자 중복 거부 없음) | 200 |
| 높이 30px 미만 제외 수 (방법별 모집단·K 풀) | 기록 |
| 출처별 후보 수 (`aida_candidate`·`label`·`unmatched_prediction`) | 기록 |
| 판정 대상 = 원래 상위 N 합집합 ∪ K ∪ 추가 후보 — 세 수를 따로 | 손으로 다시 센 수와 같다 |
| `judging.total_judging_list` ≤ C | 넘으면 5-2절 |
| 범위 내 IoU 0 라벨 수, `all_label_iou` 상위 90 중 IoU 0 수, 높이 층 분포 | 기록 |
| 표본 K건이 전부 `source=label`·규칙 밖·30px 이상 | 맞다 |
| 보조 표본 수(올림)·id 목록 저장 | 기록 |
| 판정 목록에 점수·순위·유형·출처·표본 여부·`coverage_extra`가 없다 | 없다 |
| 섞인 순서가 씨앗대로 같은가 | 두 번 만들어 같다 |
| `bootstrap_coverage`(2000·42·입력 지문)가 묶음 지문에 들어 있다 | 있다 |
| cleanlab·ultralytics·torch 버전 | 기록 |
| 합성 판정으로 내보내기 → 집계 → 부트스트랩 (메모리에서, 실제 폴더에 판정 파일 없음) | 통과 |

## 9. 실행 순서

1. **연습 판정** — train fit_check, [practice-judging-plan.md](practice-judging-plan.md). 연습 씨앗은 본 판정 씨앗과 다르게. 분석에 쓰지 않는다.
2. **지침·프롬프트 고정** — 연습에서 헷갈린 사례를 지침 부록에, 프롬프트 원문과 모델 식별자를 11절에.
3. **판정 상한 C** 결정 → 11절.
4. **이 문서 커밋·푸시.**
5. val 표집 → 업로드 → 진단 → 묶음 얼리기 → 8절 점검 → 실행 기록.
6. 본 판정 — 사람 전량, AI 보조 표본. 판정 뒤 집계·감사·결과 문서.

## 10. 커밋 뒤, 판정 전에 할 일

1. 가림 화면을 **점검용 평가**(같은 씨앗·예산의 별도 ID)로 열어 본다. 실제 평가에 기록이 남지 않게.
2. 점검용 평가에서 실제 브라우저로 목록을 넘기며 이미지가 그려지는지 본다(전체 장면 + 크롭).
3. 점검 탭을 닫고 늦게 오는 기록 전송을 기다린 뒤, 실제 평가에 `adjudications*.json`·`activity.jsonl`이 없는지 본다.
4. 마지막 판정 뒤 기록 전송이 끝났는지 확인한다(prelim1의 186 대 185 사례).

## 11. 실행 명세 — 커밋 전에 채운다

| 항목 | 값 | 어디서 |
|---|---|---|
| 자 `car_v1_e100` 가중치 SHA-256 | `fffecf529a6df1a87d5f10ec2f5613d55adaf69ec09fd48996ecd467584110cc` (2026-09-29 데스크탑, `experiment/planning_evidence/desktop_environment.json`; 연습 진단 응답과 일치) | 데스크탑 `check_run_environment.py` 또는 `GET /api/datasets/rulers` |
| AI 판정자 모델 식별자·버전·스냅샷 날짜·온도·입력 해상도 | **[미기입 — 임의로 채우지 않는다]** | 연습 4단계에서 정해 적는다. UI가 노출하지 않는 값은 "설정 불가/미노출" |
| AI 판정 프롬프트 원문 | **[미기입]** — [ai-adjudicator-prompt-draft.md](ai-adjudicator-prompt-draft.md)를 연습 뒤 고정해 여기 그대로 붙인다 | 연습 뒤 |
| 판정 상한 C (건) | **[미기입]** | 연습의 후보당 시간 × 계획 세션 수 |
| 사람 판정 지침 부록 (헷갈린 사례) | **[미기입]** | 연습 뒤 |

네 칸 중 하나라도 비어 있으면 이 문서는 사전 등록이 아니다. (D8-2 human2의 이름·확보 여부는 관문이 아니라 실행 기록에 적는다.)
