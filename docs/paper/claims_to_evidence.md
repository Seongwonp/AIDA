# 논문 초안의 수치·주장 ↔ 근거 파일 대응표

> 2026-09-29 노트북. **모든 값은 문서가 아니라 결과 파일을 열어 다시 읽었다.** 읽은 방법을 "재계산" 열에 적는다.
> 문서(`current-evidence.md`, README)와 다른 값이 나온 것은 맨 아래 "문서와 달랐던 것"에 모았다.
> 결과 파일은 읽기만 했고 고치지 않았다.

## A. 통제 실험 — 주입 오류 (초안 6절)

| 초안 주장 | 값 | 근거 파일 | 재계산 |
|---|---|---|---|
| 유형 판별 정확도 | **25/27 = 92.6%** | `backend/app/data/label_diagnosis_eval.csv` | `correct==True` 행 수. 틀린 2건: `missing_10`, `duplicate_10`. 데이터셋 단위 판별이라 채점 순서와 무관(2026-10-06 재확인 25/27) |
| 회전 조건은 "크기 계열이면 정답"으로 채점 | 채점 규칙 | `experiment/evaluate_label_diagnosis.py` docstring·`EXPECTED_SUSPICION` | 코드 확인 |
| KITTI Car 상위 10% 정밀도 | **99.7%** (0.9968) | `experiment/box_accuracy_eval.json` → `precision_at_k.top_10pct` | 단일 시드, 조건 26, micro P 0.680 / R 0.854, TP 2191 / FP 1029. **순서: `legacy_severity_v0`(과거 순서)** — 08-29~30 커밋(09-06 `2f46365` 이전) 결과이고, 프로파일 없이 돈 2단계 재추론 D의 legacy `all_conditions_finding_unit` 0.9968과 일치. 같은 재추론의 `review_order_v1`은 **0.9583** (`controlled_baseline_stage2_tieseed_2026-10-06.json` → `groups.D.rulers.kitti_car_clean.all_conditions_finding_unit`). micro P/R은 순서 무관 |
| 다중 클래스 상위 10% | 89.1% | `experiment/box_accuracy_eval_mc.json` → `precision_at_k.top_10pct=0.8913` | 조건 29. **순서: `legacy_severity_v0` 규칙, 신뢰도 프로파일 사용** — 08-31(`2f46365` 이전) 결과, 당시 코드는 절대 문턱 rescore 뒤 −severity 정렬. 프로파일 사용은 [명세](controlled-baseline-spec.md) 1·4절(캐시 `box_accuracy_verdicts_mc.json` 심각도가 프로파일로 재현). 캐시의 저장 순서로 상위 10%를 다시 세면 0.8913(29조건, 2026-10-06). 자(`runs_mc/clean`)는 2단계 재추론에 없어 `review_order_v1` 값 없음 |
| 자 적합 — 4클래스·29조건·7시드 상위 10% | 자기 도메인 **94.0 ±2.20** · 약한 이동 64.6 ±5.45 · 먼 이동(1C) 65.8 ±2.59 · 넓은 자(800) 61.3 ±3.27 | `experiment/seeded_ruler4_7seeds.json` → `rulers[*][i].top10` | 시드 7개의 평균·표본표준편차(×100) 직접 계산. 시드 42·7·123·777·2024·2025·31337 |
| 시드별 자기 도메인 우위 | 시드 7개 **모두**에서 자기 도메인 자가 최고. 자기 도메인 최저 **91.2**(시드 7) 대 다른 자 최고 **70.6**(약한 이동, 시드 777) | `experiment/seeded_ruler4_7seeds.json` → `rulers[*][i].top10` | 시드별 4자 값을 직접 읽어 비교. README·current-evidence의 "7.1~11.8σ"와 초안 이전 판의 "5.4~10.9배"는 차이를 한쪽 SD로 나눈 값이라 **쓰지 않는다** |
| 어긋난 자 정의 | 6.2: 약한 이동(4클래스, `mc` 대 `cyclist_rich` 프레임)·먼 이동(Car 1클래스)·넓은 자(4클래스 800장); 6.4: 약한 이동·넓은 자·broad 자전거0/중/多(넓은 풀 400장, Cyclist 0/39/76개, 평가셋과 겹침 0) | `docs/21-next-plan.md` "설계 — 클래스는 같게, 도메인만 다르게"(3846행~), "결과 (같은 cyclist_rich 데이터, 자만 교체)"(2436행~); `rank_fix_seed*.json` `rows[*].label` | 문서·JSON 라벨 대조 |
| 자 정의표 — 학습 장수·에폭 확인 | COCO 자기: COCO val2017 차량 프레임 520장을 KITTI와 같은 분할(400/120) → **400장 확인**(`docs/21-next-plan.md` 3369행). broad 자전거0/중/多: broad 풀 400장씩, 평가셋과 겹침 0 → **확인**(3849~3850행). 넓은 자(800): cyclist_rich 제외 1000장 풀에서 800장 → **확인**(2518~2522행). 약한 이동: `mc` 4클래스 기본 `N_TRAIN=400` → **확인**(`config.py`, 2441행). **에폭: 확인(2026-09-29 데스크탑)** — `experiment/runs*/*/args.yaml` 321개 중 `runs_nuimages/car_v1_e100`만 `epochs: 100`, 나머지 320개(KITTI·COCO·mc·nested·obb 전부) `epochs: 50`. `imgsz: 640`, `model: yolov8n.pt` | `experiment/config.py:190`, `docs/21-next-plan.md` 해당 행, `experiment/switch_to_reduced_epochs.sh` | 초안 3.1 자 정의 문단에 반영 |
| 진짜 도메인 이동 — COCO 26조건·3시드 | COCO 자기 **82.4 ±7.60** · KITTI→COCO **26.0 ±1.75** | `experiment/seeded_coco_3seeds.json` | 시드 42·123·2024. 평균·표준편차 직접 계산 |
| 유형별 생존 (COCO 자기 → KITTI→COCO) | missing 94.9→76.7 · duplicate 82.6→40.8 · width 75.5→29.4 · height 77.9→20.2 · rot 90.1→13.4 · scale 81.1→9.9 · trans_x 74.5→9.0 · trans_y 80.7→7.5 | 같은 파일 `per_condition` | 유형별로 조건·시드를 합쳐 평균 |
| 계통 유형 우선 정렬 @5 (주입 조건 관찰) | 어긋난 자 5종 평균 **+0.422 / +0.418 / +0.385**, 세 시드 평균 **+0.408 (≈+0.41)**; 맞는 자 +0.007 / +0.028 / +0.145 (평균 **+0.06**) | `experiment/rank_fix_seed42.json`·`_seed123`·`_seed2024` → `rows[*].after["5"] − before["5"]` | 어긋난 자 = broad 자전거0·중·多, 약한 이동, 넓은 자(800). @10은 +0.326/+0.327/+0.313. **순서(2026-10-06 확인): `before` = `legacy_severity_v0`, `after` = 절대 문턱만 승격한 계통 우선 정렬(`2f46365`~`ba937f9c` 사이, 상대 문턱 없음) — `review_order_v1`이 아니다.** 세 파일 모두 `ba937f9c`(09-06 10:22) 전 커밋(00:16·09:35), 스크립트 `rank_systematic_first.py`. 2단계 재추론(프로파일 없음)에서 자기 도메인·약한 이동·넓은 자 × 시드 3의 `before` @5가 legacy와 9/9, `after` @5가 legacy 목록을 legacy `present_types`로 안정 분할한 값과 9/9 일치. `review_order_v1` @5는 넓은 자 3시드·약한 이동 2024에서 `after`보다 높다(예: 넓은 자 s42 0.779→0.883) — broad 자전거 3종은 재추론에 없어 5종 평균의 v1 값은 못 냄. 재계산 평균 +0.4083, 맞는 자 +0.0598. **상대 문턱 상수(0.06, 중앙값×2)는 +0.41 측정 뒤에 넣었고, 역시 같은 주입 조건에서 정한 in-sample** (`label_diagnosis.py` 주석, docs/21 AO·AV~BB) |
| 확신도 바닥 실험 — 성공선과 최고값 | 성공선 "무너진 자 @10 **+0.05** 이상", 최고 **+0.037**(COCO, 바닥 0.40); KITTI에서는 −0.002 | `experiment/conf_*.json`(COCO 자기)·`confhi_*.json`·`confk_*.json`(KITTI 자기), 시드 42·123·2024; 판정 문장은 `docs/21-next-plan.md` BC절(5282행~, "성공선은 … 최고가 +0.037") | JSON은 바닥별 @5/@10/@20 정밀도 원자료. 성공선은 BC절 문장. **2026-10-06 원자료 재계산:** KITTI→COCO @10 시드 평균 바닥 0.25 0.391 → 0.40 0.428(+0.037); KITTI 넓은 자 0.894→0.892(−0.002, `confk`). **순서: `review_order_v1`(현재 순서)** — 09-08 커밋(`ba937f9c` 뒤), 바닥 0.25 기준값이 2단계 재추론의 `review_order_v1` @10과 12/12(자 4종 × 시드 3) 일치(legacy와는 불일치) |
| 자기 정제 — 버린 프레임당 오류 | keep 90%에서 프레임 1장이 데려간 오류 400장 3.20건·800장 **3.81건**, 무작위 0.85·0.93건 → **4.1배** | `docs/21-next-plan.md` AT절 4524~4533행(정제 로그의 의심 건수 표) | 문서 표에서 읽음(원 로그 파일은 `runs*/`에 있어 저장소 밖). 4.1배 = 800장(3.81/0.93), 400장은 3.8배. 프레임을 의심 건수로 고르므로(`refine_ruler.py`) 채점 순서와 무관 |
| 자기 정제는 진다 | **13개 설정 전부 음수, −0.030 ~ −0.245 mAP50** | `backend/app/data/metrics_mc_nested.csv`(400장)·`_n800`·`_n1600`·`_n3200` | `refined{k} − 원본조건`: 400장 missing_30 −0.213/−0.162/−0.075/−0.030(keep 30/50/70/90), scale_m30 −0.122; 800장 missing −0.245/−0.213/−0.119/−0.054, scale −0.177; 1600장 scale −0.181, missing −0.184; 3200장 scale −0.169. 각 점 단일 관측. 2026-10-06 CSV에서 13점 재확인. 학습 mAP50이라 채점 순서와 무관 |
| OBB에서는 회전 조건 저하가 사라짐 | AABB rot_m15 −5.71% vs OBB −0.81% 등, 3시드에서 ±방향 차이 기각 | `backend/app/data/metrics_obb.csv`·`metrics_obb_multi_seed.csv`, `docs/21-next-plan.md` "OBB 실험 결과 요약" | 문서 값 인용, CSV 존재 확인. 초안에서는 "회전 조건은 AABB 표현 한계" 근거로만 |
| 임계값·신뢰도 상수의 보정 출처 | 같은 27~29개 조건에서 잰 값 | `experiment/label_diagnosis.py` 상수 주석 | 코드 확인 — **in-sample** 한계로 적는다 |

