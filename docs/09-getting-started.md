# 09. 시작하기 (새 세션/새 개발자용 진입점)

이 문서는 새로운 대화 세션이나 새 팀원이 이 프로젝트를 이어받을 때 **가장 먼저**
읽어야 할 문서다. "지금 뭐가 되어 있고, 뭐가 안 되어 있고, 다음에 뭘 해야 하는지"만
간단히 정리한다. 배경 설명이 필요하면 [00-overview.md](./00-overview.md)부터.

## 지금까지 완료된 것 (2026-07-07 기준)

- [x] 발표자료(PPT) 40장 초안 — `../AIDA_발표자료_초안.pptx`
- [x] 기술 검증 실험 설계 확정 — [03-experiment-design.md](./03-experiment-design.md)
      (KITTI Car 클래스, 13개 오류 조건, YOLOv8n)
- [x] 교수님(김성호) 기술 검토 요청 메일 완성 — [08-professor-review-email.md](./08-professor-review-email.md)
- [x] MVP 웹 대시보드 스캐폴딩 — `backend/`(FastAPI) + `frontend/`(React+TS), **목업
      데이터로 구동 확인 완료**
- [x] `experiment/` 폴더 구현 완료 — KITTI 다운로드(Range 요청 부분 다운로드) →
      전처리 → 에러 라벨 생성(13개 조건) → YOLOv8n 학습·평가 → `metrics.csv` 자동
      갱신까지 전체 파이프라인. 작은 샘플(16장, 1 epoch)로 스모크 테스트 통과 확인.
      **아직 실제 규모(400+120장, 13개 조건 풀 학습)로는 실행 안 함** — 아래 참고

## 아직 안 된 것 (다음에 할 일, 우선순위 순)

1. **`experiment/` 실제 규모 실행** — 코드는 완성됨, 실행만 남음
   ```bash
   cd experiment && source venv/bin/activate
   python run_all.py --priority 1     # 핵심 7개 먼저 (clean, width±30, height±30, rot±15)
   python run_all.py --priority 2     # 시간 남으면 세분화 6개 이어서
   ```
   예상 소요: 이미지 다운로드(약 520장, Range 요청) 10~20분 + 조건당 학습 10~20분
   (M1 MPS 기준) × 13 ≈ 2~4시간. `--priority 1`만으로도 핵심 가설 검증 가능.
   완료되면 `backend/app/data/metrics.csv`가 자동으로 실제 결과로 갱신됨(수동 교체 불필요).
2. 교수님 회신 반영 → 실험 설계/오류 유형 조정 필요 시 [06-decisions.md](./06-decisions.md)에
   새 결정 기록
3. 2차 예선(2026-07-09~10) 발표 리허설, MVP 데모(프론트엔드) 실제 시연 연습

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
