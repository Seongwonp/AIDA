# 통제 실험 기준선 — 데스크탑 자료 목록 (2026-10-05)

[`controlled-baseline-audit.md`](controlled-baseline-audit.md) 6절 "데스크탑 인수인계"의 회신이다.

**실행한 것 없음.** 추론·학습·채점·결과 생성 스크립트를 돌리지 않았고, 기존 파일을 고치거나 옮기거나 지우지 않았다. 작업은 파일 목록·JSON 키 나열·SHA-256 계산·저장소 이력 조회뿐이다(도우미 스크립트는 저장소 밖 임시 폴더). **nuImages val은 열지 않았다.** 보호 업로드·prelim 자료는 건드리지 않았다. 조사 기준 커밋 `8464e8d`.

## 1. 비교 대상 결과 파일

| 파일 | 조건 | 자 (실행 폴더/가중치) | 시드 | limit | 과거 실행 근거 |
|---|---|---|---|---|---|
| `experiment/seeded_ruler4_7seeds.json` | `conditions_mc_cyclist_rich` 29개(clean 제외) | 자기 도메인 `runs_mc_cyclist_rich`, 약한 이동 `runs_mc`, 먼 이동(1C) `runs`, 넓은 자(800) `runs_mc_broad_n800` — 각 `clean`(시드 42)·`clean_ts{seed}` | 학습 시드 42·7·123·777·2024·2025·31337 (조건 데이터는 시드와 무관하게 하나) | 80 | 로그 `experiment/final_comparison.log`(09-04 13:11, "조건 29개 × 자 4종 × 학습 시드 7개"). 명령은 저장되지 않음 — `compare_rulers_seeded.py --limit 80 --all-conditions --rulers matched shifted far broad --seeds 42 7 123 777 2024 2025 31337 --out …`, 환경 `AIDA_CLASSES`(4클래스)·`AIDA_FRAME_SELECT=cyclist_rich`로 **추정**. 실행 시점 최신 커밋 `b4d3d0f`(미커밋 변경 여부 불명). 파일 커밋 `cb90f35`(09-05) |
| `experiment/seeded_coco_3seeds.json` | `conditions_coco` 26개 | COCO 자기 `runs_coco`, KITTI→COCO `runs` (clean·clean_ts123·clean_ts2024) | 42·123·2024 | 80 | 명령이 `experiment/run_coco_comparison.sh`에 그대로 있음(`AIDA_DATASET=coco … --rulers coco_self kitti_on_coco --seeds 42 123 2024`). 로그 `coco_comparison.log`(09-04 22:09). 직전 커밋 `3ce2b3c`(09-04 22:11) |
| `experiment/seeded_ruler_7seeds.json` | 30개(clean 포함) | 먼 이동·약한 이동 | 7시드(값 **미확인**) | 80 | 로그 `seeded_7.log`(09-04 11:45). 명령·커밋 **미확인** |
| `experiment/seeded_same_classes.json` | 29개 | broad 자전거0/중/多·약한 이동·넓은 자 | 3시드(값 **미확인**) | 80 | `score_same_classes.log`. 명령·커밋 **미확인** |
| `experiment/box_accuracy_eval.json` | `conditions` (KITTI Car) 26개 | `runs/clean` | 42 | **미확인**(파일에 없음, 기본 80 추정) | 첫 커밋 `6a21438`(08-29), 마지막 `daf2260`(08-30) |
| `experiment/box_accuracy_eval_mc.json` | `conditions_mc` 29개 | `runs_mc/clean` | 42 | **미확인**(파일에 없음, 기본 80 추정) | 08-31 |
| `experiment/box_accuracy_eval_mc_cyclist_rich*.json` (4개) | `conditions_mc_cyclist_rich` 29개 | 자기(`_mc_cyclist_rich`)·`_ruler_runs`·`_ruler_runs_mc`·`_ruler_runs_mc_broad_n800` | 42만 | **미확인**(파일에 없음) | 로그 `matched.log`·`far.log` 등, 커밋 `29af3f7`·`6fe85ce`(09-03) |
| `experiment/box_accuracy_eval_mc_ruler_self.json` | `conditions_mc` 29개 | 조건별 self 가중치(`runs_mc/<조건>`) | 42 | **미확인**(파일에 없음, 기본 80 추정) | 커밋 `f377f4f`(09-02) |

