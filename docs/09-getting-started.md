# 09. 시작하기 (새 세션/새 개발자용 진입점)

이 문서는 새로운 대화 세션이나 새 팀원이 이 프로젝트를 이어받을 때 **가장 먼저**
읽어야 할 문서다. "지금 뭐가 되어 있고, 뭐가 안 되어 있고, 다음에 뭘 해야 하는지"만
간단히 정리한다. 배경 설명이 필요하면 [00-overview.md](./00-overview.md)부터.

## 지금까지 완료된 것 (2026-07-08 기준)

- [x] 발표자료(PPT) 41장 — 최신본은 `../AIDA_발표자료_v2(결과반영).pptx`
      (원본 `../AIDA_발표자료_초안.pptx`는 그대로 보존, 덮어쓰지 않음). 실측 결과
      그래프·대시보드 스크린샷·ROI 슬라이드·완화된 진단 문구 반영 완료
- [x] 기술 검증 실험 설계 확정 — [03-experiment-design.md](./03-experiment-design.md)
      (KITTI Car 클래스, 13개 오류 조건, YOLOv8n)
- [x] 교수님(김성호) 기술 검토 요청 메일 완성 및 **회신 도착** —
      [08-professor-review-email.md](./08-professor-review-email.md),
      [11-professor-feedback.md](./11-professor-feedback.md)
- [x] MVP 웹 대시보드 스캐폴딩 — `backend/`(FastAPI) + `frontend/`(React+TS)
- [x] `experiment/` 파이프라인 구현 및 **핵심 7개 조건 실제 학습·평가 완료**
      (KITTI 400+120장, YOLOv8n, M1 Mac MPS) — `backend/app/data/metrics.csv`에
      실측 결과 반영됨, 분석은 [12-experiment-results.md](./12-experiment-results.md) 참고.
      단, 시간 제약으로 `clean`만 50epoch·나머지 6개는 25epoch로 학습해 절대 저하율에
      편향 있음 (조건 간 상대 비교는 유효) — 아래 "다음에 할 일" 1번에서 해결 예정
- [x] 공식 공고문 정리 — [10-competition-brief.md](./10-competition-brief.md)
- [x] 테스트 코드 — `backend/tests/`(pytest 12개, API·진단 로직),
      `experiment/tests/`(pytest 8개, 오류 라벨 변형 좌표 계산 로직).
      `python -m pytest tests/ -v`로 각 폴더에서 실행
- [x] `experiment/config.py`의 학습 디바이스를 `AIDA_DEVICE=auto`로 자동 감지하도록
      변경 (`cuda > mps > cpu` 순). M1 Mac과 CUDA 데스크탑(RTX 3050) 양쪽에서 `.env`
      수정 없이 동일하게 최적 디바이스로 학습됨

## 아직 안 된 것 (다음에 할 일, 우선순위 순)

1. **13개 조건 전부, 동일 epoch(50)로 재실행** — CUDA 데스크탑(RTX 3050)에서 진행 중/예정.
   M1에서는 시간 제약으로 조건마다 epoch을 다르게 줄여야 했는데(위 참고), CUDA가
   훨씬 빠르므로 이번엔 13개 전부 동일 조건으로 다시 돌려 그 한계를 없앤다.
   ```bash
   cd experiment
   python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env   # AIDA_DEVICE=auto가 cuda를 자동으로 잡음
   python -c "import torch; print(torch.cuda.is_available())"  # True 확인 후 진행
   python run_all.py --priority all
   ```
   KITTI 원본 데이터는 `.gitignore`돼 있어 clone 후 새로 받아야 함(Range 요청으로
   부분 다운로드, ~20분) → 13개 조건 학습(CUDA 기준 M1보다 훨씬 빠를 것으로 예상,
   조건당 수 분대 예상이나 실측 전까지는 추정치). 끝나면
   `backend/app/data/metrics.csv`와 [12-experiment-results.md](./12-experiment-results.md)를
   새 결과로 갱신할 것 (특히 "한계" 절의 epoch 불일치 항목 제거)
2. **교수님 피드백 기술 반영** — [11-professor-feedback.md](./11-professor-feedback.md)의
   "2차 예선 전 실행 가능한 액션 아이템" 표 참고. 포지셔닝 문구 변경·회전각 한계
   선제 설명은 이미 PPT에 반영됨(위 참고). 남은 것: IoU 기반 오류강도 지표 계산,
   회전각 오류 재설계(OBB 도입 또는 중심점이동·스케일 교체) — 본선(7/31) 전 검토
3. 2차 예선(2026-07-09~10) 발표 리허설, MVP 데모(프론트엔드) 실제 시연 연습

## 실행 명령어 모음

```bash
# 백엔드
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 프론트엔드 (새 터미널)
cd frontend && npm run dev

# 실험 파이프라인 (13개 조건 전부, 동일 epoch)
cd experiment && source venv/bin/activate
python run_all.py --priority all

# 테스트
cd backend && source venv/bin/activate && python -m pytest tests/ -v
cd experiment && source venv/bin/activate && python -m pytest tests/ -v
```

## 이 프로젝트를 처음 보는 AI 어시스턴트에게

이 저장소를 열었다면, 다음 순서로 컨텍스트를 파악할 것:
1. `docs/00-overview.md` — 뭘 만드는지
2. `docs/01-technology.md` — 왜 그 방식이 기술적으로 성립하는지 (특허 근거)
3. `docs/03-experiment-design.md` — 지금 검증하려는 실험이 정확히 무엇인지
4. `docs/06-decisions.md` — 왜 이런 선택을 했는지 (시행착오 포함, 최신 항목이 맨 아래)
5. `docs/12-experiment-results.md` — 지금까지 나온 실측 결과와 한계
6. 이 문서(`09-getting-started.md`)의 "아직 안 된 것" — 지금 이어서 할 작업

**다른 기기(예: CUDA 데스크탑)에서 이 저장소를 새로 clone해 이어받은 경우**: git
커밋 이력에 모든 코드·문서가 있지만, `.gitignore`된 것들(venv, `.env`, KITTI 원본
데이터, 학습 결과물)은 새로 만들어야 한다 — 위 "아직 안 된 것" 1번의 셋업 명령을
그대로 따라가면 된다.

사용자가 "개발 시작하자"/"이어서 하자"고 하면, 위 "아직 안 된 것" 1번(13개 조건
동일 epoch 재실행)부터 시작하면 된다.
