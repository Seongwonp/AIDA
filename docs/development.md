# 개발 환경과 실행 절차

외부 개발자가 이 저장소를 받아 검사·실행·분석까지 돌리는 데 필요한 것만 적는다. 작업 상태나 다음
할 일은 여기 두지 않는다.

## 1. Python 환경은 둘로 나뉜다

| | 무엇이 있나 |
|---|---|
| `backend/venv` | FastAPI. torch 없음 |
| `experiment/venv` | torch·ultralytics·cleanlab. FastAPI 없음 |

`experiment/`의 스크립트와 `experiment/evaluation/` 집계 모듈은 `experiment/venv`로 돌린다. 집계 모듈은
표준 라이브러리만 쓰므로 backend 검사에서도 그대로 불러 쓴다.

```powershell
python -m venv backend\venv;    backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
python -m venv experiment\venv; experiment\venv\Scripts\python.exe -m pip install -r experiment\requirements.txt
cd frontend; npm install
```

GPU 없이 실험 검사만 돌리려면 `experiment/requirements-ci.txt`로 충분하다(CI와 같은 구성).

## 2. 검증 명령

```powershell
cd backend;    .\venv\Scripts\python.exe -m pytest tests -q
cd experiment; .\venv\Scripts\python.exe -m pytest tests -q
cd frontend;   npm test; npm run typecheck; npm run lint; npm run build
```

윈도우에서 사용자 경로에 한글이 있으면 pytest 임시 폴더가 실패할 수 있다 — `--basetemp=C:\aida_tmp\pt`처럼
ASCII 경로를 준다. 검사가 무엇을 잡고 무엇을 못 잡는지는 [testing-boundary.md](testing-boundary.md).

## 3. 서버 실행 (창 두 개, AIDA 루트에서)

```powershell
cd backend;  .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

```powershell
cd frontend; npm run dev
```

진단(추론)은 backend가 `experiment/venv`의 파이썬을 서브프로세스로 부른다. GPU가 있는 기계에서만 돈다.
컨테이너(`Dockerfile`)에서는 결과 열람만 되고 새 진단은 돌지 않는다.

## 4. 실행 기록용 환경 확인

자 가중치의 SHA-256과 cleanlab·ultralytics·torch 버전을 JSON으로 남긴다. 가중치가 없으면 `sha256`이
`null`로 나오고 다른 자로 대체하지 않는다.

```powershell
.\experiment\venv\Scripts\python.exe .\experiment\check_run_environment.py --out .\experiment\planning_evidence\environment.json
```

## 5. 평가 묶음과 판정 화면

- 업로드 → `POST /api/datasets/{id}/diagnose-labels?ranking=aida_v2_candidate_iou&ruler=nuimages_car_v1_e100`
  (응답의 `ruler.weights_sha256`이 4절의 값과 같아야 한다).
- 묶음 생성 `POST /api/datasets/{id}/evaluations` — 본문 항목은 [qa-preregistration.md](qa-preregistration.md)와
  [qa-preregistration-proposal-2026-09-27.md](qa-preregistration-proposal-2026-09-27.md) 참고. 묶음은 덮어쓰지 않는다.
- 판정 화면 `http://localhost:5173/?evaluate=<dataset_id>:<evaluation_id>`. 버튼은 오류 있음(1)·오류 없음(2)·판단 보류(3).
- 보조 판정자 입력 그림: `GET .../queue?adjudicator=<id>` 결과를 `experiment/render_adjudication_images.py`에 넣는다.
- 연습은 [practice-judging-plan.md](practice-judging-plan.md)를 따른다(train fit_check만, val은 사전 등록 확정 전 열지 않는다).

## 6. 최종 분석

판정을 모두 마친 뒤에만 실행한다. 묶음의 coverage 설정·입력 지문과 인자가 다르거나 고정 재표본·원래 상위 N에
미판정이 있으면 중단한다.

```powershell
.\experiment\venv\Scripts\python.exe .\experiment\analyze_qa.py --export labelled_primary.json --budget 90 --iterations 2000 --seed 42 --methods aida all_label_iou all_label_objectlab --adjudicator primary --out qa_result.json
```

## 7. 보호 자료

`backend/app/data/uploads/`, `experiment/data/`, `experiment/runs*/`는 git 밖이다. 얼린 묶음(`snapshot.json`)·
판정 원본(`adjudications*.json`)·사전 등록 파일은 지우거나 고치지 않는다. 실행 기록은 [qa-run-record.md](qa-run-record.md).