`seeded_*`의 자별 값은 시드마다 `{precision, top10, top10_noswap, n_conditions, per_condition, silent}`(`seeded_same_classes`는 `per_condition_fit` 추가). `per_condition`은 조건→P@10% 숫자 하나다. `box_accuracy_eval*`의 `per_condition` 행은 `condition, type, predicted_dominant, magnitude, injected, flagged, tp, fp, caught, fn, precision, recall, f1, type_accuracy, present_types`.

## 2. 상세 캐시·진단 JSON·예측 캐시

| 종류 | 파일 수 | 최상위 키 | 행 필드 | 행 수 |
|---|---|---|---|---|
| `experiment/box_accuracy_verdicts*.json` (gitignore) | 7 | 조건 이름 | 조건 행: `box_accuracy_eval` 행 필드 + `verdicts_by_rank`. verdict 한 건 = 7-튜플 `(correct, suspicion, severity, is_dominant, raw_signal, confidence, class_id)` | 무태그 1조건/149, `_mc` 29/4570, `_mc_cyclist_rich` 29/5676, `_ruler_runs` 29/3925, `_ruler_runs_mc` 29/6065, `_ruler_runs_mc_broad_n800` 29/5598, `_mc_ruler_self` 29/3622 |
| 기타 루트 결과 JSON (`rank_fix_*`, `consensus_*`, `geom_*`, `cswap_*`, `relfb_*`, `conf*_*`, `fit_*`, `survivor_*` 등) | 약 90 | `seed, kinds, ks, rows` 등 | 집계값만. 이미지·라벨 인덱스·박스·IoU 키 없음(재귀 검색). `conf*`의 `predictions`는 개수 필드 | 리스트 최대 길이 ≤29 |
| 진단 population 출력 | **0** | — | — | — |
| 예측(prediction) 캐시 | **0** | — | — | — |
| `conditions*/…/labels/{train,val}.cache` | 116 | — | ultralytics **라벨** 캐시(예측 아님) | — |

- verdict 캐시의 행 수는 각 `box_accuracy_eval*.json`의 `tp+fp`와 29조건 모두 일치한다. 예외: **무태그 `box_accuracy_verdicts.json`은 1조건뿐**이고 `box_accuracy_eval.json`은 26조건이다 — 나중의 부분 실행이 캐시를 덮어쓴 것으로 보인다. KITTI Car 26조건 상세는 없다.
- verdict 캐시는 **시드 42 단일 실행**이다. `_tag()`에 시드가 없으므로 7시드·3시드 실행(`compare_rulers_seeded.measure` → `score_condition`)은 캐시를 남기지 않았다.
- 무태그를 뺀 verdict 캐시 6개의 mtime이 모두 2026-09-03 10:07로 같다(대응 eval JSON은 08:37~09:37). 원인은 확인하지 못했다.
- `experiment/runs_nuimages/*/ruler_manifest.json` 2개는 nuImages 자 기록이라 이 비교와 무관하다.

## 3. 실제로 있는 필드

