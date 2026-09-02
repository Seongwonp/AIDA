# 09. 시작하기 (새 세션/새 개발자용 진입점)

이 문서는 새로운 대화 세션이나 새 팀원이 이 프로젝트를 이어받을 때 **가장 먼저**
읽어야 할 문서다. "지금 뭐가 되어 있고, 뭐가 안 되어 있고, 다음에 뭘 해야 하는지"만
간단히 정리한다. 배경 설명이 필요하면 [00-overview.md](./00-overview.md)부터.

## 지금까지 완료된 것 (2026-07-08 기준)

- [x] **21개 오류 조건 전부, 동일 50epoch로 실측 완료** (CUDA 데스크탑, KITTI Car
      400+120장, YOLOv8n) — `backend/app/data/metrics.csv`에 반영, 통합 결과표와
      분석은 [17-professor-feedback-response.md](./17-professor-feedback-response.md) 참고.
      교수님 피드백을 받아 중심점 이동(translation)·스케일(scale) 조건을 추가해
      기존 13개 → 21개로 확장했고, IoU 감소율 지표도 계산해 전체 API·대시보드에 통합함
- [x] 발표자료(PPT) **29장** — 최신본은
      `../AIDA_2차예선_발표자료_완성본_화이트톤_29장_20260708.pptx`
      (26장본은 `..._26장_20260708.pptx`로 그대로 보존). 목차 슬라이드, 제도적
      정합성 슬라이드 2장(데이터산업법 제20조, TTA 품질지표기준서 "제3자
      품질검증" 프로세스 매핑) 추가, 실측 21개 조건 그래프·ROI·대시보드 반영,
      전체 톤 다듬기 완료(상투적 AI 말투 잔여분 3곳 수정: 8·18·28번 슬라이드)
- [x] 별도 사업계획서형 리포트(`Documents/카카오톡 받은 파일/발표자료.hwpx`,
      **원래대로 12개 섹션** — 문제제기·기존방식한계·AIDA소개·국방기술활용·
      MVP구현및검증계획·결과물·고객구조수요·사업모델·시장성성장전략·리스크대응·
      팀역량실행계획·마무리. 중간에 "10개 섹션"으로 잘못 재구성한 적 있는데,
      그건 사용자가 잘못된 목차 이미지를 보내서 생긴 착오였고 폐기함) — 1~6번은
      hwpx 원문 그대로, 7~12번(고객구조/수요, 사업모델, 시장성/성장전략, 리스크
      대응, 팀역량/실행계획, 마무리)은 새로 써서 12개 섹션 전체를
      [19-report-sections-6-12-draft.md](./19-report-sections-6-12-draft.md)에
      작성해둠 — hwpx에 그대로 옮겨 붙이면 됨. **주의**: 같은 폴더의
      `발표자료.pdf`는 내보내기가 끊긴 1페이지짜리 불완전한 파일이니 참고하지
      말 것 (hwpx 원본이 진본)
- [x] 기술 검증 실험 설계 확정 — [03-experiment-design.md](./03-experiment-design.md)
- [x] 교수님(김성호) 기술 검토 요청 메일 완성 및 **회신 도착, 4개 지적사항 100% 반영** —
      [08-professor-review-email.md](./08-professor-review-email.md),
      [11-professor-feedback.md](./11-professor-feedback.md),
      [17-professor-feedback-response.md](./17-professor-feedback-response.md)
- [x] MVP 웹 대시보드 — `backend/`(FastAPI) + `frontend/`(React+TS), ROI 추정 카드·
      IoU 감소율 컬럼·CSV 다운로드까지 구현 완료
- [x] 공식 공고문 정리 — [10-competition-brief.md](./10-competition-brief.md)
- [x] 테스트 코드 — `backend/tests/`, `experiment/tests/`(pytest).
      `python -m pytest tests/ -v`로 각 폴더에서 실행
- [x] `experiment/config.py`의 학습 디바이스를 `AIDA_DEVICE=auto`로 자동 감지

## 아직 안 된 것 (다음에 할 일)

> 2026-08-19 창업경진대회 2차 예선에서 탈락했다. **PPT·발표 준비 작업은 전부
> 죽었다.** 이 문서의 이 절이 한동안 그 목록을 담고 있어서, 새로 이어받는
> 사람이 죽은 작업을 하러 갈 위험이 있었다. 지금 목록은 제품 개발 기준이다.
> 개선 이력과 실측 근거는 [21-next-plan.md](./21-next-plan.md)의 A~U 절.

1. **다중 클래스 3-seed** (약 7시간, GPU) — L~U의 다중 클래스 수치가 전부
   단일 관측이다. 단일 관측을 믿었다가 두 번 데였다: S는 데이터 오염으로
   결론이 뒤집혔고, T는 1회차에서 불가능한 값(상한 초과)이 나왔다.
   `AIDA_TRAIN_SEED`/`AIDA_RUN_SUFFIX`로 반복 실행이 가능하다.

2. **고객 도메인용 기준 모델** — 지금 박스 단위 진단은
   `runs/clean/weights/best.pt`(KITTI Car 학습)를 자로 쓴다. 고객 데이터가
   KITTI와 다르면 그 자가 안 맞는다. 이게 제품의 가장 큰 구조적 한계다.
   고객 데이터로 기준 모델을 학습하거나 가져오게 하는 경로가 필요하다.

3. **취약도 추정의 대안 신호** — S에서 클래스 개수만으로는 안 된다는 걸
   확인했다. clean 모델의 클래스별 mAP가 후보지만, T에서 클래스 가중 정렬이
   severity보다 낫지 않다고 나와 우선순위는 내려갔다.

## 실행 명령어 모음

```bash
# 백엔드
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 프론트엔드 (새 터미널)
cd frontend && npm run dev

# 실험 파이프라인 (27개 조건 전부 — 이미 완료됨, 재실행 시에만 사용)
cd experiment && source venv/bin/activate
python run_all.py --priority all

# 테스트
cd backend && source venv/bin/activate && python -m pytest tests/ -v
cd experiment && source venv/bin/activate && python -m pytest tests/ -v
```

### 다중 클래스 실험 (docs/21 L·Q)

클래스 구성이 바뀌면 라벨·가중치·지표 경로가 전부 분리된다(`_mc` 접미사).
Car 단일 결과를 덮어쓰지 않으므로 그냥 돌리면 된다.

```bash
cd experiment && source venv/bin/activate
export AIDA_CLASSES="Car,Van,Pedestrian,Cyclist"

python data_loader.py && python error_injector.py
# 유형마다 하나씩 먼저 끝내고, 중간에 끊기면 같은 명령으로 이어서 돈다
python run_all.py --skip-download --skip-preprocess --breadth-first --skip-done
```

### 진단 품질 측정

```bash
cd experiment && source venv/bin/activate

# 박스 단위 정확도 (조건당 수 분)
python evaluate_box_accuracy.py --limit 80
# 심각도 공식만 바꿨다면 추론을 건너뛴다 (20분 → 2초)
python evaluate_box_accuracy.py --limit 80 --reuse-cache

# 유형 신뢰도를 이 도메인에서 다시 재 프로파일로 저장
python evaluate_box_accuracy.py --limit 80 --write-profile reliability_profile_mc.json
export AIDA_RELIABILITY_PROFILE=$PWD/reliability_profile_mc.json

# 클래스별 mAP → 클래스 취약도
python evaluate_per_class.py
python build_class_vulnerability.py --profile reliability_profile_mc.json

# 클래스 구성 간 성능 저하 비교
python compare_class_configs.py
```

### 정리

```bash
# 안 쓰는 학습 산출물(last.pt·배치 이미지) 회수. 기본은 보고만 한다
cd experiment && python cleanup_runs.py
python cleanup_runs.py --delete
```

## 이 프로젝트를 처음 보는 AI 어시스턴트에게

이 저장소를 열었다면, 다음 순서로 컨텍스트를 파악할 것:
1. `docs/00-overview.md` — 뭘 만드는지
2. `docs/01-technology.md` — 왜 그 방식이 기술적으로 성립하는지 (특허 근거)
3. `docs/03-experiment-design.md` — 지금 검증하려는 실험이 정확히 무엇인지
4. `docs/06-decisions.md` — 왜 이런 선택을 했는지 (시행착오 포함, 최신 항목이 맨 아래)
5. `docs/17-professor-feedback-response.md` — 21개 조건 실측 결과와 교수님 피드백 반영 내역
6. 이 문서(`09-getting-started.md`)의 "아직 안 된 것" — 지금 이어서 할 작업

**다른 기기에서 이 저장소를 새로 clone해 이어받은 경우**: git 커밋 이력에 모든
코드·문서가 있지만, `.gitignore`된 것들(venv, `.env`, KITTI 원본 데이터, 학습
결과물)은 새로 만들어야 한다.

**PPT(`../AIDA_2차예선_발표자료_완성본_화이트톤_29장_20260708.pptx`)와 사업계획서형
리포트(`Documents/카카오톡 받은 파일/발표자료.hwpx`)는 이 git 저장소 밖에 있다** —
경로는 위 "지금까지 완료된 것"과
[19-report-sections-6-12-draft.md](./19-report-sections-6-12-draft.md) 참고.

사용자가 "개발 시작하자"/"이어서 하자"고 하면, 위 "아직 안 된 것" 목록부터
시작하면 된다.
