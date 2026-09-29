# 논문 초안의 수치·주장 ↔ 근거 파일 대응표

> 2026-09-29 노트북. **모든 값은 문서가 아니라 결과 파일을 열어 다시 읽었다.** 읽은 방법을 "재계산" 열에 적는다.
> 문서(`current-evidence.md`, README)와 다른 값이 나온 것은 맨 아래 "문서와 달랐던 것"에 모았다.
> 결과 파일은 읽기만 했고 고치지 않았다.

## A. 통제 실험 — 주입 오류 (초안 6절)

| 초안 주장 | 값 | 근거 파일 | 재계산 |
|---|---|---|---|
| 유형 판별 정확도 | **25/27 = 92.6%** | `backend/app/data/label_diagnosis_eval.csv` | `correct==True` 행 수. 틀린 2건: `missing_10`, `duplicate_10` |
| 회전 조건은 "크기 계열이면 정답"으로 채점 | 채점 규칙 | `experiment/evaluate_label_diagnosis.py` docstring·`EXPECTED_SUSPICION` | 코드 확인 |
| KITTI Car 상위 10% 정밀도 | **99.7%** (0.9968) | `experiment/box_accuracy_eval.json` → `precision_at_k.top_10pct` | 단일 시드, 조건 26, micro P 0.680 / R 0.854, TP 2191 / FP 1029 |
| 다중 클래스 상위 10% | 89.1% | `experiment/box_accuracy_eval_mc.json` → `precision_at_k.top_10pct=0.8913` | 조건 29 |
| 자 적합 — 4클래스·29조건·7시드 상위 10% | 자기 도메인 **94.0 ±2.20** · 약한 이동 64.6 ±5.45 · 먼 이동(1C) 65.8 ±2.59 · 넓은 자(800) 61.3 ±3.27 | `experiment/seeded_ruler4_7seeds.json` → `rulers[*][i].top10` | 시드 7개의 평균·표본표준편차(×100) 직접 계산. 시드 42·7·123·777·2024·2025·31337 |
| 시드별 자기 도메인 우위 | 시드 7개 **모두**에서 자기 도메인 자가 최고. 자기 도메인 최저 **91.2**(시드 7) 대 다른 자 최고 **70.6**(약한 이동, 시드 777) | `experiment/seeded_ruler4_7seeds.json` → `rulers[*][i].top10` | 시드별 4자 값을 직접 읽어 비교. README·current-evidence의 "7.1~11.8σ"와 초안 이전 판의 "5.4~10.9배"는 차이를 한쪽 SD로 나눈 값이라 **쓰지 않는다** |
| 어긋난 자 정의 | 6.2: 약한 이동(4클래스, `mc` 대 `cyclist_rich` 프레임)·먼 이동(Car 1클래스)·넓은 자(4클래스 800장); 6.4: 약한 이동·넓은 자·broad 자전거0/중/多(넓은 풀 400장, Cyclist 0/39/76개, 평가셋과 겹침 0) | `docs/21-next-plan.md` "설계 — 클래스는 같게, 도메인만 다르게"(3846행~), "결과 (같은 cyclist_rich 데이터, 자만 교체)"(2436행~); `rank_fix_seed*.json` `rows[*].label` | 문서·JSON 라벨 대조 |
| 자 정의표 — 학습 장수·에폭 확인 | COCO 자기: COCO val2017 차량 프레임 520장을 KITTI와 같은 분할(400/120) → **400장 확인**(`docs/21-next-plan.md` 3369행). broad 자전거0/중/多: broad 풀 400장씩, 평가셋과 겹침 0 → **확인**(3849~3850행). 넓은 자(800): cyclist_rich 제외 1000장 풀에서 800장 → **확인**(2518~2522행). 약한 이동: `mc` 4클래스 기본 `N_TRAIN=400` → **확인**(`config.py`, 2441행). **에폭: 확인(2026-09-29 데스크탑)** — `experiment/runs*/*/args.yaml` 321개 중 `runs_nuimages/car_v1_e100`만 `epochs: 100`, 나머지 320개(KITTI·COCO·mc·nested·obb 전부) `epochs: 50`. `imgsz: 640`, `model: yolov8n.pt` | `experiment/config.py:190`, `docs/21-next-plan.md` 해당 행, `experiment/switch_to_reduced_epochs.sh` | 초안 3.1 자 정의 문단에 반영 |
| 진짜 도메인 이동 — COCO 26조건·3시드 | COCO 자기 **82.4 ±7.60** · KITTI→COCO **26.0 ±1.75** | `experiment/seeded_coco_3seeds.json` | 시드 42·123·2024. 평균·표준편차 직접 계산 |
| 유형별 생존 (COCO 자기 → KITTI→COCO) | missing 94.9→76.7 · duplicate 82.6→40.8 · width 75.5→29.4 · height 77.9→20.2 · rot 90.1→13.4 · scale 81.1→9.9 · trans_x 74.5→9.0 · trans_y 80.7→7.5 | 같은 파일 `per_condition` | 유형별로 조건·시드를 합쳐 평균 |
| 계통 유형 우선 정렬 @5 (주입 조건 관찰) | 어긋난 자 5종 평균 **+0.422 / +0.418 / +0.385**, 세 시드 평균 **+0.408 (≈+0.41)**; 맞는 자 +0.007 / +0.028 / +0.145 (평균 **+0.06**) | `experiment/rank_fix_seed42.json`·`_seed123`·`_seed2024` → `rows[*].after["5"] − before["5"]` | 어긋난 자 = broad 자전거0·중·多, 약한 이동, 넓은 자(800). @10은 +0.326/+0.327/+0.313. **정렬 규칙 상수(0.06, 중앙값×2)는 같은 주입 조건에서 정한 in-sample** (`label_diagnosis.py` 주석, docs/21 AV~BB) |
| 확신도 바닥 실험 — 성공선과 최고값 | 성공선 "무너진 자 @10 **+0.05** 이상", 최고 **+0.037**(COCO, 바닥 0.40); KITTI에서는 −0.002 | `experiment/conf_*.json`(COCO 자기)·`confhi_*.json`·`confk_*.json`(KITTI 자기), 시드 42·123·2024; 판정 문장은 `docs/21-next-plan.md` BC절(5282행~, "성공선은 … 최고가 +0.037") | JSON은 바닥별 @5/@10/@20 정밀도 원자료. +0.037·−0.002·성공선은 BC절 문장에서 읽었다(원자료에서 재계산은 안 했다) |
| 자기 정제 — 버린 프레임당 오류 | keep 90%에서 프레임 1장이 데려간 오류 400장 3.20건·800장 **3.81건**, 무작위 0.85·0.93건 → **4.1배** | `docs/21-next-plan.md` AT절 4524~4533행(정제 로그의 의심 건수 표) | 문서 표에서 읽음(원 로그 파일은 `runs*/`에 있어 저장소 밖) |
| 자기 정제는 진다 | **13개 설정 전부 음수, −0.030 ~ −0.245 mAP50** | `backend/app/data/metrics_mc_nested.csv`(400장)·`_n800`·`_n1600`·`_n3200` | `refined{k} − 원본조건`: 400장 missing_30 −0.213/−0.162/−0.075/−0.030(keep 30/50/70/90), scale_m30 −0.122; 800장 missing −0.245/−0.213/−0.119/−0.054, scale −0.177; 1600장 scale −0.181, missing −0.184; 3200장 scale −0.169. 각 점 단일 관측 |
| OBB에서는 회전 조건 저하가 사라짐 | AABB rot_m15 −5.71% vs OBB −0.81% 등, 3시드에서 ±방향 차이 기각 | `backend/app/data/metrics_obb.csv`·`metrics_obb_multi_seed.csv`, `docs/21-next-plan.md` "OBB 실험 결과 요약" | 문서 값 인용, CSV 존재 확인. 초안에서는 "회전 조건은 AABB 표현 한계" 근거로만 |
| 임계값·신뢰도 상수의 보정 출처 | 같은 27~29개 조건에서 잰 값 | `experiment/label_diagnosis.py` 상수 주석 | 코드 확인 — **in-sample** 한계로 적는다 |