| 필드 | seeded JSON | box_accuracy_eval | verdict 캐시 | injection_record | 조건 라벨 파일 |
|---|---|---|---|---|---|
| 이미지 ID | 없음 | 없음 | **없음** | 있음(파일 stem 키) | 있음(파일명) |
| 라벨 인덱스 | 없음 | 없음 | **없음** | 있음(`errored`) | 있음(줄 순서) |
| 박스 좌표 | 없음 | 없음 | **없음** | `dropped`만(정규화 cx,cy,w,h) | 있음 |
| 예측 클래스 | 없음 | 없음 | `class_id` — 기존 라벨 후보는 라벨 클래스(`label_diagnosis.py:878`), 1C 자는 None | — | 라벨 클래스 |
| 신뢰도 | 없음 | 없음 | 있음(finding confidence) | — | — |
| 라벨 IoU | 없음 | 없음 | **없음**(`raw_signal`은 유형별 신호, IoU로 간주 불가) | — | — |
| 주입 정답 | 없음 | 조건 합계(`injected, tp, caught`) | finding별 `correct`만 | 있음(라벨 단위) | — |
| 전체 예측(박스·클래스·신뢰도) | 없음 | 없음 | 없음 | — | — |

## 4. 조건 폴더와 injection_record

| 묶음 | 조건 폴더 | record 있음 | record 없는 폴더 | 이미지=라벨 수 | 표본 대조 |
|---|---|---|---|---|---|
| `conditions` (KITTI Car) | 27 | 27 | — | 400=400 | 0 불일치 |
| `conditions_e123`, `_e2024` | 27씩 | 27씩 | — | 400 | 0 |
| `conditions_coco` | 41 | 41 | — | 400 | 0 |
| `conditions_mc` | 42 | 30 | 12(`scale_m30_asis`, `_fix_*` 6, `_refined*` 3 등 실험 파생) | 일치 | 0 |
| `conditions_mc_cyclist_rich` | 38 | 38 | — | 400 | 0 |
| `conditions_mc_e123`, `_e2024` | 30씩 | 30씩 | — | 400 | 0 |
| `conditions_mc_nested*`, `conditions_nested*`, `conditions_mc_all_local_n800` | 29~39 | 27~30 | `*_refined*` 파생만 | 일치 | 0 |
| `conditions_mc_broad_*`, `_cyclist_rich_e*` | 1(clean) | 1(빈 record) | — | 일치 | — |
| `conditions_obb*` | 5씩 | **0** | 전부 | 400 | — |

record 항목 키는 `errored`, `dropped`. 모든 record 키가 해당 `labels/train` stem에 있었다(불일치 0). 표본 대조는 조건마다 오류 이미지 20장을 뽑아 `errored` 인덱스가 라벨 줄 수 범위 안인지 본 것이다(예: `conditions_mc_cyclist_rich/width_m30` 58건, `duplicate_30` 55건, 불일치 0). 좌표·클래스 내용 대조는 하지 않았다. 통제 비교에 쓰는 조건(rot·width·…·class_swap·missing·duplicate)은 모두 record가 있다.

## 5. 가중치

`weights/best.pt` 개수와 clean 자 SHA-256(전체 64자). `args.yaml`의 `seed`가 폴더 시드와 모두 일치했다.

| 실행 폴더 | best.pt | self 조건 가중치 |
|---|---|---|
| `runs` | 33 | 조건 27개 전부 |
| `runs_e123`, `runs_e2024` | 27씩 | 27개 전부 |
| `runs_mc` | 62 | 42개 전부 |
| `runs_mc_e123`, `runs_mc_e2024` | 30씩 | 30개 전부 |
| `runs_mc_cyclist_rich` | 16 | **대표 9조건만**(width_m30, height_m30, rot_m15, trans_x_m15, trans_y_m15, scale_m30, missing_30, duplicate_30, class_swap_30). 나머지 20조건 없음 |
| `runs_coco` | 7 | **없음**(clean 7시드만) |
| `runs_mc_broad_n800` | 7 | clean만 |
| `runs_mc_broad_{poor,mid,rich}` | 3씩 | clean만 |
| `runs_mc_nested*`, `runs_nested*`, `runs_mc_all_local_n800` | 4~12 | 일부(`*_refined` 계열) |
| `runs_obb*` | 5씩 | 5개 |

