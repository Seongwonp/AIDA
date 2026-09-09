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
| `AIDA_ERROR_RATIO` | 0.3 | 기본값이 아니면 경로에 `_r0p1`처럼 붙는다. 0 초과 1 이하만 받는다 |

전체 목록은 `experiment/.env.example`과 README의 환경변수 표에 있다.

### ~~분할 목록 파일이 없는 이유~~ — 정정 (2026-09-09, docs/25 2단계)

처음엔 이렇게 적었다: "분할은 `AIDA_SEED`로 결정론적이라 목록을 따로 저장하지
않아도 된다."

**시드만으로는 부족하다.** 시드는 **같은 프레임 풀**을 전제한다. 풀
(`data/raw/selected_frames*.txt`)은 저장소에 없고, 원본 데이터가 달라지면 같은
시드로도 다른 분할이 나온다. 같은 이름의 다른 그림이면 목록조차 같아 보인다.

그래서 **실행 명세**를 남긴다 — `experiment/run_manifest.py`.

```bash
python run_manifest.py --runs runs_coco/clean --out manifests/coco.json
```

| 담기는 것 | 왜 |
|---|---|
| 학습·평가 프레임 id **전부**와 목록 해시 | 시드를 대신한다 |
| 분할에 든 이미지의 **내용 해시** | 같은 이름의 다른 그림을 잡는다 |
| `best.pt`의 sha256과 학습 설정 | 어느 가중치였는지 |
| git 커밋과 **작업 트리가 깨끗한지** | 커밋만 적으면 없는 상태를 재현하려 하게 된다 |
| python·torch·ultralytics 판 | 없는 것은 **없다고** 적는다 |
| 클래스·데이터셋·프레임 선택·규모·에폭·비율·시드 | 설정 전부 |

**풀 파일이 없으면 "분할을 되살릴 수 없다"고 적는다** — 조용히 빈 목록을 남기면
명세를 믿고 재현하려다 다른 분할을 얻는다.

### 명세가 스스로 불완전함을 말한다

| 항목 | 뜻 |
|---|---|
| `complete` | 분할의 **모든** 이미지 해시를 떴는가 |
| `missing_images` | 못 찾은 것의 목록. 빈 채로 두지 않는다 |
| `image_locations` | 각 이미지를 **어느 폴더에서** 찾았는가 |
| `code.reproducible` | 작업 트리가 더러우면 `false` |
| `weights[].source` | 어느 실행이 만들었는가. 모르면 `unknown` |
| `manifest_schema_version` | 명세의 모양이 바뀌면 올린다 |

**논리적 분할과 파일이 놓인 자리는 다르다.** 학습 목록의 프레임이
`images/val`에 있기도 한다 — 물리적 배치는 내려받기 단계가 정하고 분할은 시드가
정하기 때문이다. 처음엔 한쪽만 찾다가 COCO에서 **190장을 조용히 빠뜨렸고**,
그때도 명세는 완전해 보였다.

**더러운 작업 트리는 정확 재현이 안 된다.** 커밋되지 않은 변경의 해시를 남기지만
**그것으로 재현할 수 있다는 뜻이 아니다** — diff 내용은 어디에도 안 남고, 추적
안 되는 새 파일은 diff에 잡히지도 않는다. 나중에 같은 상태인지 **대조만** 할 수
있다.

**가중치 출처는 자동으로 모른다.** 실행 폴더 이름은 조건 이름이지 출처가 아니다.
`--source runs_coco/clean=train_coco_rulers.sh`처럼 직접 준다.

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
