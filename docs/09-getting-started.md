# 09. 새로 이어받는 사람을 위한 진입점

새 세션이나 새 개발자가 이 프로젝트를 이어받을 때 **이 문서부터** 읽으면 된다.

## 이 프로젝트가 지금 무엇인가

객체탐지 학습데이터의 **바운딩박스 라벨 오류를 진단해 재검수 우선순위를 주는**
연구 프로토타입이다. 국방과학연구소 특허(10-2664201)의 방법을 쓴다.

2026-08-19에 창업경진대회 2차 예선에서 떨어졌고, **그 뒤로는 발표 준비가 아니라
기술을 실제로 검증하는 쪽**으로 방향을 바꿨다. 대회 관련 문서(07·10·11·13~19번)는
그때의 기록이라 갱신하지 않는다.

## 5분이면 파악되는 순서

1. **저장소 [README](../README.md)의 "지금 어디까지 왔나"** — 무엇이 되고
   무엇이 안 되는지. 여기부터.
2. **[25번 고도화 계획](25-advancement-roadmap.md)** — 현재 작업과 완료 조건. 데스크탑 실행 안내는 [CLAUDE.md](../CLAUDE.md).
3. **[현재 근거표](current-evidence.md)**와 **[검사 경계](testing-boundary.md)** — 성능 주장과 검증 범위를 구분한다. 세부 실험 이력은 [21번](21-next-plan.md), 변경 이력은 [CHANGELOG](../CHANGELOG.md).
4. 배경이 필요하면 [00-overview.md](./00-overview.md), 원리는
   [01-technology.md](./01-technology.md).

## 지금까지 확인된 가장 중요한 사실

**기준 모델("자")의 적합성이 진단 품질에 큰 영향을 주었다.** COCO 평가에서 모델을 바꾼 비교는 다음과 같다:

| 자 | 상위 10% | 근거 |
|---|---|---|
| COCO 자기 도메인 모델 | **82.4%** | 21번 AI (조건 26개 · 시드 3개) |
| KITTI 모델 → COCO 평가 | **26.0%** | 같은 실험 |

실무에서 유용한지는 오류 빈도와 검수 비용까지 비교해야 하며 아직 미검증이다.
KITTI의 94.0%는 별도 조건의 결과로 이 표와 직접 비교하지 않는다. 제품은 어느 자로 쟀는지 숨기지 않고, 그 자가
이 데이터를 실제로 보고 있는지(라벨 중 몇 %를 짚었는지)까지 보여준다.

## 이 프로젝트에서 반복해서 난 사고

새로 작업할 때 같은 함정을 밟지 않도록 적어둔다. 전부 **오류 없이 조용히
틀리는** 종류다.

- **하드코딩된 조건 목록이 새 조건군을 놓친다.** 네 번 났다. 조건을 이름으로
  찾을 때는 `config._BY_NAME`을 쓸 것.
- **경로에 차원이 빠지면 다른 실험 결과를 덮는다.** 클래스 구성·프레임 선택·
  규모·데이터셋이 전부 접미사에 들어간다. `check_consistency.py`가 잡는다.
- **깨진 심볼릭 링크를 학습이 조용히 건너뛴다.** ultralytics는 읽을 수 없는
  파일을 "corrupt"로 세고 넘어가므로, 빈 데이터셋으로 학습이 성공한다.
- **결과가 소수점까지 같으면 의심할 것.** 이 프로젝트에서 조용한 실패를
  잡아준 신호가 매번 이것이었다.
- **점 두세 개로 추세를 그리지 말 것.** X가 두 점으로 그은 직선이 네 점에서
  틀렸고, 나도 세 점으로 같은 실수를 할 뻔했다(21번 AJ).

## 실행

저장소 [README](../README.md)의 "실행 방법"에 백엔드·프론트엔드·실험
파이프라인 명령이 다 있다. 요약하면:

```bash
# 백엔드
cd backend && ./venv/Scripts/python.exe -m uvicorn app.main:app --reload

# 프론트엔드
cd frontend && npm run dev        # http://localhost:5173

# 검증
cd backend && ./venv/Scripts/python.exe -m pytest tests -q
cd frontend && npm run typecheck  # tsc -b — tsc --noEmit는 아무것도 안 본다
cd frontend && npm run lint && npm test
cd experiment && ./venv/Scripts/python.exe check_consistency.py   # 느리다(수십 분)
```

CI 구성은 `.github/workflows/ci.yml`을 따른다. 백엔드·프론트 검사와 빌드 외에
GPU 없는 실험 로직 검사도 포함된다. 실제 모델 추론과 원본 데이터가 필요한
`check_consistency.py`는 별도 로컬 검증이다. 상세 범위는 [검사 경계](testing-boundary.md)를 참고한다.

**검사는 어디서 돌리든 같은 결과가 나와야 한다.** 예전에는 학습된 자가 있는
이 기계에서만 통과하고 CI에서는 5건이 건너뛰어졌다. 지금은
`tests/fake_experiment.py`가 자리표시자 자(빈 `best.pt`)와 torch 없는 가짜
진단 스크립트로 experiment 경계를 흉내 내므로 **건너뛰는 것이 없다.**

새 검사를 쓸 때도 그렇게 해야 한다 — 진짜 가중치가 필요하면 `fake_experiment`
fixture를 쓰고, 로컬 파일 존재 여부로 갈라지게 두지 말 것.

여전히 안 보는 것은 **추론 자체**다. GPU가 필요하고 CI에서 못 한다. 배선이
맞는지는 보지만 진단이 맞는지는 안 본다 — 그 구분을 흐리면 안 된다.
여기서는 자가 있으니 통과하는데 CI에서는 없다 — 그래서 "여기서만 통과하는 검사"가
생기지 않도록, 자가 필요하면 건너뛰게 해뒀다. 새 검사를 쓸 때도 같게 해야 한다.
로컬에서 CI 환경을 흉내 내려면:

```bash
cd backend && EXPERIMENT_ROOT=/tmp/empty ./venv/Scripts/python.exe -m pytest tests -q
```

실험 산출물(조건 폴더·원본 데이터)은 `D:\AIDA-data\experiment`에 있고
`experiment/` 아래 디렉터리 정션으로 연결돼 있다. 경로는 그대로 동작한다.

## 다른 기기에서 새로 clone한 경우

git에는 코드와 문서가 다 있지만 `.gitignore`된 것들은 새로 만들어야 한다 —
venv 두 개, `.env`, KITTI/COCO 원본, 학습 결과물(`runs*`), 조건 폴더
(`conditions*`). 조건 폴더는 `data_loader.py` → `error_injector.py`로
다시 만들 수 있고, 학습은 GPU 시간이 든다.

## 다음에 할 일

[21-next-plan.md](./21-next-plan.md) 끝의 "다음 할 일" 절에 비용순으로
정리돼 있다. 5개 후보 중 1~5번은 끝났고, 각 절의 "남은 한계"가 다음 후보다.
