# 통제 실험 기준선 — 명세 (2026-10-06)

[감사](controlled-baseline-audit.md) 5절과 [데스크탑 목록](controlled-baseline-desktop-inventory.md) 6~8절을 받아 정한 것이다. 사용자가 승인한 계획 범위는 순서 버전 2개, 모집단 수집 옵션, 합성 검사, 1단계 재현 확인까지다. **2단계(전체 재추론)는 별도 승인 전 실행하지 않는다.**

## 1. 순서 버전

순서가 다르면 다른 버전 ID다. 코드: `experiment/evaluate_box_accuracy.py`의 `ORDERINGS`, `order_for_scoring`.

| ID | 승격(rescore) | 정렬 | 쓰는 곳 |
|---|---|---|---|
| `legacy_severity_v0` | 절대 문턱(ratio ≥ 0.12)으로 고른 유형만 — 09-06 상대 문턱 물러남(`ba937f9c`) 이전 | `-severity` 안정 정렬 | 09-02~09-04 결과 파일 재현표 |
| `review_order_v1` | `present_types`(상대 문턱 포함) | `(계통 유형 아님, -severity)` 안정 정렬(`2f46365`, 09-06) | 현재 제품 순서와의 대조 |

- 기본 동작은 바뀌지 않는다. `score_condition`·`score_findings`에 `ordering`을 주지 않으면 예전 그대로이고(새 추론 = review_order, `--reuse-cache` = `-severity`), 행에 `ordering` 키도 붙지 않는다. 이름을 주면 행에 `ordering`이 남는다. `compare_rulers_seeded.py --ordering`도 같다(출력 JSON에 `ordering` 기록).
- **심각도 상수 집합도 버전의 일부다.** 다중 클래스 verdict 캐시 6개와 `box_accuracy_eval_mc*.json`은 `AIDA_RELIABILITY_PROFILE=reliability_profile_mc.json`으로, `seeded_ruler4_7seeds.json`·`seeded_coco_3seeds.json`은 프로파일 없이(기본 상수) 만들어졌다(아래 4절). 재현표는 기본 상수, 프로파일 없음으로 돌린다.

## 2. 표에 넣는 비교

| 묶음 | 자 | 시드 | 조건 | 비고 |
|---|---|---|---|---|
| clean 자 4종 | 자기 도메인·약한 이동·먼 이동(1C)·넓은 자(800) | 42·7·123·777·2024·2025·31337 | `conditions_mc_cyclist_rich` 29 | 812회. `AIDA_CLASSES=Car,Van,Pedestrian,Cyclist`, `AIDA_FRAME_SELECT=cyclist_rich` |
| COCO | COCO 자기(1C)·KITTI→COCO(1C) | 42·123·2024 | `conditions_coco` 26 | 156회. `AIDA_DATASET=coco`(`run_coco_comparison.sh`) |
| self | 조건별 self 가중치(`runs_mc/<조건>`) | 42 | `conditions_mc` 29 | 29회. 재현 대상은 `box_accuracy_eval_mc_ruler_self.json`(프로파일 사용 — 4절) |

**제외(한계로 적는다):** cyclist_rich self 20조건(가중치는 대표 9조건만 있음)과 COCO self(조건별 가중치 없음). 둘 다 재학습이 필요하다. KITTI Car 26조건(`runs/clean`)은 표의 필수 묶음이 아니다.

## 3. 측정 규칙

- **공통 예산 k:** 조건마다 하나로 고정한다. 재현표는 기존 정의(AIDA finding 수 × 10% 내림, 최소 1)를 그대로 쓴다. 전체 라벨 기준선(무작위·`1 − label_iou`·ObjectLab)과 견줄 때는 그 조건의 같은 k를 모든 방법에 쓰고, 방법별 후보 수에서 따로 산출하지 않는다. 후보가 k보다 적으면 있는 만큼만 보고 분모는 k로 둔다(부족분은 미검출) — **제안, 사용자 확인 전**. 결과 표에 같이 적는다.
- **동점:** 순서 버전은 모두 안정 정렬이다. 동점은 진단이 낸 순서(이미지 파일 이름 순 → 이미지 안 진단 순)를 따른다. 전체 라벨 기준선의 동점은 (이미지 이름, 라벨 인덱스) 순으로 고정하고 무작위 기준선은 고정 씨앗으로 한다(**제안** — 구현 전 확인).
- **단위:** 재현표는 기존과 같은 **finding 단위**(같은 라벨의 여러 유형·중복 쌍 모두 계수)를 유지한다. **고유 라벨 단위**는 이름을 달리한 별도 지표로만 내고 재현값과 섞지 않는다.
- **누락 층:** 기존 라벨 층과 합치지 않는다. 미매칭 예측 모집단(`matches_dropped`, IoU ≥ 0.4)은 별도 층·별도 예산으로 보고한다.
- **빈 조건:** finding 0건은 `silent`로 평균에서 뺀다(`compare_rulers_seeded.measure`와 같음). 다른 분모를 쓰는 산출물과 평균을 같은 것으로 읽지 않는다.
- **모집단 수집:** `score_condition(..., collect_population=True)`가 행에 `population`(전체 라벨 + `label_iou` + `injected_error`, 미매칭 예측 + `confidence` + `matches_dropped`, cleanlab이 있으면 ObjectLab 점수)을 붙인다. 기본은 꺼짐이고 꺼져 있으면 행이 예전과 같다.