## A2. 통제 기준선 2단계 — 재추론 (2026-10-06 데스크탑, 초안 6절 반영)

**전부 합성 주입 오류에 대한 채점이다 — 사람 판정·자연 오류가 아니며, 이 8개 자·조건 밖으로 일반화하지 않는다.** 값은 확정 동점 규칙(고정 씨앗 해시, 1차 씨앗 20260929)으로 다시 집계한 `experiment/planning_evidence/controlled_baseline_stage2_tieseed_2026-10-06.json`(집계 `experiment/analyze_controlled_baseline_stage2.py`)에서 읽었다. 옛 동점 규칙 값은 같은 파일 `*_tie_name_index`와 원래 파일 `controlled_baseline_stage2_2026-10-06.json`(같은 값). 공통 예산 k = max(1, ⌊0.1 × AIDA finding⌋), 후보 < k여도 분모 k(사용자 확정). 기존 라벨 층은 `missing_*` 제외 조건 평균 → 시드 평균 ± 표본SD. C·D는 단일 시드, C는 신뢰도 프로파일 없이 돌림. AIDA 열은 finding 단위, 전체 라벨 열은 고유 라벨 단위. 상세: [명세 6절·6.5절](controlled-baseline-spec.md).

| 주장 후보 | 값 | 근거 키 | 조건 |
|---|---|---|---|
| 재추론이 seeded 값을 재현 | legacy P@10% 조건별 일치 **A 812/812 · B 156/156**; C·D 지목 수·TP 29/29 · 26/26 | `groups.*.rulers.*.seeds.*.repro_vs_seeded` (C·D 대조는 원래 파일 `flagged_tp_vs_eval`) | 프로파일 없음, limit 80. **C는 원래 self 평가와 달리 신뢰도 프로파일 없이** 돌렸다(지목·TP만 대조) |
| 두 순서 — 전 조건 상위 10%(seeded `top10`과 같은 정의), 초안 표 1 | legacy: 자기 도메인 0.940 ± 0.022 · 먼 이동 0.658 ± 0.026 · 약한 0.646 ± 0.054 · 넓은 0.613 ± 0.033. current: 0.985 ± 0.004 · 0.808 ± 0.013 · 0.762 ± 0.058 · **0.907 ± 0.022** | `groups.A.rulers.*.all_conditions_finding_unit` | A, 7시드, 29조건, finding 단위. 동점 규칙 무관 |
| 두 순서에서 시드별 자기 도메인 최고 여부 | 시드 7개 모두 자기 도메인이 최고: legacy 최저 0.912 대 다른 자 최고 0.706, current 최저 0.977 대 다른 자 최고 0.936 | `groups.A.rulers.*.seeds.*.mean_all_conditions` | 같음 |
| 두 순서 — COCO, 초안 표 2 | legacy 자기 0.824 ± 0.076 · KITTI→COCO **0.260 ± 0.018**; current 0.921 ± 0.043 · **0.391 ± 0.064** | `groups.B.rulers.*.all_conditions_finding_unit` | 3시드, 26조건 |
| 기존 라벨 층 같은 k — 자기 도메인 | legacy 0.933 ± 0.025 · current **0.984 ± 0.004** · AIDA 안 무작위 0.607 · 전체 라벨 무작위 0.288 · 1−IoU 0.295 ± 0.006 · ObjectLab 0.329 ± 0.009 | `groups.A.rulers.matched.existing_label_layer` | A, 26조건 |
| 기존 라벨 층 — 어긋난 자 3종(약한·먼·넓은) | current 0.779 ± 0.065 · 0.827 ± 0.007 · **0.929 ± 0.018**; legacy 0.624 · 0.630 · 0.596; 전체 라벨 기준선(1차 씨앗) 0.244~0.302 | `groups.A.rulers.{shifted,far,broad}.existing_label_layer` | 7시드 |
| 기존 라벨 층 — KITTI→COCO | current 0.386 ± 0.047 · legacy 0.194 ± 0.012 · AIDA 안 무작위 0.326 · ObjectLab 0.352 ± 0.016 · 1−IoU 0.295 ± 0.012 · 무작위 0.301 | `groups.B.rulers.kitti_on_coco.existing_label_layer` | 3시드, 23조건 |
| AIDA 안 무작위 / IoU 재정렬 | 자기 도메인 0.607 / 0.498, KITTI→COCO 0.326 / 0.355 (모든 자에서 current보다 낮음) | `aida_random_expected`, `aida_iou_reorder` | finding 단위 |
| 전체 라벨 1−IoU의 동점 민감도 | 씨앗 1~10 헤드라인 평균 범위: KITTI→COCO 0.213~0.369, 넓은 자 0.248~0.313, 먼 이동 0.259~0.307, 약한 0.256~0.297, 자기 도메인 0.292~0.298, D 0.300~0.300 | `groups.*.rulers.*.tie_seed_sensitivity.existing_label_layer.all_label_iou` | label_iou = 0 동점 라벨이 상위 k를 채움 — 경계 동점 조건 A 어긋난 자 182/182, B 69/69 (`n_boundary_tie`). ObjectLab·IoU 재정렬 범위 폭 ≤ 0.004 |
| 분모 부족분(후보 < k) | 기존 라벨 층 모든 방법 0건. 누락 층 `unmatched_objectlab`만: A 19/21·19/21·21/21·19/21, B 7/9·9/9, C 3/3, D 3/3 | `groups.*.rulers.*.denominator_shortfall` | 실제 후보 수 분모 변형(후보 0건 제외): 1.000(자기 도메인)·0.832·1.000·0.577, B 자기 1.000, D 1.000 — `mean_actual_denominator`, 부록용 |
| 누락 층 ObjectLab 측정 불가 | 점수 있는 미매칭 예측 0~2% (예: A 먼 이동 10/3,758) | 원래 파일 `seeds.*.missing_layer_objectlab_scored_total` / `_unmatched_total` | cleanlab 기본 문턱 0.95. 누락 층 ObjectLab 값은 성능이 아니라 거의 빈 모집단의 결과다 |
| IoU 0 제외 변형 | (사후, 명세 밖) | `all_label_iou_excl0_posthoc` | **결론에 쓰지 않는다** |

