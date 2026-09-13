# prelim1 사전 등록 — AIDA 대 단순 기준선 예비 비교 (탐색)

> **판정 전에 커밋한다.** 이 문서와 명세
> (`experiment/planning_evidence/prelim1_manifest.json`)를 푸시하기 전에는 판정 화면을
> 열지 않는다. 판정은 사람이 나중에 한다.

| | |
|---|---|
| 데이터셋 ID | **`30512dfcbfbb`** (새로 만든 예비 데이터셋) |
| 평가 ID | **`prelim1`** |
| `candidate_set_hash` | `e996e26282ab1723ea8ca7a11e820031a34b057cd115ab1a3412011f8391e497` |
| `snapshot.json` SHA-256 | `b694ac2d2e145e408b9ec50ea7a89bcfb5471b0cb88cba392441ee6d34123309` |
| `label_diagnosis.json` SHA-256 | `1feb441bebf2f3902562a349671cc975bc488063d735be0d66e0482f674c9c04` |
| 자 가중치 SHA-256 | `4e998fa7a6df…` (전체는 명세) |
| 이미지 목록 SHA-256 | `19cd45af1bb2…` (전체는 명세) |
| 판정할 후보 | **186건** — 기존 라벨 162 + 누락 24 |
| 판정 상태 | **시작 안 함** — `adjudications.json`·`activity.jsonl` 없음 |

## 1. 목적 — 탐색적 계획 근거

**최종 검증이 아니다.** 검정력 계획을 막고 있는 현실 값 — 두 방법의 순위 품질
차이, 오류 비율, 이미지 내 묶임 — 에 대한 **첫 판정 자료**를 모으려는 것이다
([planning-assumption-evidence.md](planning-assumption-evidence.md)).

**성공·실패를 주장하지 않는다.** Δ가 정해지지 않았으므로 판정 규칙
(`verdict_against_delta`)을 쓰지 않는다. `N_required`·`N_final`·Δ·D·T는 **미정으로
남는다.**

## 2. 데이터

| 항목 | 고정값 |
|---|---|
| 범위 | **KITTI 개발 데이터, Car 한 클래스** |
| 원본 | `experiment/data/processed/images/val`, 라벨 `labels_gt_nested/val` |
| 제외 1 | 자의 학습 프레임 — `labels_gt/train`·`images/train` stem |
| 제외 2 | 파일럿 `ffffffffff01`~`07`이 쓴 이미지 338장 |
| 적격 | 413장 |
| 표집 | **씨앗 20260914로 300장** — 이름 전부가 명세에 있다 |
| 자 | `experiment/runs/clean/weights/best.pt` (프로파일 없음 = 기본 KITTI Car) |

**최종 평가에 재사용하지 않는다.** 이 데이터는 규약을 보정하는 데 쓰므로 개발
데이터다. 최종 평가 후보는 KITTI 밖이다([evaluation-data.md](evaluation-data.md)).

**보존.** 판정에 쓰는 정확한 파일 — 이미지·라벨·`classes.txt`·`ruler.json`·
`label_diagnosis.json`·`snapshot.json` — 을 `D:/AIDA-eval/prelim/prelim1_30512dfcbfbb/`에
읽기 전용으로 복사했다(저장소 밖). 파일마다 SHA-256이 명세에 있다. 파일럿
`ffffffffff01`~`07`, 사용자 데이터셋 5개, 기존 CSV·PDF·가중치는 건드리지 않았다.

## 3. 제품 경로와 이탈 하나

| 단계 | 경로 |
|---|---|
| 업로드 | `POST /api/datasets/upload` — 백엔드 앱을 같은 프로세스에서 불렀다 |
| 진단 | 실행 중인 백엔드의 `POST /api/datasets/30512dfcbfbb/diagnose-labels` |
| 평가 묶음 | 실행 중인 백엔드의 `POST .../evaluations` `{evaluation_id: prelim1, shuffle_seed: 20260915, judge_budget: 90}` |

**이탈.** 업로드 zip이 237.8MB라 코드의 상한 200MB를 넘었다. **그 한 번의 호출에서만**
`MAX_UPLOAD_BYTES`를 300MB로 올렸다. zip 안전 검사·압축 해제·폴더 검증·ID 발급은
제품 코드 그대로이고, 코드는 바꾸지 않았고, 이미지를 다시 인코딩하지 않았다.