## B. prelim1 — 탐색 비교 (초안 7절)

| 초안 주장 | 값 | 근거 파일 | 재계산 |
|---|---|---|---|
| N=90 고유 오류 | AIDA v1 **4**, `1 − label_iou` **14**, 차이 **−10**, 95% [−18, −2] | `experiment/planning_evidence/prelim1_results.json` → `labelled_layer.by_budget[budget=90]` | 직접 읽음. 부트스트랩 씨앗 42·2000회·이미지 묶음 짝지음 |
| 독립 산술 감사 일치 | AIDA 4/4/보류 1/결정 89, 기준선 14/14/1/89, 겹침 18(오류 0), AIDA만 72(오류 4), 기준선만 72(오류 14), 90위 경계 동점 없음 | `prelim1_n90_independent_audit.json` | 직접 읽음 |
| 판정 분포 | 162건 — 오류 18 · 아님 142 · 보류 2 (보류율 1.2%), hit 비율 0.111, 오류 이미지 17장(16장 1건·1장 2건) | `prelim1_results.json` → `labelled_layer` | 직접 읽음 |
| 누락 층 | 24건 중 오류 22 (비교군 없음) | `docs/prelim1-results.md` 4절 | **결과 JSON에 `missing_layer` 키 없음** — 문서 값. 초안에 "문서 기준" 표시 |
| 판정별 심각도·IoU 중앙값 | 오류(hit, n=18) 심각도 중앙값 **0.3044**, 아님(miss, n=142) **0.3514**; `label_iou` 중앙값 0.5956 / 0.6585 | `prelim1_failure_analysis.json` → `severity_by_verdict`, `label_iou_by_verdict` | 직접 읽음 |
| 제품 순서가 만들어진 방식 | 절대 문턱 0.12 미달, 상대 문턱으로 width 하나가 계통 유형, 후보 307 중 width 124가 1~124위, AIDA 상위 90 = 100% width | `prelim1_failure_analysis.json` → `product_order`, `top90_type_mix` | 직접 읽음 |
| 유형별 판정(합집합 162) | width 94/오류 4 · scale 27/5 · duplicate 17/4 · trans_x 8/3 · height 9/1 · trans_y 7/1 | 같은 파일 `judged_union_by_type` | 직접 읽음 |
| 작업 기록 결함 | 판정 186 vs 기록 185, 마지막 세션 끝 미기록, `5cf0e998`에서 수정 | `docs/prelim1-results.md` 5절 | 문서·커밋 참조 |
| 데이터 | KITTI val Car 300장, 씨앗 20260914, 자 `runs/clean` | `docs/prelim1-preregistration.md` 2절, `prelim1_manifest.json` | 문서 |

