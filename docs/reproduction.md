# 재현 안내 — 무엇이 저장소에 있고 무엇이 없는가

> docs/24 A2. [current-evidence.md](./current-evidence.md)가 "어느 파일이 그
> 주장을 뒷받침하는가"라면, 이 문서는 **"그 파일을 어떻게 다시 만드는가"**다.
>
> **복원할 수 없는 것은 추정해 채우지 않고 누락으로 표시한다**(docs/24 표기 규칙).

**2026-09-08 확인.** 환경 값은 실제로 실행해 읽은 것이다.

## 저장소에 있는 것과 없는 것

| | 저장소 | 크기 | 비고 |
|---|---|---|---|
| 코드·문서·검사 | **있음** | — | 백엔드 150건, 프론트 24건 |
| 결과 JSON | **있음** | 101개 | `experiment/*.json` |
| 지표 CSV | **있음** | — | `backend/app/data/*.csv` |
| **학습 가중치** | **없음** | 폴더 26개 · `best.pt` **319개** | `.gitignore:30` `experiment/runs/` |
| **조건 폴더** | **없음** | 폴더 1155개 · 파일 약 147만 개 | `.gitignore:20` `experiment/conditions/` |
| **원본 이미지** | **없음** | — | `experiment/data/` |

**결론이 담긴 파일은 저장소에 있고, 그것을 만든 재료는 없다.** 재료는 아래
명령으로 다시 만든다.

## 환경 (실측)

| | 값 |
|---|---|
| OS | Windows 11 |
| GPU | NVIDIA GeForce RTX 3050 (6GB) |
| Python | 3.14.0 |
| torch | 2.12.1+cu126 (CUDA 사용 가능) |
| ultralytics | 8.4.90 |
| 가상환경 | **둘이다** — `backend/venv`(FastAPI·pytest), `experiment/venv`(torch·ultralytics) |

`experiment/venv`에는 FastAPI가 없고 `backend/venv`에는 torch가 없다. 명령마다
어느 쪽인지 아래에 적었다.

## 기본 설정값

| 환경변수 | 기본값 | 뜻 |
|---|---|---|
| `AIDA_SEED` | 42 | **프레임 분할** 시드 |
| `AIDA_ERROR_SEED` | `AIDA_SEED` | 오류 주입 시드 |
| `AIDA_TRAIN_SEED` | — | 학습 시드(`AIDA_RUN_SUFFIX`와 짝) |
| `AIDA_EPOCHS` | 50 | |
| `AIDA_BATCH_SIZE` | 16 | |
| `AIDA_IMG_SIZE` | 640 | |
| `AIDA_N_TRAIN` / `AIDA_N_VAL` | 400 / 120 | |
| `AIDA_CLASSES` | Car | 4클래스는 `Car,Van,Pedestrian,Cyclist` |
| `AIDA_DATASET` | kitti | `coco`도 가능 |
| `AIDA_FRAME_SELECT` | random | `cyclist_rich` · `broad` · `nested` |
| `AIDA_ERROR_RATIO` | 0.3 | **주의: 조건 폴더 이름이 안 바뀌어 기존 조건을 덮어쓴다**(docs/21 AX) |

전체 목록은 `experiment/.env.example`과 README의 환경변수 표에 있다.

### 분할 목록 파일이 없는 이유

프레임 분할은 `AIDA_SEED`로 **결정론적**이다(`data_loader.py` — 프레임 id를
정렬한 뒤 `random.Random(SEED)`로 섞는다). 그래서 목록을 따로 저장하지 않아도
같은 시드로 같은 분할이 나온다. **다만 원본 데이터가 바뀌면 달라진다** —
KITTI·COCO는 고정된 공개 데이터라 실질적으로 안 바뀐다.

### 경로 이름 규칙

산출물 경로에 실험 설정이 접미사로 붙는다. **순서가 정해져 있다** —
클래스 구성 → 데이터셋 → 프레임 선택 → 규모.

```
conditions_mc_nested_n800   4클래스 · 중첩 부분집합 · 학습 800장
runs_mc_broad_n800          같은 설정의 학습 결과
metrics_mc_nested_n800.csv  같은 설정의 지표
```

이 순서가 어긋나면 **없는 파일을 찾거나, 더 나쁘게는 다른 실험의 수치를
읽는다.** 검사기(`check_consistency.py`)가 이 규칙을 확인한다.

## 처음부터 다시 만들기

```bash
# 1. 데이터 (외부에서 받는다)
cd experiment
./venv/Scripts/python.exe download_kitti.py      # 라벨 전체 + 필요한 이미지만 Range 요청
AIDA_DATASET=coco ./venv/Scripts/python.exe download_coco.py

# 2. 조건 폴더 (오류 주입)
./venv/Scripts/python.exe error_injector.py                  # 실행 순서의 조건 전부
./venv/Scripts/python.exe error_injector.py missing_5 width_m30_r05   # 이름으로 골라서

# 3. 학습
./venv/Scripts/python.exe train.py --condition clean
AIDA_TRAIN_SEED=123 AIDA_RUN_SUFFIX=_ts123 ./venv/Scripts/python.exe train.py --condition clean

# 4. 평가
./venv/Scripts/python.exe evaluate.py --condition clean
./venv/Scripts/python.exe evaluate_box_accuracy.py --limit 80
./venv/Scripts/python.exe evaluate_label_diagnosis.py --limit 80
```

