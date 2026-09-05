# 04. API 레퍼런스
<!-- 시점 표시 -->

> **아래 "연구 결과" 절은 2026-07 기준**이다. 그 뒤에 붙은 제품
> 엔드포인트(업로드·진단·재검수·삭제)는 맨 끝 "내 데이터셋" 절에 있다.
>
> **응답 스키마는 여기 적지 않는다.** 서버를 띄우고
> `http://localhost:8000/docs`를 보면 FastAPI가 코드에서 직접 만들어 준다.
> 이 문서가 2026-07에서 멈춘 이유가 손으로 베낀 스키마다 — 같은 내용을 두
> 군데 두면 반드시 한쪽이 낡는다. 여기에는 **OpenAPI가 말해줄 수 없는 것**을
> 적는다.


Base URL (로컬 개발): `http://localhost:8000`

## GET /api/health

서버 상태 확인용.

```json
{ "status": "ok" }
```

## GET /api/summary

데이터셋 전체 요약 정보.

```json
{
  "total_images": 412,
  "total_objects": 3184,
  "suspected_error_count": 247,
  "quality_score": 78,
  "certified": false
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| total_images | int | 데이터셋 총 이미지 수 |
| total_objects | int | 데이터셋 총 객체(라벨) 수 |
| suspected_error_count | int | 오류 의심 라벨 건수 |
| quality_score | int (0~100) | 데이터셋 품질 점수 |
| certified | bool | 품질 인증서 발급 기준 충족 여부 |

## GET /api/conditions

실험 조건별 성능 지표. `backend/app/data/metrics.csv`에
`experiment/iou_table.csv`를 조건명 기준으로 조인해서 반환한다.

```json
[
  {
    "condition": "clean",
    "type": "none",
    "magnitude": 0,
    "map50": 0.912,
    "map50_95": 0.681,
    "precision": 0.903,
    "recall": 0.887,
    "performance_drop_pct": 0.0,
    "mean_iou": 1.0,
    "mean_iou_drop_pct": 0.0
  },
  { "condition": "width_m30", "type": "width", "magnitude": -30, "...": "..." }
]
```

`performance_drop_pct`는 백엔드에서 `clean` 조건의 `map50`을 기준으로 계산해서
채워주는 파생 필드다 (CSV에는 없음).
`mean_iou`와 `mean_iou_drop_pct`는 라벨 변형 전후의 평균 IoU와 IoU 감소율이다.
IoU 표가 없는 환경에서는 `null`로 내려간다.

## GET /api/roi-estimate

수작업 검수 비용과 GPU 재학습 비용 절감 효과를 보여주는 가정값 기반 추정 예시.
실제 고객 단가가 아니라 발표/사업화 설명을 위한 샘플 계산이다.

```json
{
  "label": "추정 예시",
  "assumptions": {
    "dataset_labels": 100000,
    "manual_review_minutes_per_label": 0.5,
    "reviewer_hourly_cost_krw": 25000,
    "suspected_review_ratio": 0.3,
    "gpu_retrain_runs_without_aida": 6,
    "gpu_retrain_runs_with_aida": 2,
    "gpu_cost_per_run_krw": 120000
  },
  "manual_review_savings_krw": 14583333,
  "gpu_savings_krw": 480000,
  "total_savings_krw": 15063333,
  "review_scope_reduction_pct": 70.0
}
```

계산식:

- 수작업 검수 비용 = 라벨 수 × 건당 검수 시간 ÷ 60 × 시간당 인건비
- GPU 비용 = 재학습 횟수 × 1회 재학습 비용

## GET /api/diagnose

오류 유형별 진단 리포트. 오류 유형(width/height/rotation)마다 가장 성능 저하가
큰 조건을 뽑아 재검수 우선순위를 매긴다.

```json
{
  "dataset_name": "sample_customer_dataset_v1",
  "quality_score": 78,
  "certified": false,
  "generated_at": "2026-07-07T10:07:32Z",
  "error_reports": [
    { "error_type": "width", "label": "가로 길이 오류", "max_performance_drop_pct": 15.1, "review_priority": "높음" },
    { "error_type": "height", "label": "세로 길이 오류", "max_performance_drop_pct": 14.4, "review_priority": "중간" },
    { "error_type": "rotation", "label": "회전각 오류", "max_performance_drop_pct": 9.1, "review_priority": "중간" }
  ]
}
```

우선순위 기준(`backend/app/routers/report.py`): 성능 저하 15% 이상 → 높음,
8~15% → 중간, 8% 미만 → 낮음.

**포지셔닝 주의** (`docs/11-professor-feedback.md` 5번): 이 결과는 라벨 오류를 100%
확정하는 것이 아니라, 성능 저하 패턴 기반으로 오류 가능성이 높은 유형을 추정해
재검수 우선순위를 매기는 확률적 가이드다. 프론트엔드(`ErrorReportTable.tsx`)에도
동일한 톤으로 캡션을 넣었으니, 문구를 바꿀 때는 이 포지셔닝을 유지할 것.

## 데이터 소스 교체 방법

실제 YOLOv8 실험이 끝나면 `backend/app/data/metrics.csv`를 아래 스키마 그대로
교체하면 된다. 코드 수정 불필요.

```
condition,type,magnitude,map50,map50_95,precision,recall
clean,none,0,...
width_m30,width,-30,...
```


## 내 데이터셋 (제품)

`/api/datasets` 아래. 스키마는 `/docs`에 있으니, 여기서는 그것으로 알 수 없는
것만 적는다.

### 무엇이 GPU를 쓰는가

`POST`로 끝나는 두 개만 실제로 추론을 돌린다. 나머지는 디스크에 있는 JSON을
읽을 뿐이다.

| 경로 | 무겁나 | 남기는 것 |
|---|---|---|
| `POST /upload` | 아니오 | zip을 풀어 `<UPLOADS_DIR>/<id>/` |
| `POST /{id}/diagnose` | **예 (수십 초)** | `diagnosis.json` |
| `POST /{id}/diagnose-labels` | **예 (수십 초)** | `label_diagnosis.json`, `ruler.json` |
| `GET /{id}/diagnosis` · `/{id}/label-diagnosis` | 아니오 | — |
| `GET /history` · `/{id}/images/{name}` · `/{id}/report` | 아니오 | — |
| `DELETE /{id}` | 아니오 | 폴더째 지운다 (되돌릴 수 없음) |

추론은 backend가 아니라 `experiment/venv`에서 서브프로세스로 돈다. backend에
ultralytics·torch를 얹지 않기 위해서다. 그래서 **GPU가 없는 기계에서는 POST
두 개만 실패하고 나머지는 그대로 된다** — 이미 만들어 둔 결과는 계속 열린다.

타임아웃은 `DIAGNOSE_TIMEOUT_SEC`(300초)이고, 넘으면 504다.

### 걸리기 쉬운 곳

- **폴더째 압축한 zip.** `mydata/images/...` 처럼 한 겹 싸여 오면 벗겨서
  읽는다. 다만 최상위 폴더가 둘 이상이거나(`train/` `val/`) 안에도 `images/`가
  없으면 벗기지 않고 400을 낸다 — 잘못 벗기면 원인이 더 가려진다.
- **`labels/`에 `.txt`가 하나도 없으면 400.** 그냥 통과시키면 모든 라벨이
  '누락 의심'으로 나와서 진짜 원인(`.json`·`.xml`을 넣었다)을 못 찾는다.
- **`ruler.json`이 없는 결과가 있다.** 그 사이드카를 만들기 전에 진단한
  것이라, 화면은 기준 모델 카드를 생략하는 폴백으로 간다.
- **`review_queue`의 `box`가 `null`일 수 있다.** 누락 의심은 가리킬 라벨이
  없고, 좌표를 내보내기 전에 만든 결과에도 없다.
- **검수 판정은 서버에 없다.** 브라우저 `localStorage`에만 남는다 — 사용자
  개념이 없어서다. 다른 기계에서 열면 판정이 안 보인다.

### 경로 순서

`/{dataset_id}/...` 는 전부 두 조각이라 한 조각짜리 `/history`·`/upload`·
`/reliability-profiles`와 서로 가리지 않는다. **한 조각짜리 `/{dataset_id}`를
나중에 추가한다면 그때는 그 앞에 와야 한다.**