**재현성.** 같은 300장·라벨·가중치를 `diagnose_labels.py --dataset-dir`로 따로 한 번
돌린 결과와 제품 경로 결과의 후보 331건이 **모든 필드에서 같았다.** 비트 단위
재생성은 주장하지 않는다 — 진단 파일에 생성 시각이 들어가고, 결정적 연산 설정은
꺼져 있다(`cudnn.deterministic=False`). 판정에 쓰는 것은 보존한 파일 자체다.

## 4. 방법 — 둘만

| 방법 | 순서 |
|---|---|
| `aida` | 진단의 제품 순위 `rank` (계통적 유형 먼저, 그 안에서 심각도) |
| `iou_baseline` | `1 − label_iou` 내림차순, 동점은 집계 규약대로 |

**무작위 순서와 규칙 하나 뺀 AIDA는 넣지 않는다.** 판정 뒤에 방법을 더하거나 빼지
않는다.

## 5. 판정 규칙

- **N = 90.** 운영상 절충이다 — 판정 186건, 이 판정자 기준 활동 약 15.6분. **검정력으로
  정당화하지 않았고 `N_required`가 아니다.**
- **판정 대상 = 합집합.** 기존 라벨 층에서 AIDA 상위 90과 기준선 상위 90의 합집합
  (겹침 18건 → 162건), 누락 층에서 AIDA 상위 90(누락 후보가 24건뿐이라 전부).
- **누락 층은 기술 통계만** 낸다. 비교군이 없다.
- **판정은 방법과 무관한 사실 하나다.** 한 후보의 판정을 두 방법이 같이 쓴다.
- **가림.** 판정 화면에 점수·순위·의심 유형·추천 출처·진단 문구를 보내지 않는다.
  기존 라벨인지 누락인지는 과제가 달라 가리지 않는다.
- **순서.** `shuffle_seed` **20260915**로 섞는다.
- **두 묶음.** 섞인 순서대로 약 93건을 본 뒤 쉬고, 나머지를 본다. 화면이 강제하지는
  않는다 — 판정자가 지킨다. 한 묶음이 관측한 지속 판정 길이(120건 1회)를 넘지 않게
  하려는 것이다.
- 판정 지침은 [manual-timing-pilot.md](manual-timing-pilot.md). `hold`를 쓸 수 있다.

## 6. 판정 뒤 분석 — 미리 정한 것

1. `GET .../evaluations/prelim1/export?methods=aida,iou_baseline`(기존 라벨 층)과
   `?methods=aida&scope=missing_candidates`(누락 층)를 저장한다.
2. `experiment/evaluation`의 `importer.load_export` → `summary.summarise`로 방법마다
   **검수량 10·20·…·90**에서 고유 오류 수·hit 후보 수·보류 수·결정된 수를 센다.
3. 기존 라벨 층에서 짝지은 차이와 **이미지 묶음 짝지은 부트스트랩 95% 구간**을 낸다
   — 씨앗 **42**, 반복 **2000**. **Δ가 없으므로 성공·불확실·실패 판정은 내지 않는다.**
4. 누락 층은 hit·보류 수만 적는다.
5. 결과를 계획 근거로 쓸 때는 **판정자 한 명의 판정**으로 표시한다
   (`single_reviewer_observed_hit_rate`와 같은 수준). 참 오류 비율로 쓰지 않는다.

## 7. 지키는 약속

- 판정을 본 뒤 **N·방법·판정 규칙·분석 검수량을 바꾸지 않는다.**
- **최종 성공·실패를 주장하지 않는다.** 이 결과로 Δ나 성공 기준을 사후에 정하지 않는다.
- **최종 평가에 이 데이터를 쓰지 않는다.**
- **판정자는 훈련된 한 명이고 판정자 간 일치도가 없다.** 한 사람의 판정은 정확성을
  입증하지 않는다.
- `N_required`·`N_final`·Δ·D·T는 **정하지 않은 채로 남는다.**

## 8. 판정 전 점검 — 커밋 전에 끝낸 것

