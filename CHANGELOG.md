# Changelog

이 프로젝트의 개발 이력을 시간순으로 기록한다. 각 항목은 "무엇을 했는지"와
"왜 했는지"를 함께 남긴다. 의사결정의 배경(왜)은 [docs/06-decisions.md](docs/06-decisions.md)에
더 자세히 정리되어 있다.

## 2026-07-07

### Added

- 프로젝트 초기 스캐폴딩 생성 (`backend/`, `frontend/`, `docs/`)
- **backend**: FastAPI 앱 구성
  - `app/main.py` — 앱 진입점, CORS 설정
  - `app/models.py` — Pydantic 응답 모델 (`ConditionMetric`, `DatasetSummary`, `ErrorTypeReport`, `DiagnosisResult`)
  - `app/routers/report.py` — `/api/summary`, `/api/conditions`, `/api/diagnose` 3개 엔드포인트
  - `app/data/metrics.csv` — 실험 결과 목업 데이터 (7개 조건, 실제 실험 완료 전까지 사용)
  - Python venv 생성 및 `fastapi`, `uvicorn`, `pandas` 설치
  - 로컬에서 3개 엔드포인트 curl 테스트 통과 확인
- **frontend**: Vite + React + TypeScript 스캐폴딩
  - `recharts`, `axios` 설치
  - `src/types.ts` — 백엔드 모델과 1:1 대응하는 TypeScript 인터페이스
  - `src/api.ts` — axios 기반 API 클라이언트
  - `src/components/QualityScoreCard.tsx` — 품질 점수 카드
  - `src/components/PerformanceChart.tsx` — 조건별 성능 저하 막대그래프 (recharts)
  - `src/components/ErrorReportTable.tsx` — 오류 유형별 재검수 우선순위 표
  - `src/App.tsx`, `src/App.css`, `src/index.css` — 대시보드 레이아웃, 발표자료와 동일한
    흑백+형광(#CCFF00) 톤으로 스타일링
  - `tsc -b && vite build` 빌드 통과 확인 (recharts Tooltip 타입 에러 1건 수정)
  - `npm run dev` 로컬 구동 확인
- `docs/` 폴더 생성: 프로젝트 개요, 기술 원리, 아키텍처, 실험 설계서, API 레퍼런스,
  용어사전, 의사결정 로그, 사업화 로드맵 문서화
- 발표자료(PPTX) 40장 초안 완성 (문제정의→솔루션→차별성→시장분석→BM→실행계획→팀)
  - 1차: 네이비/시안 컬러 테마 → 2차: 형광 라임 하이라이터 스타일 → 3차: 형광 사용을
    5장으로 최소화, 박스형 카드 반복 제거하고 에디토리얼 텍스트 레이아웃으로 전환
  - 슬라이드 13(핵심 기술 원리)을 4단계(가상이미지·참값 생성 / 에러 바운딩박스 생성 /
    모델 학습과 평가 자동화 / 오류 판단)로 확정 반영
- 기술 검증 실험 설계서 확정: KITTI Car 클래스, 7개 오류 조건(가로/세로 ±30%,
  회전각 ±15°), YOLOv8n 파인튜닝 기반

### Decided

- 자세한 배경은 `docs/06-decisions.md` 참고. 요약:
  - 특허(10-2664201) 청구항과 정합성 확인 → 가로/세로/회전각을 주 오류 유형으로 확정
  - 신규 이미지 생성 없이 KITTI 기존 이미지+라벨을 참값으로 재활용하기로 결정
  - 대상 클래스는 Car 단일 클래스로 한정
  - MVP 실험은 유료 AI API 없이 로컬(M1 Mac, MPS)/무료 크레딧만으로 진행
  - MVP 데모는 FastAPI + React/TypeScript 웹 대시보드로 결정

### Next

- [ ] `experiment/` 폴더: KITTI 다운로드 → 라벨 변환 → 오류 라벨 생성 스크립트 구현
- [ ] YOLOv8n 파인튜닝 13회 실행 (핵심 7개 우선, 세분화 6개 이어서), `metrics.csv`를 실제 결과로 교체
- [ ] 교수님(김성호, 영남대 전자공학과) 기술 검토 회신 반영
- [ ] 2차 예선(2026-07-09~10) 발표 리허설

## 2026-07-07 (2)

### Changed

- 실험 조건 매트릭스를 7개 → **13개로 재확정** (기준선 + 가로±30/±15% + 세로±30/±15% +
  회전각±15/±7.5°). 이유는 `docs/06-decisions.md`의 "2026-07-07 (2)" 항목 참고
- `backend/app/data/metrics.csv`를 7행 → 13행 목업 데이터로 갱신, API 응답 정상 확인
- `docs/03-experiment-design.md` 4번 섹션을 13개 조건 매트릭스로 갱신, 실행 순서(핵심
  7개 우선 → 세분화 6개)를 시간 리스크 관리 방안으로 명시

### Added

- `docs/08-professor-review-email.md` — 교수님께 보낼 기술 검토 요청 메일 완성본
  (본문 5개 핵심 질문 + 세부 사항은 첨부 자료로 분리)
- `docs/09-getting-started.md` — 새 세션/새 개발자가 프로젝트를 이어받을 때 가장
  먼저 읽는 진입점 문서 (완료된 것 / 다음 할 일 / AI 어시스턴트용 안내 포함)

## 2026-07-07 (3)

### Added

- `experiment/` 폴더 구현 (docs/03-experiment-design.md 5절 모듈 구성 그대로 반영)
  - `config.py` — 13개 조건 정의, SEED/EPOCHS 등 전역 설정 (스모크 테스트용
    `AIDA_N_TRAIN`/`AIDA_N_VAL`/`AIDA_EPOCHS` 환경변수 오버라이드 지원)
  - `download_kitti.py` — 라벨 zip(5.6MB)은 전체, 이미지 zip(12.5GB)은 HTTP
    Range 요청으로 Car 클래스 포함 프레임 중 필요한 만큼만 부분 다운로드
    (전체 다운로드 불필요, S3가 Accept-Ranges: bytes 지원함을 확인 후 구현)
  - `data_loader.py` — Car 클래스 추출, KITTI→YOLO 라벨 변환, SEED 고정 train/val 분할
  - `error_injector.py` — 13개 조건별로 라벨 30% 무작위 변형 (크기: 중심 고정
    스케일링, 회전: 꼭짓점 회전 후 축정렬 재계산), 조건별 데이터셋을 파일 단위
    심볼릭 링크로 구성해 이미지 중복 없이 디스크 절약
  - `train.py`, `evaluate.py`, `run_all.py` — YOLOv8n 파인튜닝(우선순위 1/2/all
    선택 실행) 및 평가, 결과를 `backend/app/data/metrics.csv` 스키마로 자동 갱신
  - venv 생성 후 `AIDA_N_TRAIN=16 AIDA_N_VAL=8 AIDA_EPOCHS=1`로 전체 파이프라인
    (다운로드→전처리→에러 주입→학습→평가→metrics.csv 갱신) 스모크 테스트 통과 확인

### Fixed

- `error_injector.py`에서 조건별 `images/` 디렉토리를 통째로 심볼릭 링크했더니
  ultralytics가 data.yaml 경로를 `.resolve()`할 때 원본 디렉토리로 역참조되어
  라벨을 못 찾는 문제 발견 → 디렉토리 대신 파일 단위 심볼릭 링크로 변경해 해결
- `evaluate.py`의 `model.val()`에 `project`/`name` 미지정 시 프로젝트 루트에
  `runs/detect/val`이 새로 생겨버리는 문제 → `config.RUNS_DIR` 하위로 고정

### Next

- [ ] 실제 KITTI 다운로드(400+120장) 및 13개 조건 전체 학습·평가 실행
      (핵심 7개 우선 → 세분화 6개, 예상 2~4시간) — 사용자 확인 후 진행
- [ ] 교수님(김성호) 기술 검토 회신 반영
- [ ] 2차 예선(2026-07-09~10) 발표 리허설

## 2026-07-07 (4)

### Added

- `docs/10-competition-brief.md` — 공식 공고문(방위사업청·국방과학연구소·민군협력진흥원,
  2026-06-09) 기준 대회 전체 일정, 1차/2차 예선 평가기준 배점표, 본선 시상 내역,
  지원 내용(바우처 멘토링, MVP 제작비 50만원, 기술이전 특전 등) 정리

### Fixed

- `docs/07-roadmap.md`의 "2차 예선 통과 시 전원 수상" 메모가 공식 공고와 다름을
  확인 후 정정 (본선은 발표·시연 기반 경쟁 평가이며 최종 결과로 학생부/일반부
  각 6팀만 수상). 배경은 `docs/06-decisions.md` "2026-07-07 (3)" 항목 참고

## 2026-07-08

### Added

- **핵심 7개 조건 실제 학습·평가 완료** — KITTI Car 400장(학습)+120장(평가)로
  clean/width±30/height±30/rot±15 학습, `backend/app/data/metrics.csv`에 실측
  결과 반영 (목업 데이터 → 실제 데이터로 최초 교체)
- `docs/11-professor-feedback.md` — 김성호 교수님(영남대 AVIL) 기술 검토 회신 정리
  및 2차 예선 전 대응 방안 (포지셔닝 문구 변경, 회전각 오류 한계 인정, IoU 기반
  강도 지표 제안, ROI 정량화 등)
- `docs/12-experiment-results.md` — 실측 결과 분석: (1) 세 오류 유형 모두 성능
  저하 확인, (2) 회전각 오류가 가장 크고 양방향으로 대칭적인 저하를 보임 (교수님
  피드백의 "축정렬 재계산이 방향성을 지운다" 지적과 일치), (3) Precision은 거의
  불변, Recall만 뚜렷이 하락 — mAP 외 핵심 지표로 Recall 확인
- `docs/assets/experiment-results-priority1.png` — PPT에 바로 쓸 수 있는 조건별
  mAP@0.5·Recall 저하율 그래프

### Changed

- `run_all.py --priority 1` 실행 중 `clean`(50epoch) 완료 후 나머지 6개 조건은
  25epoch로 단축 (실제 학습 속도가 예상보다 느려 시간 리스크 관리 목적). 배경과
  트레이드오프는 `docs/06-decisions.md` "2026-07-08" 항목,
  `docs/12-experiment-results.md` "한계" 절 참고

### Next

- [ ] 교수님 피드백 액션 아이템 반영 (발표 스크립트 포지셔닝 변경 등)
- [ ] 세분화 6개 조건 실행 (`run_all.py --priority 2`)
- [ ] `clean` 25epoch 재실행으로 공정 비교 기준 확보 (선택)
- [ ] 2차 예선(2026-07-09~10) 발표 리허설
