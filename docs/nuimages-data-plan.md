# nuImages 데이터 계획 — 받기·나누기·자 학습 (평가 데이터를 보기 전에 고정)

> 2026-09-16 작성. 사용자 결정(W1): 비상업 연구·포트폴리오, 평가 데이터는 nuImages
> ([evaluation-data.md](evaluation-data.md) "사용자 결정 — W1"). 이 문서는 **개발용 준비**만 다룬다.
> 평가 표본의 N·K·씨앗·1차 지표는 사전 등록(W5, [qa-preregistration-draft.md](qa-preregistration-draft.md))에서
> 사용자가 정한다.

## 1. 왜 자를 새로 학습하나

개발용 Mini(train 소속 50장)에서 기존 자의 적합도를 쟀다(`experiment/planning_evidence/nuimages_mini_ruler_probe.json`).

| 자 | 입력 | 라벨을 짚은 비율 |
|---|---|---|
| KITTI Car (`runs/clean`) | 640 / 1280 | 25% / 21% |
| COCO Car (`runs_coco/clean`) | 640 / 1280 | 45% / 55% |

자가 차의 절반 이상을 못 보면 `all_label_iou`의 상위가 **자가 못 본 멀쩡한 라벨**로 채워져, Q-A가 라벨 오류가
아니라 자의 맹점을 잰다. 제품의 전제도 "고객 데이터에 맞는 자를 끼운다"이다. 그래서 **nuImages train으로
Car 자를 학습하고, 평가는 val에서 한다.**

## 2. 파일과 자리 — 저장소 밖 `D:/AIDA-eval/nuimages/`

| 자리 | 무엇 |
|---|---|
| `raw/` | 받은 압축 파일 그대로. 받는 즉시 SHA-256 기록 |
| `mini/` | Mini를 푼 것 (개발용) |
| `all/` | Metadata + Samples를 푼 것 (`v1.0-train`·`v1.0-val`·`v1.0-test`·`samples/`) |
| `splits/dev_v1/` | train 분할 토큰 목록과 요약 |
| `yolo/ruler_train`·`yolo/ruler_val`·`yolo/fit_check` | 변환한 YOLO 폴더 |
| `experiment/runs_nuimages/car_v1/` | 학습한 자 (git 제외, **공개하지 않는다**) |

Sweeps(180GB)는 받지 않는다 — 주석이 없다.

## 3. 나누는 규칙

| 묶음 | 어디서 | 쓰임 | 크기(목표) |
|---|---|---|---|
| **평가용** | **val** | 사전 등록한 비교만 | W5에서 사용자가 정함 |
| 적합도 확인용 `fit_check` | train, **기록 단위** | 새 자가 이 데이터를 얼마나 보나, 밴·가림 영향 | 약 500장 |
| 학습 검증용 `ruler_val` | train, **기록 단위** | 학습 중 best.pt 선택만 | 약 300장 |
| 자 학습용 `ruler_train` | train, 위 둘과 **다른 기록**에서 표집 | 자 학습 | 3,200장 |

- 씨앗 **20260916**. 세 묶음은 주행 기록(log)이 서로 겹치지 않는다(`experiment/nuimages_split.py`, 검사
  `test_nuimages_split.py`).
- **실제 분할(2026-09-16):** fit_check 620장·기록 7, ruler_val 357장·기록 3, ruler_train 3,200장·기록 303
  (`experiment/planning_evidence/nuimages_split_dev_v1.json`). 기록을 통째로 모아 목표를 넘었다. fit_check는
  96%가 singapore-onenorth라 **적합도 수치를 지역 전체로 일반화하지 않는다.** 치우침을 보고 씨앗을 바꿔
  다시 뽑지 않는다.
- **val은 사전 등록 커밋 전까지 열지 않는다** — 이미지·라벨·통계 모두. Metadata 압축에 val 표가 들어 있어
  풀리기는 하지만 읽지 않는다. 분할 스크립트는 train이 아닌 분할 이름을 거부한다.
- **적합도 확인용으로 best.pt를 고르지 않는다** — 고르면 확인 수치가 부풀려진다.
- 카메라는 **6방향 전부**로 시작한다. 평가 범위를 앞 카메라로 좁히기로 정하면(W5 D2·D3) 그때 자를 다시
  학습할지 정한다.
- 범주는 `vehicle.car` → `Car` 하나. nuImages의 car에는 **밴·SUV가 포함된다**(KITTI는 Car와 Van을 가른다).
  nuImages 규칙대로 학습하므로 자도 그 정의를 따른다.

## 4. 자 학습

`experiment/train_external_ruler.py` — `yolov8n.pt` 미세조정, `config` 기본값(입력 640, 50에폭, 배치 16,
씨앗 `AIDA_TRAIN_SEED`). 이미 있는 실행 이름은 덮어쓰지 않는다. 학습 뒤 `ruler_manifest.json`에 이미지 수·
목록 지문·설정을 남긴다.

**예상 시간:** RTX 3050에서 3,200장·640·50에폭 기존 기록이 약 34분(`runs_mc_nested_n3200/clean`). nuImages
이미지가 더 커서(1600×900) 읽기 시간이 늘 수 있다 — **약 35~60분.** 시작 전에 사용자 확인을 받는다.

## 5. 적합도 확인 (학습 뒤)

