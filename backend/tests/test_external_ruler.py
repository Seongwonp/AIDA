"""nuImages 자 선택 경로 (사전 등록 D1).

제품 경로에서 자를 이름으로 고르고, 실제 가중치와 SHA-256이 자 기록·서브프로세스·진단 결과에
남으며, 없으면 대체하지 않고 멈추는지 본다.
"""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import evaluation as E
from app.routers import upload
from tests import fake_experiment as fake

RULER = "nuimages_car_v1_e100"


@pytest.fixture
def wired(fake_experiment, monkeypatch):
    root, uploads = fake_experiment
    dataset_id = "abcdef123456"
    ds = uploads / dataset_id
    (ds / "images").mkdir(parents=True)
    (ds / "labels").mkdir(parents=True)
    (ds / "images" / "a.png").write_bytes(b"\x89PNG")
    (ds / "labels" / "a.txt").write_text("0 0.5 0.5 0.2 0.2", encoding="utf-8")
    monkeypatch.setenv("FAKE_UPLOADS_DIR", str(uploads))
    monkeypatch.setenv("FAKE_DIAGNOSIS_JSON",
                       json.dumps(fake.diagnosis_payload(dataset_id), ensure_ascii=False))
    monkeypatch.setattr(E, "UPLOADS_DIR", uploads)
    return TestClient(app), dataset_id, uploads, root


def place_weights(root, content=b"nuimages-car-v1-e100"):
    w = root / upload.EXTERNAL_RULERS[RULER]["weights"]
    w.parent.mkdir(parents=True, exist_ok=True)
    w.write_bytes(content)
    return w, hashlib.sha256(content).hexdigest()


def test_없는_자는_대체하지_않고_404다(wired):
    client, ds, _, _ = wired
    r = client.post(f"/api/datasets/{ds}/diagnose-labels?ruler={RULER}")
    assert r.status_code == 404 and "대체하지 않습니다" in r.json()["detail"]


def test_모르는_자는_400이다(wired):
    client, ds, _, root = wired
    place_weights(root)
    assert client.post(f"/api/datasets/{ds}/diagnose-labels?ruler=kitti_something").status_code == 400


def test_자와_프로파일을_같이_고르면_거부한다(wired):
    client, ds, _, root = wired
    place_weights(root)
    assert client.post(f"/api/datasets/{ds}/diagnose-labels?ruler={RULER}&profile=mc").status_code == 400


def test_고른_자의_경로와_해시가_서브프로세스와_자_기록에_남는다(wired):
    client, ds, uploads, root = wired
    w, sha = place_weights(root)
    r = client.post(f"/api/datasets/{ds}/diagnose-labels?ruler={RULER}")
    assert r.status_code == 200, r.text
    call = json.loads((uploads / ds / "stub_call.json").read_text(encoding="utf-8"))
    assert call["ruler_weights"] == str(w) and call["ruler_sha256"] == sha
    assert call["classes"] == "Car" and call["profile"] is None
    sidecar = json.loads((uploads / ds / upload.RULER_SIDECAR).read_text(encoding="utf-8"))
    assert sidecar["ruler_id"] == RULER and sidecar["weights_sha256"] == sha
    assert sidecar["weights_path"] == upload.EXTERNAL_RULERS[RULER]["weights"]
    assert r.json()["ruler"]["weights_sha256"] == sha


def test_진단이_다른_자를_열었으면_결과를_돌려주지_않는다(wired, monkeypatch):
    client, ds, _, root = wired
    place_weights(root)
    monkeypatch.setenv("FAKE_WRONG_RULER", "1")
    r = client.post(f"/api/datasets/{ds}/diagnose-labels?ruler={RULER}")
    assert r.status_code == 500 and "다릅니다" in r.json()["detail"]


def test_자가_바뀐_진단은_얼리지_않는다(wired):
    client, ds, uploads, root = wired
    place_weights(root)
    assert client.post(f"/api/datasets/{ds}/diagnose-labels?ruler={RULER}").status_code == 200
    # 자 기록은 그대로인데 진단 파일의 자가 바뀌었다(다른 자로 다시 돌린 상황)
    path = uploads / ds / "label_diagnosis.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["ruler"]["sha256"] = "f" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    r = client.post(f"/api/datasets/{ds}/evaluations", json={"evaluation_id": "e1"})
    assert r.status_code == 409


def test_자_목록은_있는지와_해시를_말한다(wired):
    client, _, _, root = wired
    before = client.get("/api/datasets/rulers").json()
    assert before[0]["ruler_id"] == RULER and before[0]["available"] is False
    _, sha = place_weights(root)
    after = client.get("/api/datasets/rulers").json()
    assert after[0]["available"] is True and after[0]["weights_sha256"] == sha


def test_자를_안_고르면_옛_경로_그대로다(wired):
    client, ds, uploads, _ = wired
    assert client.post(f"/api/datasets/{ds}/diagnose-labels").status_code == 200
    call = json.loads((uploads / ds / "stub_call.json").read_text(encoding="utf-8"))
    assert call["ruler_weights"] is None
