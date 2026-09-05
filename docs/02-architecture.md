# 02. 시스템 아키텍처
<!-- 시점 표시 -->

> 큰 틀(실험 파이프라인 → CSV → FastAPI → React)은 그대로다. 다만 **파일 목록은 2026-07 기준**이라 그 뒤에 늘어난 것이 빠져 있다 — 백엔드 `routers/upload.py`, 프론트 `Landing`·`ReviewQueue`·`RulerCard`·`BoxPreview`, 실험 스크립트 여럿. 현재 목록은 저장소 README의 '실험 스크립트' 절에 있다.


## 전체 구성

```
aida-project/
├── backend/     FastAPI — 실험 결과(CSV)를 읽어 API로 제공
├── frontend/    React + TypeScript (Vite) — 대시보드 UI
├── experiment/  (예정) KITTI 기반 오류 주입·YOLO 학습·평가 파이프라인
└── docs/        이 문서 폴더
```

현재 `backend`는 `experiment` 파이프라인이 만들어낼 `metrics.csv`를
**목업(mock) 데이터로 미리 읽는 상태**다. 실험 코드가 완성되면 같은 스키마의
실제 CSV로 교체만 하면 되고, API/프론트엔드 코드는 수정할 필요가 없다.

## 데이터 흐름

```
[KITTI 원본 데이터] → [오류 라벨 생성 스크립트] → [YOLOv8 학습·평가] → metrics.csv
                                                                          │
                                                                          ▼
                                                        backend/app/data/metrics.csv
                                                                          │
                                                     FastAPI (app/routers/report.py)
                                                                          │
                                                    GET /api/summary, /conditions, /diagnose
                                                                          │
                                                       frontend (React) ← axios
                                                                          │
                                              QualityScoreCard / PerformanceChart / ErrorReportTable
```

## 백엔드 (`backend/`)

```
backend/
├── requirements.txt
├── venv/                       (Python 3.x 가상환경, 설치 완료)
└── app/
    ├── main.py                 FastAPI 앱 진입점, CORS 설정
    ├── models.py                Pydantic 응답 모델 정의
    ├── routers/
    │   └── report.py            /api/summary, /api/conditions, /api/diagnose
    └── data/
        └── metrics.csv          실험 결과 (조건별 mAP/Precision/Recall) — 현재 목업
```

- 실행: `uvicorn app.main:app --reload --port 8000` (backend 폴더에서)
- API 문서: 서버 실행 후 http://localhost:8000/docs (FastAPI 자동 생성 Swagger UI)

## 프론트엔드 (`frontend/`)

```
frontend/
└── src/
    ├── main.tsx, App.tsx          앱 진입점, 데이터 페칭 및 레이아웃
    ├── api.ts                     axios 기반 API 클라이언트
    ├── types.ts                   백엔드 Pydantic 모델과 1:1 대응하는 TS 인터페이스
    └── components/
        ├── QualityScoreCard.tsx   품질 점수, 총 이미지/객체/오류의심 건수
        ├── PerformanceChart.tsx   조건별 성능 저하 막대그래프 (recharts)
        └── ErrorReportTable.tsx   오류 유형별 재검수 우선순위 표
```

- 실행: `npm run dev` (frontend 폴더에서) → http://localhost:5173
- 스타일: 발표자료(PPT)와 동일한 흑백 + 형광 라임(`#CCFF00`) 포인트 컬러 톤 유지
  (`src/App.css`, `src/index.css`)

## 아직 없는 것 (TODO)

- `experiment/` — 실제 KITTI 다운로드, 오류 라벨 생성 스크립트, YOLOv8 학습 코드
  (설계는 [03-experiment-design.md](./03-experiment-design.md)에 완료, 코드 구현 예정)
- 인증서(PDF) 발급 기능, 실제 파일 업로드 API는 MVP 이후 범위