clean 자 해시 — 7시드 비교에 필요한 것:

| 폴더 | clean(42) | ts7 | ts123 | ts777 | ts2024 | ts2025 | ts31337 |
|---|---|---|---|---|---|---|---|
| `runs_mc_cyclist_rich` | `32510de3f2da46c42d63adeaff3aa724bb4dae64bff7c104330e3b4b10a57587` | `3ed2d2c2da8d31daa11d1e6524cee3c443dbfb01c15bba93678001e023e13ae1` | `ceaf1bb817e7afb34542814a4fb1dc7be6d3dde503dd20b3392ae04138f525e9` | `33217cd96e04a51ded51bd96377963c78794e5db8d26db3f83643818f6b4eaf5` | `a3ba0e1aaaf5bf6c6e050031088c06f2922d55f4d5e02259e925556a56eb4551` | `69e9fffe1d0db8d3710f245df908b5874513f4c5fab49ed63979102bfb51331b` | `52ee23f0bd7b19a41b9bcc72dc936facec249bafbc2bb0666e3be94cdaed6ec5` |
| `runs_mc` | `ec591bfc2538764e649ffc8ab79b50929309a78f866413f67f8be16f09ed7f6f` | `1c1d3ec78b34a5e99b37f9eae60d5afae05d8d77480e8df91e4cee9efb181577` | `2165428c6392fb434a120422bd8d58846d35008691596019026e5bf7fb7e8e60` | `ed5973cd74a21b914ed8c890e46f3e7ca176d8080693ffd62925a61ab4ce419d` | `cb2693d2399026741a5b87cc7e0ae3d13c83cf76c61653e71fb3623b2772ad5b` | `05a19b3d2f11318154649f286289e46c42bca3b789bef8496ff3947bbab45d9b` | `e13678ae99438eadb8925b5b4f5754bf2a7a08bfced385de3bebcb869856fa21` |
| `runs` | `4e998fa7a6dfddae76309f962e8468f898d3f5da5b0f471de330afab44129691` | `7821f0d285059c845fb76b4496771db4ac959d9b3c647edd1fb583e9b2403870` | `1043327cde53c390a5acadabfad612458b9f7abb2d9a170a0ae93e9dbcb14e0f` | `d23eec044c17bab10c5154fdd5c8f3a4dc34aa026b576b2c27f23db345e7df3e` | `0b72d048f3a9f02d1f2e847842b28aeaf814395b6cffae6af6a4d7517ca09127` | `9462a142f601c044dc7d8478472de5182ac777a29e6f04e276e322eb41c32d87` | `b6a10db536b27b77ff67d83d3fdf1a063f7fc30fb87826fd95cfd6773fa5a8ee` |
| `runs_mc_broad_n800` | `f6abe0f07050510316e3523a520b795fa467f8c942b3df27e70a9aad34022c24` | `5f28894b3e298d701289207e726bb728b75a5ef46409d449f613df62ffe1f5e7` | `3d8512f94b7e2b4b80c42dc51c85ded369a186a1a6d6fbb3f3e2faccffb7f589` | `67555d4edf7b429b8ad967b968d90a8d7aea5d166950f155c45a8fea04e0275b` | `3eee98199c22ec164ae86c5726b6087c9c981dd34c7f8e14a738545fd45cb07a` | `98091c7f2e2d2d7165d0aae653a84f8adf3de803acef5957ff7e764c4a6c39c7` | `ff7a5563c72576e93d2f8329ba1e7cd34d9d80cc170ecc3fa5a20cfa3bbe265c` |
| `runs_coco` | `8ce4684b0e46faecd071c58aa6c1d454909ab62482593e454ce7eb3313ecd5b6` | `bc1b23b3e473c29f3f35c700326e496f5d637b86d229cdbc4657c52713d429cc` | `449388eec4828682ab4d90f0a5836437b2fae928ff2520a925223f2b6c2a2e07` | `8b9abb695dc36bfb0fa734c3fe59352423ae97ce8ebf8c0be48a7e595a31e0c0` | `678f80a73d695b0dd50ee59f6b7ef875b779e2ad21fe05197cdbe1b05df37071` | `6c74bfce20874ffc353d94d99097b3d8df6da3a77d0fa82a5b981cc613ab18e0` | `015b7aec9544f314e8f9e06fb5a23ddc36ff56cbcb2087d6a9a964442cb42911` |

