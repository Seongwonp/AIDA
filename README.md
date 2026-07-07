# AIDA — AI 데이터 품질 인증 플랫폼 (MVP 데모)

> 이 프로젝트가 처음이라면 [`docs/README.md`](docs/README.md)부터 읽을 것.
> 프로젝트 배경, 핵심 기술 원리(특허 연계), 아키텍처, 실험 설계, 의사결정 이유가
> 전부 문서화되어 있다. 개발 이력은 [`CHANGELOG.md`](CHANGELOG.md) 참고.

## 구성

- `backend/` — FastAPI. 실험 결과(`backend/app/data/metrics.csv`)를 읽어 품질 점수·오류 리포트 API 제공
- `frontend/` — React + TypeScript (Vite). 대시보드 UI
- `experiment/` — KITTI 다운로드 → 전처리 → 오류 라벨 생성 → YOLOv8n 학습·평가 파이프라인
  (자세한 실행법은 [docs/09-getting-started.md](docs/09-getting-started.md) 참고)
- `docs/` — 프로젝트 문서 (기술 원리, 아키텍처, 실험 설계, API 레퍼런스, 용어사전, 의사결정 로그, 로드맵)
- `CHANGELOG.md` — 개발 변경 이력

## 실행 방법

### 1. 백엔드

```bash
cd backend
cp .env.example .env        # 최초 1회만 (이미 있으면 스킵)
source venv/bin/activate    # 이미 venv 생성·설치되어 있음
uvicorn app.main:app --reload --port 8000
```

http://localhost:8000/docs 에서 API 확인 가능.

### 2. 프론트엔드 (새 터미널)

```bash
cd frontend
cp .env.example .env        # 최초 1회만 (이미 있으면 스킵)
npm run dev
```

http://localhost:5173 에서 대시보드 확인.

## 환경변수

모든 설정값(포트, CORS origin, API base URL, 실험 하이퍼파라미터 등)은 코드에
하드코딩하지 않고 `.env` 파일로 관리한다. 각 서브프로젝트(`backend/`, `frontend/`,
`experiment/`)에 `.env.example`이 있으니 최초 1회 `.env`로 복사해서 쓰면 된다.
`.env`는 `.gitignore`에 포함되어 커밋되지 않는다.

## 실제 실험 결과 반영하기

지금은 `backend/app/data/metrics.csv`가 **목업(mock) 데이터**입니다.
실제 YOLOv8 실험(7개 조건)이 끝나면, 같은 컬럼 구조(`condition,type,magnitude,map50,map50_95,precision,recall`)로
이 파일만 교체하면 대시보드에 실제 결과가 그대로 반영됩니다. 코드 수정 불필요.

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/summary` | 데이터셋 전체 요약 (품질 점수, 총 이미지/객체 수) |
| GET | `/api/conditions` | 실험 조건별 성능 지표 (mAP, Precision, Recall) |
| GET | `/api/diagnose` | 오류 유형별 진단 리포트 (재검수 우선순위 포함) |
