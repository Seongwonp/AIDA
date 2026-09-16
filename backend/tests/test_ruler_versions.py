"""자 기록(`ruler.json`)이 순위 버전마다 따로인가 (docs/next-work-2026-09-15.md S3).

진단 결과는 순위 버전마다 파일이 따로인데 **자 기록은 데이터셋에 하나였다.** 그래서 v1을 기본
자로 돌리고 v2를 다른 프로파일로 돌리면, v1 결과를 다시 열 때 **v2의 자가 붙어 나왔다.** 평가
묶음은 자를 지문에 넣으므로, 그 상태로 v1을 얼리면 다른 자로 잰 후보라고 기록된다.

기대값의 클래스 목록은 문자열로 직접 적는다(`fake_experiment`의 `mc` 프로파일과 기본 자).
"""
import json

import pytest
from fastapi.testclient import TestClient

from app import ranking as R
from app.main import app
from app.routers import evaluation as E
from app.routers import upload
from tests import fake_experiment as fake

DATASET = "abcdef123456"
V1 = "aida_v1_systematic_boost"
V2 = "aida_v2_candidate_iou"
MC_CLASSES = ["Car", "Van", "Pedestrian", "Cyclist"]


@pytest.fixture
def wired(fake_experiment, monkeypatch):
    root, uploads = fake_experiment
    ds = uploads / DATASET
    (ds / "images").mkdir(parents=True)
    (ds / "labels").mkdir(parents=True)
    (ds / "images" / "a.png").write_bytes(b"\x89PNG")
    (ds / "labels" / "a.txt").write_text("0 0.5 0.5 0.2 0.2", encoding="utf-8")
    monkeypatch.setenv("FAKE_UPLOADS_DIR", str(uploads))
    monkeypatch.setenv("FAKE_DIAGNOSIS_JSON",
                       json.dumps(fake.diagnosis_payload(DATASET), ensure_ascii=False))
    monkeypatch.setattr(E, "UPLOADS_DIR", uploads)
    return TestClient(app), uploads


def ruler_of(client, version):
    body = client.get(f"/api/datasets/{DATASET}/label-diagnosis?ranking={version}").json()
    return body["ruler"]


def test_자_기록_파일_이름은_버전마다_따로다():
    """v1은 옛 이름 그대로라 옛 데이터셋의 자 기록이 그대로 읽힌다."""
    assert R.ruler_filename(V1) == "ruler.json"
    assert R.ruler_filename(V2) == "ruler.aida_v2_candidate_iou.json"


def test_v2를_다른_프로파일로_돌려도_v1의_자는_그대로다(wired):
    client, _ = wired
    assert client.post(f"/api/datasets/{DATASET}/diagnose-labels").status_code == 200
    v1_before = ruler_of(client, V1)
    assert v1_before["classes"] != MC_CLASSES

    r = client.post(f"/api/datasets/{DATASET}/diagnose-labels?ranking={V2}&profile=mc")
    assert r.status_code == 200, r.text

    assert ruler_of(client, V1) == v1_before          # v2 실행이 v1의 자를 덮지 않는다
    assert ruler_of(client, V2)["classes"] == MC_CLASSES


def test_자기_기록이_없는_v2_결과는_v1의_자를_빌려_쓰지_않는다(wired):
    """이 수정 전에 만든 v2 결과에는 자기 자 기록이 없다. 공유 파일(`ruler.json`)은 어느
    실행의 것인지 모르므로 **모른다(None)** 고 말한다 — 틀린 자를 붙이는 것보다 낫다."""
    client, uploads = wired
    assert client.post(f"/api/datasets/{DATASET}/diagnose-labels").status_code == 200
    assert client.post(f"/api/datasets/{DATASET}/diagnose-labels?ranking={V2}").status_code == 200
    (uploads / DATASET / R.ruler_filename(V2)).unlink()     # 수정 전 상태를 흉내 낸다
    assert (uploads / DATASET / "ruler.json").exists()       # 공유 파일은 남아 있다
    assert ruler_of(client, V2) is None
    assert ruler_of(client, V1) is not None


def test_옛_데이터셋의_ruler_json은_v1으로_읽힌다(wired):
    client, uploads = wired
    assert client.post(f"/api/datasets/{DATASET}/diagnose-labels?profile=mc").status_code == 200
    assert (uploads / DATASET / "ruler.json").exists()
    assert ruler_of(client, V1)["classes"] == MC_CLASSES


def test_v2_평가_묶음은_v2의_자를_얼린다(wired):
    client, _ = wired
    client.post(f"/api/datasets/{DATASET}/diagnose-labels")
    client.post(f"/api/datasets/{DATASET}/diagnose-labels?ranking={V2}&profile=mc")
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": "e2", "ranking_version": V2})
    assert r.status_code == 200, r.text
    assert r.json()["ruler"]["classes"] == MC_CLASSES
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": "e1", "ranking_version": V1})
    assert r.status_code == 200, r.text
    assert r.json()["ruler"]["classes"] != MC_CLASSES