그 밖의 clean 자(시드 42; broad 3종은 ts123·ts2024 포함):

| 폴더 / 실행 | SHA-256 |
|---|---|
| `runs_e123/clean` | `0e6577db443a8a43ac6f40080ac9c37075412641655d49df0d1c9610b7fa0d6c` |
| `runs_e2024/clean` | `b261f15b74866ec68df732a2e624e17d23587c1dfa2c23351056914be79b02c8` |
| `runs_mc_e123/clean` | `49b92335657835e255fdb150ab9e441f2a96ce5512cbdf443076ddf140e8f1b3` |
| `runs_mc_e2024/clean` | `3bacfcd631d6f3288877785f45aa11a18f1044de4a1138ce12bb1178ca8908ff` |
| `runs_mc/clean_asis` | `d4e7cda2e1d0305823840d7aef45344020c482c3380b26fce581035cb07215f6` |
| `runs_mc/clean_sub200` | `6f6743f04834302455263716521d690a804b247064aa521965effef43f875346` |
| `runs_mc_cyclist_rich_e123/clean` | `df659df0606fa97de5fcc9504c32ae61c410310507748cc5dcc1c07275637459` |
| `runs_mc_cyclist_rich_e2024/clean` | `85357747e0b9900c9a498181fb2c3dbac5e1748abff5bf142cb01f5f6bdb605f` |

broad 3종(clean · ts123 · ts2024): poor `1817b4785aabde21583b6f6ece25b54185e4fc4600b8caf53dbec058e35e13dd` · `c1115e0ce5f55fd25fbce3b7258288b94bff66efd8fdffde7d74f7fa24c5f8e7` · `80180764fbe3b451ce3c11d319ee4499e100323edadc65ba5ac632727178860e`; mid `a2baed5e4a19422b16a8e674542515516101c02b1a20bb5724e21cd3ab1516a8` · `baecf50e6332ac8a881ecea6ea8718994c5298dc5269c722d4359fec41dac69c` · `1a55335fac3d41bda724e5e1787a510f1a518f7a497635383e63915f1f21f57d`; rich `e6ded1e454c6151258e924e089ee0939ca95d4a9c94f2a7e76d94dcaea5870d8` · `61dcff19a00b111db109a588778d8bc81431fa6f66372bf4bd2aaf1d6e443172` · `7625fa8bfab288337e828fcc4e667092f60514731438e329fd869368e07284d1`.

self 조건 가중치 62개(`runs_mc` 53, `runs_mc_cyclist_rich` 9)의 SHA-256은 `experiment/planning_evidence/controlled_baseline_self_weights_sha256_2026-10-05.json`에 따로 적었다(2026-10-05 검토 반영).

nested·sub 계열 clean 자(`runs_mc_nested*/clean_sub*`, `runs_nested*/clean_sub*`, `runs_mc_all_local_n800/clean*`)도 전부 best.pt가 있다. 해시는 조사 출력에 있으나 이 비교에 직접 쓰이지 않아 싣지 않는다.

## 6. 감사 4절 비교별 분류

재추론 비용 가정: RTX 3050에서 약 29~31장/초 — 근거는 2026-09-29 연습 묶음 진단(620장, ObjectLab 포함 21.5초, `experiment/planning_evidence/practice1_bundle_2026-09-29.json`). limit 80이면 실행 1건 = 80장. 실행마다 모델 적재·적합도 계산의 고정 비용(측정 안 함, **2~5초로 가정**)을 실행 수만큼 더한다.