## 4. 1단계 재현 확인 — 결과 (2026-10-06)

자기 도메인 자 `runs_mc_cyclist_rich/clean`(시드 42, SHA-256 앞 12자 `32510de3f2da` — 목록 5절과 같음), 29조건, limit 80, 4클래스·cyclist_rich, 프로파일 없음. 추론 1회로 두 순서 모두 채점(90.6초, ultralytics 8.4.90, torch 2.12.1+cu126). 근거: `experiment/planning_evidence/controlled_baseline_stage1_repro_2026-10-06.json`.

| 대조 | 29조건 중 P@10% 정확히 일치 | 평균 P@10% |
|---|---|---|
| `legacy_severity_v0` 재실행 vs seeded 시드 42 | **29** | 0.9709 = 0.9709 |
| `review_order_v1` 재실행 vs seeded | 23 | 0.9886 |
| 재실행 vs verdict 캐시(저장 순서) | legacy 22 · current 18 | 캐시 0.9241 |
| 캐시 vs seeded | 22 | — |

- 지목 수·TP는 재실행과 캐시가 29조건 모두 같다 — 추론·이미지 선택·클래스 매핑·문턱 차이는 없다.
- `review_order_v1`만 다른 6조건: width_m15·width_p15·height_m30·height_m15·height_p15·trans_y_m15(모두 current가 높음).
- **목록 7.2-2(캐시가 seeded를 재현 못 함)의 원인:** 캐시의 저장 심각도는 `reliability_profile_mc.json`으로 다시 계산하면 29/29 조건에서 정확히 재현되고, 기본 상수로는 0/29다. 캐시를 기본 상수로 다시 매기면(`load_cached_rows`, GPU 없음) P@10%가 seeded와 29/29 일치한다. 즉 순서·추론이 아니라 **심각도 상수 집합(신뢰도 프로파일)** 차이다. 같은 검사에서 다중 클래스 캐시 6개 모두 프로파일로 만들어졌다.

## 5. 2단계 관문

2단계(1,023회 재추론, 약 1.3~2.2시간 + `collect_population` ObjectLab 비용)는 **1단계가 재현될 때만** 하며, 사용자 승인을 따로 받는다. 1단계는 자기 도메인 자·시드 42에서 재현됐다. 2단계 시작 조건:

1. `AIDA_RELIABILITY_PROFILE`·`AIDA_RULER_WEIGHTS`를 비운 상태를 실행 기록에 남긴다. self 묶음을 기존 eval JSON과 대조할 때만 프로파일 사용 여부를 따로 정한다.
2. 첫 묶음에서 1C 자(먼 이동)·넓은 자 시드 하나씩을 seeded 값과 먼저 대조한다(이번 확인은 4클래스 자기 도메인 자뿐).
3. 출력은 새 파일 이름으로만 쓰고 기존 결과·캐시를 덮지 않는다.

## 검토 반영 (2026-10-06, Copilot CLI 읽기 전용 검토)

- 기본 경로(`ordering=None`, `collect_population=False`)가 바뀌지 않았고 `legacy_severity_v0`가 절대 문턱 승격 + 안정 `-severity` 정렬이라는 점은 문제 없음으로 확인됐다.
- **반영:** `evaluate_box_accuracy.py` CLI에 `--ordering`을 더했다. `--reuse-cache`와 함께 주면 거부한다(캐시 경로는 캐시의 `present_types`로만 다시 매기므로 순서 버전이 조용히 섞이지 않게).
- **알려진 한계:** 모집단의 미매칭 예측 상자는 `unmatched_prediction_rows`가 소수점 1자리로 반올림해 저장하고, 누락 채점은 원본 좌표를 쓴다. IoU가 0.4 경계에 아주 가까운 예측은 `matches_dropped`와 채점 TP/FP가 다를 수 있다. 누락 층 기준선을 계산할 때 이 불일치 건수를 함께 적는다.