**결과 (2026-09-16, `experiment/planning_evidence/nuimages_fit_check_car_v1.json`).** 학습 2,131초(약 36분),
ruler_val 마지막 에폭 P 0.866·R 0.604·mAP50 0.726(50에폭에서도 오르는 중). fit_check 620장·라벨 1,728개:

| 자 | 라벨을 짚은 비율 | 높이 <30px | 30–60 | 60–120 | ≥120 | IoU 0 라벨 | 규칙 후보 |
|---|---|---|---|---|---|---|---|
| **nuImages car_v1** | **69.9%** | 47% | 75% | 86% | 96% | 263 | 554 (누락 9) |
| COCO Car | 49.0% | 22% | 51% | 72% | 80% | 505 | 466 (누락 26) |
| KITTI Car | 30.6% | 3% | 30% | 57% | 56% | 935 | 219 (누락 7) |

- 카메라별 64.5%(BACK_RIGHT)~77.6%(FRONT_RIGHT). 지역 차이는 기록 7개라 해석하지 않는다.
- **남은 맹점은 작은 차다** — 높이 30px 미만 489개 중 절반을 못 본다. 이 라벨들이 `all_label_iou` 상위를
  채울 수 있으므로, 평가 범위에서 작은 상자를 뺄지(D2)·이 자를 쓸지는 **사용자가 사전 등록 전에 정한다.**
- 규칙 후보 554개는 너비·높이·크기 같은 기하 후보가 대부분이다. amodal 상자 때문인지는 아직 보지 않았다.

`fit_check` 폴더를 새 자로 진단해 `ruler_fit.matched_label_ratio`, 상자 높이별·카메라별 짝 비율, 규칙에 걸린
후보 수를 적는다. **통과 기준을 지금 정하지 않는다** — 기존 참고값(맞는 자가 COCO에서 85.1%, 이 Mini에서
KITTI 25%·COCO 55%)과 나란히 적고, 사전 등록 전에 사용자가 이 자를 쓸지 정한다.

같이 볼 것:

- **가림:** 규칙에 걸린 기하 후보 표본을 보고 nuImages의 amodal 상자 규칙 때문인지 확인한다.
- **작은 차:** 높이 10px 미만·20% 미만으로 보이는 객체는 nuImages가 라벨을 달지 않는다 — 누락 후보가 이런
  것이면 판정 지침에 넣는다.

### 평가 경로에 더한 것 (2026-09-16, W5 조언 반영)

- **주행 기록 묶음.** `nuimages_to_yolo.py`가 `groups.json`(이미지 → log)을 쓴다. 업로드 zip에 넣으면 평가
  묶음이 후보마다 `group_id`를 얼리고(지문에 들어간다), 집계가 기록 단위로 재표집한다. 표에 없는 이미지가
  있으면 묶음을 만들지 않는다.
- **val 표집** `nuimages_eval_sample.py` — 사전 등록 파일이 커밋되어 있고 바뀌지 않았을 때만 val 표를 연다.
  기록을 씨앗으로 섞고 기록마다 최대 `per_log`장. 요약에 사전 등록 커밋을 적는다.
- **높이 층별 기술통계** `evaluation/strata.py` — 내보내기 줄의 `box`로 층을 정하고, 방법의 상위 N을 전체에서
  고른 뒤 층으로 나눠 센다.
- **아직 없는 것:** 제품 경로(업로드 → 진단)에서 nuImages 자를 고르는 길. 지금 진단은 `AIDA_DATASET`별
  `runs*/clean/weights/best.pt`를 연다 — 자를 확정한 뒤 연결한다.

## 6. 판정 지침에 넣을 nuImages 라벨 규칙

([advice-w1-w5-2026-09-16.md](advice-w1-w5-2026-09-16.md) 5절, nuScenes devkit `instructions_nuimages.md`)

- 가려진 차의 상자는 **가려진 부분까지 추정해 포함**한다(amodal).
- 이미지 경계에서 잘린 차는 **경계에서 멈춘다.**
- **높이 10px 미만**, **20% 미만으로 보이는** 객체는 라벨을 달지 않는 것이 규칙이다(확신할 수 있으면 예외).
- 돌출부는 사이드미러·안테나를 빼고 포함한다.
- `vehicle.car`에는 승용차·왜건·밴·미니밴·SUV·지프가 들어가고, 화물용 픽업은 `vehicle.truck`이다.

## 7. 명령 순서

```
cd experiment
# 1) 받은 압축 해시 기록 → 풀기 (Metadata, Samples) — D:/AIDA-eval/nuimages/all/
# 2) 분할 (train만)
./venv/Scripts/python.exe nuimages_split.py --src D:/AIDA-eval/nuimages/all --version v1.0-train \
    --out D:/AIDA-eval/nuimages/splits/dev_v1 --fit-check-images 500 --ruler-val-images 300 \
    --ruler-train-images 3200 --seed 20260916
# 3) 변환 — 묶음마다 한 번
./venv/Scripts/python.exe nuimages_to_yolo.py --src D:/AIDA-eval/nuimages/all --version v1.0-train \
    --out D:/AIDA-eval/nuimages/yolo/ruler_train --category vehicle.car=0 --class-names Car \
    --tokens-file D:/AIDA-eval/nuimages/splits/dev_v1/ruler_train_tokens.txt
# 4) 학습 — 사용자 확인 뒤
./venv/Scripts/python.exe train_external_ruler.py --train D:/AIDA-eval/nuimages/yolo/ruler_train \
    --val D:/AIDA-eval/nuimages/yolo/ruler_val --name car_v1
```