**외부 데이터 출처.** KITTI Object Detection 2D(`cvlibs.net/datasets/kitti`),
COCO val2017. 둘 다 등록 없이 받히고 HTTP Range 요청을 지원해 **필요한 이미지만**
내려받는다(KITTI 이미지 zip 전체는 12.5GB).

## 주장별 재현 명령

[current-evidence.md](./current-evidence.md)의 번호와 같다.

| 주장 | 명령 |
|---|---|
| 1. 유형 판별 92.6% | `evaluate_label_diagnosis.py --limit 80` |
| 2. 상위 10% 99.7% | `evaluate_box_accuracy.py --limit 80` |
| 3. 자 4종 비교 | `compare_rulers_seeded.py --out seeded_ruler4_7seeds.json` |
| 4. 도메인 이동 | 같은 스크립트, `AIDA_DATASET=coco` |
| 5. 순서 처방(AN) | `rank_systematic_first.py` |
| 6. 자기 정제 | `compare_keep_ratio.py` (지표 CSV만 읽는다 — GPU 불필요) |
| 7. 바닥 식 | `analyze_relthr_conditions.py` · `analyze_intensity.py` · `measure_type_ratio.py` |
| 8. 신뢰도 바닥 | `confidence_floor.py --floors 0.10 0.15 0.25 0.40` |

**6번은 GPU 없이도 확인된다** — 학습 결과 CSV가 저장소에 있다. 나머지는 자
가중치가 필요해 학습부터 다시 해야 한다.

## 가중치 식별값

가중치가 저장소에 없으므로 **지금 로컬에 있는 것의 해시**를 남긴다. 다시
학습하면 값이 달라진다(같은 시드여도 CUDA 비결정성이 있다).

| 자 | sha256 앞 16자 |
|---|---|
| `runs_mc_cyclist_rich/clean` | `32510de3f2da46c4` |
| `runs_coco/clean` | `8ce4684b0e46faec` |
| `runs/clean` | `4e998fa7a6dfddae` |

**319개 전부의 해시는 기록하지 않았다.** 필요해지면 그때 만든다.

## 복원할 수 없는 것 — 추정해 채우지 않는다

- **대회 시기(7월) 실험의 조건 폴더와 가중치.** 그 뒤로 조건 정의와 경로 규칙이
  여러 번 바뀌었다. 당시 수치는 `docs/04~08`의 보고서에 남아 있지만 **그
  산출물을 다시 만들 수는 없다.**
- **319개 가중치의 학습 로그 전체.** `runs*/`에 `results.csv`가 있지만
  저장소에는 없다.
- **각 결과 JSON이 어느 커밋에서 생성됐는지.** 파일 안에 커밋 해시를 안 남겼다.
  앞으로 만드는 산출물에는 넣는 것이 좋다 — **지금은 없다.**
- **일부 조건의 무작위 씨앗 차이.** `width_m30_r30`과 기존 `width_m30`은 같은
  설정인데 따로 만들어 주입 박스 수가 다르다(docs/21 AX).

## 대회 시기와 개인 개발의 범위 구분

**2026-08-19를 경계로 가른다.** 그날 2차 예선에서 떨어졌고, 다음 커밋까지
7일이 비어 경계가 분명하다.

| | 대회 시기 | 이후 개인 개발 |
|---|---|---|
| 기간 | 2026-07-07 ~ **08-19** | 2026-08-26 ~ |
| 커밋 | **20개** | **218개** |
| 작업일 | 3일 (07-07, 07-08, 08-19) | 13일 |

### 대회 시기에 만든 것 (커밋 20개)

- MVP 골격 — FastAPI 백엔드 + React 대시보드 + 문서
- KITTI 오류 주입 실험 파이프라인, 오류 조건 21종 학습·API·대시보드
- 최종 보고서(PDF)와 발표 자료, 교수 피드백 반영
- 백엔드 API·오류 주입 로직 검사
- OBB 파이프라인(회전 오류 방향 탐지), 다중 시드 파이프라인과 오차막대

### 이후 개인 개발에서 만든 것 (커밋 218개)

**연구 쪽 — 이 저장소의 결론 대부분이 여기서 나왔다.**

- 실험 일지 `docs/21`의 절 **A~BC**(54개). 대회 시기 결과는 앞부분 일부다
- 자 개념의 확립과 검증 — 자가 맞는지가 진단 품질을 정한다(AA·AD·AG)
- **진짜 도메인 이동**(AI) — 대회 때의 "도메인 이동"은 전부 KITTI 안이었다
- 재검수 순서 결함 발견과 처방(AN·AO)
- 자기 정제가 진다는 결론(AJ~AT, 열세 점)
- 순서 규칙의 바닥 식(AV~BB)과 신뢰도 바닥 검증(BC)
- **예측을 먼저 커밋하는 규칙**(`PREDICTION_*.md` 10개)

**제품 쪽**

- 업로드 → 진단 → 재검수 목록이 끝까지 도는 흐름, 키보드 검수, CSV 내보내기
- 자 추천·적합도 표시, 유형으로 좁히기, 순서 근거(`order_basis`)와
  위험 경고(`order_risk`)
- 검수 판정 서버 보관, 지난 진단 다시 열기, Dockerfile
- 검사 **150건**과 CI, 실험 산출물 정합성 검사기

**대회 발표 자료의 수치는 이 문서가 보증하지 않는다.** 그 뒤 여러 결론이
뒤집혔고 정정 이력은 `docs/21`과 `CHANGELOG.md`에 있다.