| 비교 | 분류 | 입력 출처 | 결정적인 누락 필드 | 재추론 규모 |
|---|---|---|---|---|
| 기존 집계 재확인 | **캐시로 계산** | `seeded_*.json`의 `per_condition`·`top10`(추적 파일) | 없음(과거 명령은 ruler4가 추정) | 0 |
| AIDA finding 안 무작위 — 시드 42, 자 4종(cyclist_rich)·`_mc`·self | **캐시로 계산** | verdict 캐시 `correct`·finding 수 | 없음. 단, 이 캐시는 seeded 시드 42 실행과 같은 실행이 아니다(7절 2) | 0 |
| AIDA finding 안 무작위 — 7시드·COCO 3시드 | **기존 가중치 재추론** | seeded JSON에는 조건별 TP·finding 수가 없음 | 조건·자·시드별 `tp`, `flagged` | 아래 A·B |
| AIDA finding 안 무작위 — KITTI Car 26조건 | **기존 가중치 재추론** (또는 eval JSON의 조건별 `tp/flagged`로 기대값만) | 무태그 verdict 캐시가 1조건뿐 | finding별 `correct` | D |
| AIDA 후보 안 IoU 재정렬 | **기존 가중치 재추론** | verdict 캐시 | 이미지 ID, 라벨 인덱스, `label_iou` | A·B(+C·D) |
| 전체 기존 라벨 무작위·IoU | **기존 가중치 재추론** (정답 자료는 존재 — 좌표·클래스 정합은 미검증) | 정답: `injection_record` + 조건 라벨 파일(stem 일치·표본 인덱스 범위만 확인) | 전체 라벨의 `label_iou`(예측 필요) | A·B(+C·D), `collect_population=True` 경로 |
| ObjectLab 박스 적응 | **기존 가중치 재추론** | 라벨 박스·클래스는 라벨 파일에 있음 | 예측 박스·클래스·신뢰도 전체 | 위와 같은 실행에서 함께 |
| 누락 층 | **기존 가중치 재추론** + 명세 먼저 | `dropped` 좌표는 record에 있음 | 미매칭 예측 모집단 | 위와 같은 실행 |
| self 비교 (`conditions_mc` 29조건) | **기존 가중치 재추론** | `runs_mc/<조건>` 전부 있음 | 위와 같음 | C |
| self 비교 (`conditions_mc_cyclist_rich`) | 대표 9조건: **기존 가중치 재추론** / 나머지 20조건: **재학습 검토** | `runs_mc_cyclist_rich` self 9개만 | 20조건 self 가중치 | 9×80=720장 |
| COCO self(오류 조건으로 학습한 자) | **재학습 검토** (필요할 때만) | `runs_coco`에 clean만 | 조건별 가중치 | — |

재추론 규모:

| 묶음 | 실행 수 | 이미지 | 순수 추론 | 고정 비용 포함 |
|---|---|---|---|---|
| A. 4클래스 자 4종 × 7시드 × 29조건 | 812 | 64,960 | 약 35분 | 약 62~103분 |
| B. COCO 자 2종 × 3시드 × 26조건 | 156 | 12,480 | 약 7분 | 약 12~20분 |
| C. self `conditions_mc` 29조건 | 29 | 2,320 | 약 1.3분 | 약 2.5~4분 |
| D. KITTI Car `runs/clean` 26조건 | 26 | 2,080 | 약 1.1분 | 약 2~3분 |
| 합계 | 1,023 | 81,840 | 약 44분 | **약 79~130분(1.3~2.2시간)** |

필요한 clean 자 가중치는 A·B·D 모두 존재한다. 재학습이 필요한 비교는 cyclist_rich 20조건 self와 COCO self뿐이며 논문 표에 넣을지부터 정해야 한다.