## A3. 통제 기준선 후속 분석 — 짝지은 차이·k 민감도·+0.41 대체 자료 (2026-10-06 데스크탑, 재집계만)

**합성 주입 오류에 대한 채점이다 — 사람 판정·자연 오류가 아니다.** 설계 [followup-plan](controlled-baseline-followup-plan.md). 값은 `experiment/planning_evidence/controlled_baseline_followup_2026-10-06.json`(집계 `experiment/analyze_controlled_baseline_followup.py`)에서 읽었다. 재추론·GPU 없음. 1차 동점 씨앗 20260929, 씨앗 1~10은 따로(학습 시드와 합치지 않음). 차이는 같은 조건·같은 시드에서 내고 시드별 조건 평균 → 시드 간 평균, 조건은 재표집하지 않는다. 구간은 시드별 평균의 **탐색적** t 구간(자유도 = 시드 − 1), C·D는 단일 시드라 구간 없음. **구간이 0을 빼는 것만으로 우위를 말하지 않는다.**

| 주장 후보 | 값 | 근거 키 | 조건 |
|---|---|---|---|
| 원시 기록 완전성 | 1,023/1,023 존재, 읽기 실패·필수 필드 누락·길이/summary 불일치·finding↔라벨 ID 깨짐·ObjectLab 점수 없는 라벨 **모두 0**, 제외 0 | `controlled_baseline_followup_completeness_2026-10-06.json` → `totals`, `exclusions` | summary.json 36개의 조건별 P@10%(두 순서)와 대조 |
| 표 6 재현 | 1,023/1,023 조건의 k·조건별 값(4자리)과 8개 자의 기존 라벨 층 평균·SD가 tieseed 파일과 같음 | 같은 파일 `table6_reproduction` | 1차 동점 씨앗, 같은 k |
| A — current − ObjectLab (같은 k) | 자기 도메인 +0.655 [0.650, 0.660] · 약한 +0.477 [0.417, 0.537] · 먼 +0.547 [0.525, 0.570] · 넓은 +0.632 [0.604, 0.661] (모두 7/7 시드 양수, 조건 26/26·23/26·25/26·26/26) · COCO 자기 +0.617 [0.481, 0.754] (3/3, 23/23) · C +0.606 · D +0.709 | `A_paired_differences.<묶음/자>.aida_current_minus_all_label_objectlab.primary_tie_seed` | 기존 라벨 층(missing_* 제외), current는 finding 단위·기준선은 고유 라벨 단위(고유 라벨 단위 current와 같은 값 — `unique_label_unit_check`, 1,023/1,023 조건에서 같음) |
| A — **KITTI→COCO current − ObjectLab** | **+0.034, 탐색적 t 구간 [−0.046, 0.114]**, 양수 시드 2/3(시드별 +0.062 · +0.041 · −0.002), 양수 조건 14/23 (음수 9) | `A_paired_differences.B/kitti_on_coco.aida_current_minus_all_label_objectlab.primary_tie_seed` | ObjectLab 동점 씨앗 1~10에서 평균 폭 0 |
| A — KITTI→COCO current − 1−IoU / − 무작위 | 1−IoU +0.091 [0.004, 0.178], 3/3, 16/23 (동점 씨앗 1~10 평균 +0.017~+0.174, 양수 시드 2/3~3/3); 무작위 +0.085 [−0.031, 0.201], 3/3, 15/23 | `...aida_current_minus_all_label_iou`, `..._random_expected` | 1−IoU는 동점 규칙이 값을 정한다(표 6 주석과 같음) |
| A — 다른 자의 current − 1−IoU / − 무작위 | 1−IoU +0.507~+0.696, 무작위 +0.491~+0.697 (A·B 자기 모두 양수 시드 전부) | 같은 키 | 1−IoU 동점 씨앗 범위는 `tie_seed_sensitivity` |
| B — k 민감도, 8개 중 7개 자 | AIDA 지목 수 5·10·20·50%와 전체 라벨 1·2·5% 일곱 k 모두에서 current(고유 라벨 단위) − 세 기준선의 평균이 양수, 양수 시드 전부 | `B_k_sensitivity.<묶음/자>.paired_unique_current_minus_baseline.<f5…l5>` | 차이는 지목 50%에서 가장 작다(예: 약한 이동 − ObjectLab +0.203, 그때 ObjectLab 0.451) |
| B — **KITTI→COCO k 민감도** | current − ObjectLab: f5 +0.037 (2/3) · f10 +0.034 (2/3) · f20 +0.076 (3/3) · f50 +0.002 (1/3) · **l1 −0.022 (1/3)** · l2 +0.032 (2/3) · l5 +0.081 (3/3); current 0.308~0.392 대 ObjectLab 0.298~0.391 | 같은 키 `B/kitti_on_coco`, 값은 `unique_label_unit.<k>` | 전체 라벨 1% k에서 평균 부호가 바뀐다. 시드 3개 |
| B — 분모 부족·IoU 0 | 일곱 k 모두 기존 라벨 층 모든 방법 후보 부족 0건(전체 라벨 5%도 AIDA 지목 수 이하). k > IoU 0 라벨 수인 조건 실행: 자기 도메인 f10 134/182 · f20·f50·l5 182/182 · f5·l1·l2 0; 어긋난 자는 f50에서만(약한 178/182, 넓은 167/182, 먼 0/182); COCO 자기 f20 7/69 · f50 69/69; KITTI→COCO 모든 k 0/69; C f10 3 · f20 19 · f50 26 · l5 17 /26; D f10·f20·f50·l5 23/23 · l2 2/23 | `B_k_sensitivity.*.{finding_unit,unique_label_unit}.<k>.<방법>.n_short`, `iou0.<k>` | IoU 0 라벨은 빼지 않았다 |
| B — 지목 50%에서 legacy ≥ current | 약한 이동 0.671 대 0.654, KITTI→COCO 0.339 대 0.308, C 0.690 대 0.676 | `B_k_sensitivity.*.finding_unit.f50` | 두 순서는 같은 지목 집합 — k가 커지면 순서 차이가 줄어든다 |
| C — legacy → current, 저장된 자별 (전 조건) | @k(P@10%) 차이: 자기 도메인 +0.045 · 약한 +0.116 · 먼 +0.151 · 넓은 +0.294 · COCO 자기 +0.098 · KITTI→COCO +0.131 · C +0.018 · D −0.039. @5 차이: +0.086 · +0.321 · +0.310 · +0.573 · +0.113 · +0.141 · +0.048 · −0.039 | `C_plus041_replacement_material.<묶음/자>.diff_at_k`, `.diff_at5` | **@k와 @5는 다른 지표.** 시드 평균(A 7, B 3, C·D 1). legacy @5가 `rank_fix_seed*.json` `before["5"]`와 9/9 일치(`per_seed.*.rank_fix_before_at5_equals_legacy_at5`). 기존 +0.41의 broad 자전거 3종은 재추론에 없어 같은 5종 구성은 낼 수 없다 — **초안 +0.41은 고치지 않았다** |

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
| 합성 검증 — 미판정 처리 두 가지의 포함률·치우침 (P5, 초안 4.3 표 5) | 네 조건 × 200회, 부트스트랩 2000, θ는 5,000개 데이터셋 평균. 포함률 미판정=0 / 합집합: 기본 iou 0.985/0.990, OL 0.970/0.980; Q-A 모양 iou 0.990/0.985, OL 0.960/0.970; 오류×0.5 iou 0.970/0.975, OL 0.940/0.950; 오류×1.5 iou 0.995/1.000, OL 0.980/0.965. 치우침 전부 ±0.55 이내, 몬테카를로 SE 0~0.017, 두 구간이 다른 반복 50~88% | `experiment/planning_evidence/sim_coverage_{base,qa_like,low_error,high_error}_2026-09-29.json` → `summary` | 2026-09-29 노트북에서 파일을 직접 읽어 데스크탑 보고와 대조, 모두 일치. 합성 — 실제 값 아님 |
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
