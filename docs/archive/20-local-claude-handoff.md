---

# 로컬 Claude에게 — OBB 파이프라인 실행 + 다음 계획 수립

## 먼저 할 것 (순서대로)

```bash
# 1. 최신 코드 받기
cd <AIDA 프로젝트 루트>
git pull

# 2. 스모크 테스트 (1epoch짜리, 파이프라인 전체 흐름 확인용)
cd experiment
source venv/bin/activate  # Windows: venv\Scripts\activate
AIDA_N_TRAIN=20 AIDA_N_VAL=10 python run_obb.py --epochs 1

# 3. 스모크 통과하면 본 실험
python run_obb.py
```

스모크 테스트가 실패하면 아래 체크리스트 확인:
- `yolov8n-obb.pt` 다운로드 시도 시 인터넷 연결 필요
- KITTI 데이터 (`experiment/data/raw/`) 가 있어야 함 — 없으면 `python download_kitti.py` 먼저
- AABB 실험 데이터 (`experiment/data/processed/images/`) 가 있어야 함 — 없으면 `python data_loader.py` 먼저
- 에러 메시지 보고 원인 파악 후 수정

본 실험 완료 후:
- `backend/app/data/metrics_obb.csv` 생성 확인
- 백엔드 + 프론트엔드 띄우고 대시보드에서 "OBB vs AABB 회전 오류 비교" 차트 확인

---

## 프로젝트 컨텍스트

AIDA는 객체탐지 AI 학습데이터의 바운딩박스 라벨 오류를 자동 진단하는 B2B 플랫폼이다.
국방과학연구소 특허(10-2664201) 기반, KITTI 데이터셋으로 YOLOv8n을 조건별 학습해
성능 저하 패턴으로 오류 유형을 진단한다.

**기존 결과 (AABB, 21개 조건, 완료):**
- `backend/app/data/metrics.csv` — 절대 건드리지 말 것
- 회전 오류의 한계: `rot_p15`와 `rot_m15` mAP 저하율이 거의 같음 (방향성 소실)

**이번 추가 (OBB, 5개 조건, 실행 대기 중):**
- YOLO OBB 라벨 포맷: `class x1 y1 x2 y2 x3 y3 x4 y4` (polygon 꼭짓점)
- 핵심 차이: 회전 오류를 AABB 외접 박스가 아니라 rotated polygon으로 저장
  → `obb_rot_p15`와 `obb_rot_m15`가 서로 다른 polygon = 방향성 보존
- 결과는 `backend/app/data/metrics_obb.csv`에 저장
- 대시보드에 AABB vs OBB 비교 차트 이미 추가되어 있음

---

## OBB 실험 완료 후: 다음 계획 수립

OBB 본 실험이 끝나면, 아래 질문들을 바탕으로 **다음 고도화 계획을 직접 수립하고 `docs/21-next-plan.md`로 저장**해줘.

### 질문 1: OBB 결과 분석

`metrics_obb.csv`를 읽어서:
- `obb_rot_p15` vs `obb_rot_m15` 저하율 차이가 실제로 생겼는가? (있으면 OBB 도입 정당화)
- AABB `rot_p15/m15` 저하율 vs OBB `obb_rot_p15/m15` 저하율 비교
- 전체적으로 AABB 대비 OBB의 성능 저하가 더 크거나 작은가? 이유는?

### 질문 2: 다음 기술 방향 세 가지 후보

아래 세 방향 중 지금 AIDA의 기술 수준과 임팩트를 고려해 우선순위를 매기고 이유를 설명해줘:

**A. 다중 seed 반복 실험**
- 현재 모든 실험이 seed=42 단 하나
- seed 3~5개로 반복해 평균±표준편차 구하기
- 논문/특허 수준 통계 신뢰도 확보
- 필요 시간: AABB 21조건 × 3 seed = 63회 학습 (CUDA 기준 6~12시간 추가)

**B. 새 오류 유형: 중복 박스 / 누락 박스**
- 현재 오류 유형: 기하학적(크기/위치/회전) → 라벨이 있긴 하지만 위치가 틀린 케이스
- 추가 후보: duplicate (같은 위치에 박스 2개), missing (일부 객체를 아예 라벨링 안 함)
- B2B 고객이 실제로 자주 겪는 오류 유형 확장
- 구현 난이도: 중간 (error_injector.py에 새 함수 추가)

**C. 실제 데이터 업로드 기능**
- 현재 대시보드는 KITTI 실험 결과만 보여줌 (데모 수준)
- 고객이 자기 라벨 파일을 올리면 진단해주는 실제 B2B 흐름
- 구현 범위: 파일 업로드 API, 오류 주입 + 학습 + 평가 파이프라인 자동화, 결과 리포트 다운로드
- 가장 큰 임팩트이지만 구현 범위도 가장 큼

### 계획서 형식 (`docs/21-next-plan.md`)

```markdown
# 21. 다음 고도화 계획

## OBB 실험 결과 요약
(실측 수치 기반으로 채울 것)

## 다음 방향 우선순위
1. (선택한 방향) — 이유
2. ...

## 선택 방향 구체 실행 계획
- 무엇을: ...
- 어떻게: (파일/함수 단위)
- 예상 시간: ...
```

계획 수립 후 git commit 해줘 (메시지: "docs: add OBB results and next plan").

---

## 참고: 현재 코드 구조

```
experiment/
  config.py          # OBB 조건/경로 포함 (이미 추가됨)
  data_loader.py     # main_obb() 추가됨
  error_injector.py  # rotate_obb_poly() 등 OBB 함수 추가됨
  train_obb.py       # yolov8n-obb.pt 학습 (신규)
  evaluate_obb.py    # OBB 평가 (신규)
  run_obb.py         # 파이프라인 진입점 (신규)

backend/app/
  config.py          # OBB_METRICS_CSV_PATH 추가됨
  routers/report.py  # /api/obb/conditions 엔드포인트 추가됨

frontend/src/
  api.ts             # getObbConditions() 추가됨
  components/ObbComparisonChart.tsx  # 비교 차트 (신규)
  App.tsx            # ObbComparisonChart 추가됨
```

---