## C. Q-A 설계 (초안 8절) — 결과 없음

| 항목 | 값 | 근거 파일 |
|---|---|---|
| D1~D9, coverage 설정 | `docs/qa-preregistration.md` 0절 | 커밋 `cdb30a3`·`2462562` |
| 자 `car_v1_e100` | SHA-256 `fffecf52…`, fit_check 짚은 비율 71.6%, ruler_val fitness 0.5162(best 93에폭), 학습 3,200장·100에폭·4,093초 | `experiment/planning_evidence/nuimages_fit_check_car_v1_e100.json`, `desktop_environment.json` |
| fit_check 높이별 짚은 비율 | <30px 50.7% · 30–60 77.6% · 60–120 86.2% · ≥120 96.0%; IoU 0 라벨 233/1,728 | 같은 fit_check 파일 `by_height`, `labels_with_iou0` |
| nuImages 분할 | train 67,279 키프레임·기록 350 → fit_check 620장(기록 7) · ruler_val 357(기록 3) · ruler_train 3,200(기록 303), 씨앗 20260916 | `nuimages_split_dev_v1.json` |
| 연습 묶음 practice1 (train fit_check, **계획용**) | 라벨 1,728 · 후보 566 · 높이 필터 제외 라벨 317·AIDA 후보 172 · N=20·K=10에서 원래 상위N∪K 89 + 재표본 추가 83 = 172 (기본 풀 대비 **+93.3%**) · `unmatched_objectlab` 모집단 **0건** | `practice1_bundle_2026-09-29.json` | 결과가 아니다 — 방법·한계 절에서 판정량 근거로만 |
| `unmatched_objectlab` 측정 불가 사유 | cleanlab 기본 `high_probability_threshold=0.95`, 자 예측 최대 확신도 0.93 | 같은 파일, `docs/qa-preregistration.md` 4절 (사용자 결정 (a), 2026-09-29) |
| 합성 시뮬레이션 (**저장소 JSON 판본**) | 미판정 진입 재표본 비율: aida 0.48/0.49/0.43, ObjectLab 0.46/0.50/0.48, all_label_iou 0.33/0.33/0.14 (씨앗 1/2/3) → 초안 "43~49% / 46~50% / 14~33%". 재표본당 상위 90 미판정 평균: aida 3.87/1.87/1.55, ObjectLab 2.90/3.84/3.63, iou 0.63/0.78/0.33. 추가 판정량 +53/+61/+71 = 원래 판정 범위 242/245/233의 **21.9/24.9/30.5%** | `sim_unjudged_2026-09-27.json` → `results[*].iou_minus_aida.current_code.unjudged_in_top_n`, `objectlab_minus_aida…`, `coverage` | **판본 차이:** `docs/literature-review-2026-09-27.md` §3.3 표(aida 2.7~4.2, iou 0.15~0.2)는 저장소 밖 초기 스크립트(두 방법, K 없음)의 값이고, `docs/unjudged-bootstrap-review-2026-09-27.md` 2절 표(aida 2.51/1.31/1.09, iou 0.45/0.54/0.21)는 커밋된 JSON과도 다르다(문서 작성 뒤 재실행된 것으로 보임). **초안은 커밋된 JSON 값 하나로 맞췄다.** 합성 — "합성 조건의 예시"로만 |
| W4 드라이런 판정량 | N=90·K=50에서 388건 | `w4_dryrun.json` → `judging_load.candidates_to_judge` |
| 판정 시간 상수 | `s_plan = 5.02초` (timing5, 120건 연속) | `docs/sustained-pilot-protocol.md`, `docs/25-advancement-roadmap.md` 110행 | 문서 |
| 소비된 개발 데이터 원장 | prelim1 300장, 파일럿 `ffffffffff01~07` 338장 | `docs/evaluation-data.md` |

