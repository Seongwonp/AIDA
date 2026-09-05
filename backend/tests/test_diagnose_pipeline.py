"""업로드 → 진단 서브프로세스 → 응답. 제품의 핵심 경로다.

**CI에서 한 번도 안 타던 길이다.** 진단은 backend가 아니라 experiment/venv에서
서브프로세스로 도는데(torch를 backend에 안 얹으려고), 그 경계를 넘는 검사가
하나도 없었다. 넘겨주는 것(인자·cwd·환경변수)이 틀려도, 받아오는 JSON의 모양이
달라져도 아무도 모른다.

여기서는 `EXPERIMENT_PYTHON`을 지금 돌고 있는 파이썬으로, 스크립트를 torch 없는
가짜로 바꿔서 **진짜 서브프로세스를 띄운다.** 그러면 배선 전체가 실제로 탄다.

**보지 않는 것: 추론 자체.** 그건 GPU가 필요하고 CI에서 못 한다. 여기서 보는
것은 "배선이 맞는가"지 "진단이 맞는가"가 아니다 — 그 구분을 흐리면 안 된다.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import upload
from tests import fake_experiment as fake


@pytest.fixture
def wired(fake_experiment, monkeypatch):
    """가짜 experiment가 걸린 상태에서 데이터셋 하나를 올려 둔다."""
    root, uploads = fake_experiment
    dataset_id = "abcdef123456"
    ds = uploads / dataset_id
    (ds / "images").mkdir(parents=True)
    (ds / "labels").mkdir(parents=True)
    (ds / "images" / "a.png").write_bytes(b"\x89PNG")
    (ds / "labels" / "a.txt").write_text("0 0.5 0.5 0.2 0.2", encoding="utf-8")

    # 가짜 스크립트가 결과를 어디에 쓸지, 무엇을 쓸지 알려준다
    monkeypatch.setenv("FAKE_UPLOADS_DIR", str(uploads))
    monkeypatch.setenv("FAKE_DIAGNOSIS_JSON",
                       json.dumps(fake.diagnosis_payload(dataset_id), ensure_ascii=False))
    return TestClient(app), dataset_id, uploads


def test_label_diagnosis_runs_end_to_end(wired):
    """업로드된 데이터셋 → 서브프로세스 → 응답 모델까지 실제로 간다."""
    client, dataset_id, _ = wired
    res = client.post(f"/api/datasets/{dataset_id}/diagnose-labels")
    assert res.status_code == 200, res.text

    body = res.json()
    assert body["dataset_id"] == dataset_id
    assert body["total_findings"] == 2
    assert len(body["review_queue"]) == 2
    # 한글 라벨로 옮겨졌는가 (SUSPICION_LABELS를 실제로 탄다)
    assert body["dominant_label"] == "가로 길이 어긋남"
    assert body["review_queue"][0]["label"] == "가로 길이 어긋남"
    # 누락 의심은 가리킬 라벨도 좌표도 없다
    assert body["review_queue"][1]["label_index"] is None
    assert body["review_queue"][1]["box"] is None
    # 좌표가 있는 건 그대로 실려 왔는가 (미리보기가 이걸 쓴다)
    assert body["review_queue"][0]["box"] == [10.0, 20.0, 110.0, 220.0]


def test_what_backend_hands_to_the_subprocess(wired):
    """넘겨주는 것이 계약이다. 인자 이름 하나만 바뀌어도 진단이 안 돈다."""
    client, dataset_id, uploads = wired
    client.post(f"/api/datasets/{dataset_id}/diagnose-labels")

    call = json.loads((uploads / dataset_id / "stub_call.json").read_text(encoding="utf-8"))
    assert call["argv"] == ["--upload-id", dataset_id]
    # cwd가 experiment 루트여야 한다 — 스크립트가 상대 경로로 config를 읽는다
    assert call["cwd"].endswith("experiment")
    # 프로파일을 안 골랐으면 아무것도 안 넘긴다 (기본 기준 모델)
    assert call["profile"] is None


def test_profile_choice_reaches_the_subprocess(wired):
    """프로파일을 고르면 상수와 **클래스 구성**이 같이 넘어가야 한다.

    상수만 갈아끼우고 클래스가 그대로면 엉뚱한 자로 잰 결과가 그 프로파일
    이름을 달고 나온다 (docs/21 AI에서 26.0%까지 무너졌다).
    """
    client, dataset_id, uploads = wired
    res = client.post(f"/api/datasets/{dataset_id}/diagnose-labels?profile=mc")
    assert res.status_code == 200, res.text

    call = json.loads((uploads / dataset_id / "stub_call.json").read_text(encoding="utf-8"))
    assert call["profile"].endswith("reliability_profile_mc.json")
    assert call["classes"] == "Car,Van,Pedestrian,Cyclist"


def test_ruler_sidecar_is_written_before_the_run(wired):
    """진단이 끝난 뒤에는 어느 자로 돌렸는지 알 길이 없다. 먼저 남겨야 한다."""
    client, dataset_id, uploads = wired
    client.post(f"/api/datasets/{dataset_id}/diagnose-labels?profile=mc")

    sidecar = json.loads(
        (uploads / dataset_id / upload.RULER_SIDECAR).read_text(encoding="utf-8"))
    assert sidecar["classes"] == ["Car", "Van", "Pedestrian", "Cyclist"]
    # 다시 GET으로 불러왔을 때도 자가 붙어 나와야 한다
    again = client.get(f"/api/datasets/{dataset_id}/label-diagnosis").json()
    assert again["ruler"]["classes"] == ["Car", "Van", "Pedestrian", "Cyclist"]


def test_subprocess_failure_becomes_500_with_the_reason(wired, monkeypatch):
    """스크립트가 실패하면 이유를 삼키지 말아야 한다."""
    client, dataset_id, _ = wired
    monkeypatch.setenv("FAKE_FAIL", "1")
    res = client.post(f"/api/datasets/{dataset_id}/diagnose-labels")
    assert res.status_code == 500
    assert "일부러 낸 실패" in res.json()["detail"]


def test_subprocess_timeout_becomes_504(wired, monkeypatch):
    client, dataset_id, _ = wired
    monkeypatch.setenv("FAKE_HANG", "1")
    monkeypatch.setattr(upload, "DIAGNOSE_TIMEOUT_SEC", 1)
    res = client.post(f"/api/datasets/{dataset_id}/diagnose-labels")
    assert res.status_code == 504


def test_missing_experiment_python_is_reported_clearly(wired, monkeypatch, tmp_path):
    """GPU 없는 서버에 올렸을 때 나는 상황. 무슨 일인지 말해줘야 한다."""
    client, dataset_id, _ = wired
    monkeypatch.setattr(upload, "EXPERIMENT_PYTHON", tmp_path / "없는파이썬")
    res = client.post(f"/api/datasets/{dataset_id}/diagnose-labels")
    assert res.status_code == 500
    assert "experiment/venv" in res.json()["detail"]


def test_diagnosing_an_unknown_dataset_is_404(wired):
    client, _, _ = wired
    res = client.post("/api/datasets/000000000000/diagnose-labels")
    assert res.status_code == 404
