# 09. 시작하기 (새 세션/새 개발자용 진입점)

이 문서는 새로운 대화 세션이나 새 팀원이 이 프로젝트를 이어받을 때 **가장 먼저**
읽어야 할 문서다. "지금 뭐가 되어 있고, 뭐가 안 되어 있고, 다음에 뭘 해야 하는지"만
간단히 정리한다. 배경 설명이 필요하면 [00-overview.md](./00-overview.md)부터.

## 지금까지 완료된 것 (2026-07-08 기준)

- [x] 발표자료(PPT) 40장 초안 — `../AIDA_발표자료_초안.pptx`
- [x] 기술 검증 실험 설계 확정 — [03-experiment-design.md](./03-experiment-design.md)
      (KITTI Car 클래스, 13개 오류 조건, YOLOv8n)
- [x] 교수님(김성호) 기술 검토 요청 메일 완성 및 **회신 도착** —
      [08-professor-review-email.md](./08-professor-review-email.md),
      [11-professor-feedback.md](./11-professor-feedback.md)
- [x] MVP 웹 대시보드 스캐폴딩 — `backend/`(FastAPI) + `frontend/`(React+TS)
- [x] `experiment/` 파이프라인 구현 및 **핵심 7개 조건 실제 학습·평가 완료**
      (KITTI 400+120장, YOLOv8n) — `backend/app/data/metrics.csv`에 실측 결과 반영됨,
      분석은 [12-experiment-results.md](./12-experiment-results.md) 참고
- [x] 공식 공고문 정리 — [10-competition-brief.md](./10-competition-brief.md)

## 아직 안 된 것 (다음에 할 일, 우선순위 순)

1. **교수님 피드백 반영** — [11-professor-feedback.md](./11-professor-feedback.md)의
   "2차 예선 전 실행 가능한 액션 아이템" 표 참고. 특히 우선순위 1~2번(포지셔닝
   문구 변경, 회전각 한계 선제 설명)은 코드 변경 없이 발표 스크립트만 손보면 됨
2. **세분화 6개 조건 실행** (선택, 시간 되면) — `width±15%, height±15%, rot±7.5°`
   ```bash
   cd experiment && source venv/bin/activate
   python run_all.py --priority 2 --skip-download --skip-preprocess
   ```
3. **`clean` 조건 25epoch로 재실행** (선택, ~15~20분) — 지금 clean은 50epoch,
   나머지 6개는 25epoch로 학습해 절대 저하율 수치에 편향이 있음
   ([12-experiment-results.md](./12-experiment-results.md) "한계" 참고). 공정 비교
   기준을 원하면 `python train.py --condition clean --epochs 25 --evaluate`
4. 2차 예선(2026-07-09~10) 발표 리허설, 결과 그래프
   (`docs/assets/experiment-results-priority1.png`) PPT에 반영, MVP 데모(프론트엔드)
   실제 시연 연습

## 실행 명령어 모음

```bash
# 백엔드
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 프론트엔드 (새 터미널)
cd frontend && npm run dev

# 실험 파이프라인 (핵심 7개 조건)
cd experiment && source venv/bin/activate
python run_all.py --priority 1
```

## 이 프로젝트를 처음 보는 AI 어시스턴트에게

이 저장소를 열었다면, 다음 순서로 컨텍스트를 파악할 것:
1. `docs/00-overview.md` — 뭘 만드는지
2. `docs/01-technology.md` — 왜 그 방식이 기술적으로 성립하는지 (특허 근거)
3. `docs/03-experiment-design.md` — 지금 검증하려는 실험이 정확히 무엇인지
4. `docs/06-decisions.md` — 왜 이런 선택을 했는지 (시행착오 포함)
5. 이 문서(`09-getting-started.md`)의 "아직 안 된 것" — 지금 이어서 할 작업

사용자가 "개발 시작하자"고 하면, 위 "아직 안 된 것" 1번(`experiment/` 폴더 구현)부터
시작하면 된다.