| 점검 | 결과 |
|---|---|
| `all_candidates` 길이 = `total_in_queue` | 331 = 331 |
| `review_queue`가 순위의 앞부분 | 앞 100건 일치 |
| `rank`가 1부터 겹침 없이 | 맞다 |
| 기존 라벨 후보에 `label_iou` | 307/307 |
| 묶음이 잘리기 전 후보 전부를 얼렸는가 | `candidate_pool=all_candidates`, 331건 |
| 판정 대상 = AIDA 90 ∪ 기준선 90 ∪ 누락 AIDA 90 | **정확히 같다** (186건) |
| 세 번째 방법(무작위) | 없다 — 점수는 `aida`·`iou_baseline`뿐 |
| 판정 목록에 담기는 항목 | `box`·`canonical_candidate_id`·`class_name`·`image`·`label_index`·`unique_error_id`·`verdict` — 점수·순위·유형 없음 |
| 섞인 순서가 씨앗대로 같은가 | 두 번 만들어 같았다 |
| 내보내기 → 가져오기 → 요약 | (아래 9절) |

## 9. 합성 판정으로 집계 경로 확인

**실제 prelim1 판정 파일을 만들지 않았다.** 메모리에서 합성 판정(씨앗 777)을 만들어
내보내기 함수를 부르고, 결과를 임시 폴더에 쓴 뒤 `importer`·`summary`로 읽었다.
실제 평가 폴더의 파일 목록은 전후가 같았다.

| 확인 | 결과 |
|---|---|
| 합성 판정 | 판정 대상 186건 전부 (씨앗 777, hit·miss·hold 섞음) |
| 서버 검증 | `validate_adjudications`·`resolve_unique_error_ids` 통과 |
| 기존 라벨 층 내보내기 (`aida,iou_baseline`) | 후보 307 · 순위 614 · `comparison_allowed=true` |
| 누락 층 내보내기 (`aida`) | 후보 24 · `descriptive_only=true` |
| `importer.check_scope`·`load_export` | 두 층 모두 통과 |
| `summary.summarise` 검수량 10·50·90 | 두 방법 모두 **예산 안 후보가 전부 판정됨** |
| 짝지은 부트스트랩 (씨앗 42, 반복 2000) | **처음에는 실패 → 고쳐서 통과** (아래) |
| 실제 `prelim1` 폴더 | 전후 파일 목록·수정 시각 같음 — `snapshot.json`만 있다 |

**판정 전에 잡은 결함.** 부트스트랩 재표집이 이미지를 `a.jpg#0`으로, 기존 라벨 hit의
고유 오류 id를 `a.jpg/L0#0`으로 **따로** 바꿔 스키마 규칙(`id = 이미지/L라벨`)에
걸렸다. **서버가 붙이는 형식의 id로는 부트스트랩이 한 번도 돌지 않았다** — 기존
검사는 그 모양의 id를 부트스트랩에 넣지 않았다. 손계산 검사
(`experiment/tests/test_bootstrap_server_ids.py`)가 고치기 전 실패, 고친 뒤 통과했고
합성 내보내기에서 부트스트랩이 돌았다(이미지 묶음 163개). 수정 커밋 `21fd32d8`.
**분석 코드만 바뀌었다** — 진단·평가 묶음 코드는 그대로라 `candidate_set_hash`에
영향이 없다. 명세의 코드 커밋(`809cd990`)은 진단·묶음을 만든 시점이다.

합성 판정의 수치는 뜻이 없어 싣지 않는다.

## 10. 커밋 뒤, 판정 전에 할 일

1. 재검수 화면에서 맨 위 행이 `rank` 1·2·3과 같은 후보인지 본다.
2. 가림 화면을 **prelim1이 아닌 점검용 평가**(같은 씨앗·예산으로 만든 별도 ID)로
   열어 점수·순위·유형이 안 보이는지 본다. prelim1에 점검 기록이 남지 않게 하려는 것이다.
3. 점검 탭을 모두 닫고, 늦게 오는 기록 전송을 기다린 뒤, prelim1에
   `adjudications.json`·`activity.jsonl`이 없는지 다시 본다.
4. 백엔드·프론트엔드를 띄우고 판정 주소를 남긴다:
   `http://localhost:5173/?evaluate=30512dfcbfbb:prelim1`
