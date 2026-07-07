# 04. API 레퍼런스

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

실험 조건별(7개) 성능 지표. `backend/app/data/metrics.csv`를 그대로 반영.

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
    "performance_drop_pct": 0.0
  },
  { "condition": "width_m30", "type": "width", "magnitude": -30, "...": "..." }
]
```

`performance_drop_pct`는 백엔드에서 `clean` 조건의 `map50`을 기준으로 계산해서
채워주는 파생 필드다 (CSV에는 없음).

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

## 데이터 소스 교체 방법

실제 YOLOv8 실험이 끝나면 `backend/app/data/metrics.csv`를 아래 스키마 그대로
교체하면 된다. 코드 수정 불필요.

```
condition,type,magnitude,map50,map50_95,precision,recall
clean,none,0,...
width_m30,width,-30,...
```