## 7. 확인한 것과 새로 드러난 점

### 7.1 감사 5절 1번 — 코드 위치

- 새 추론: `experiment/evaluate_box_accuracy.py:160-161`에서 `review_order(findings, summary)`를 부르고, `experiment/label_diagnosis.py:407-408`이
  `sorted(findings, key=lambda f: (f.suspicion not in present, -f.severity))`로 정렬한다.
- 캐시 재사용: `experiment/evaluate_box_accuracy.py:279-284`의 `order(x)`가 `CLASS_WEIGHTED`가 아니면 `return -x[2]`(= `-severity`)로 정렬한다.

코드 경로 차이는 사실이다. 다만 `review_order`는 커밋 `2f46365`(2026-09-06)에서 들어왔다. **위 1절의 결과 파일은 모두 09-02~09-04 생성**이라 그 당시 새 추론도 심각도 순이었을 가능성이 크다. 따라서 이 불일치는 "과거 수치가 어느 경로로 나왔나"보다 **"지금 코드로 다시 돌리면 과거 수치가 재현되지 않을 수 있다"**는 문제다. 재추론 전에 과거 순서 규칙을 재현 모드로 둘지 정해야 한다.

### 7.2 그 밖의 발견

1. **verdict 캐시의 저장 순서는 심각도 순이다.** cyclist_rich 4개와 self 캐시는 29조건 모두 `-severity` 비증가 순이고, `review_order` 키로도 정렬된 조건은 0~14개뿐이다. `_mc` 캐시는 어느 순서도 아니다(클래스 가중 정렬 실행으로 추정, 미확인).
2. **캐시는 seeded 시드 42 값을 재현하지 않는다.** 같은 자·조건(cyclist_rich, 시드 42)에서 캐시로 다시 구한 조건별 P@10%가 seeded 파일과 일치한 조건: 자기 도메인 22/29, 약한 이동 7/29, 먼 이동 3/29, 넓은 자 7/29. 차이는 대부분 +0.1~+0.3, `missing_30`에서 −0.5~−0.77. 두 실행은 하루 차이(09-03 → 09-04)이고 그 사이 순위 코드 커밋은 확인되지 않아 원인 미상이다. 캐시의 eval JSON P@10%는 캐시와 정확히 같다.
3. 무태그 `box_accuracy_verdicts.json`은 1조건만 남아 있다(eval JSON은 26조건).
4. 예측 캐시·population 출력은 디스크에 하나도 없다. 박스 단위 기준선은 모두 재추론이 필요하다.
5. 조건 데이터·injection_record·clean 자 가중치는 필요한 범위에서 모두 남아 있어 **현재 확인 범위에서는** 자료 복구가 필요한 비교가 없다. 라벨 좌표·클래스와 record의 전수 정합은 확인하지 않았다 — 재추론 첫 실행 전에 조건 하나로 전수 대조한다.

## 외부 검토 (2026-10-05)

Copilot CLI(읽기 전용)로 인용·산술·분류를 검토받았다. file:line 인용 4곳과 실행·이미지 수 산술은 맞았다. 지적 4건을 반영했다 — 시간 추정을 가정에서 직접 계산(1.5~2.5시간 → 1.3~2.2시간), 속도 근거 명시, 정답 자료의 '복구 불필요'를 확인 범위로 낮춤, 확인 못 한 시드·limit·명령을 '미확인'으로 표기, self 가중치 해시를 별도 파일로 추가.

## 8. 다음

노트북 2단계(기준선 명세)에서 정할 것: 과거 순서 규칙 재현 여부(7.1), 7.2-2의 차이를 재추론 첫 실행으로 먼저 확인할지, self 20조건·COCO self를 범위에 넣을지. 재추론은 위 규모를 사용자에게 제시하고 승인받은 뒤 실행한다.