## D. 환경·재현

| 항목 | 값 | 근거 |
|---|---|---|
| 패키지 | Python 3.14.0, cleanlab 2.9.0, ultralytics 8.4.90, torch 2.12.1+cu126, numpy 2.4.4 | `desktop_environment.json` |
| GPU | RTX 3050 6GB | `nuimages_fit_check_car_v1_e100.json` → `training.gpu` |
| 대회 시기 / 이후 구분 | 2026-07-07~08-19 커밋 20개 / 2026-08-26~ 커밋 218개(2026-09-08 기준) | `docs/reproduction.md` "대회 시기와 개인 개발의 범위 구분" |
| 검사 수 | backend 367 통과·1 건너뜀, experiment 541 통과 (2026-09-27 노트북) | `CLAUDE.md` — **이번에 다시 돌리지 않았다** |

## 문서와 달랐던 것 / 확인 못 한 것

| 항목 | 문서 | 파일 | 처리 |
|---|---|---|---|
| 처방 @5 | README 한때 +0.42 | 세 시드 평균 +0.408 | 초안은 +0.41로, 시드별 값 병기 (current-evidence.md 정정과 같음) |
| prelim1 누락 층 22/24 | `prelim1-results.md` | `prelim1_results.json`에 누락 층 키 없음 | 초안에 "문서 기준, 결과 JSON에는 없음" 각주 |
| 자기 정제 "13개 설정" | `current-evidence.md` 6절 | CSV에서 13점 확인(위 A표) — 일치 | — |
| 대회 발표자료 수치 (예: 21조건, 품질점수) | 발표 PDF | 대회 시기 산출물은 재생성 불가(`reproduction.md`) | 초안에 넣지 않음 |
| 검사 수 | CLAUDE.md | 미실행 | 초안에 검사 수를 쓰지 않음 |
