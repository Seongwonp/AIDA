"""검수 판정을 서버에 남기기 (docs/22 계획 5번).

브라우저에만 두면 기계를 옮길 때 사라진다. 검수는 한 번에 끝나지 않는
일이라(그래서 지난 진단을 다시 여는 기능이 있다) 진행이 기계에 묶이면 반쪽이다.
"""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import upload

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c630001000005000101"
    "0d0a2db40000000049454e44ae426082"
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "UPLOADS_DIR", tmp_path / "uploads")
    return TestClient(app)


@pytest.fixture
def dataset(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("images/a.png", PNG)
        zf.writestr("labels/a.txt", b"0 0.5 0.5 0.2 0.2\n")
    res = client.post("/api/datasets/upload",
                      files={"file": ("d.zip", buf.getvalue(), "application/zip")})
    assert res.status_code == 200, res.text
    return res.json()["dataset_id"]


def test_empty_before_anything_is_saved(client, dataset):
    res = client.get(f"/api/datasets/{dataset}/verdicts")
    assert res.status_code == 200
    assert res.json()["verdicts"] == {}


def test_round_trip(client, dataset):
    """다른 기계에서 이어받는 것이 목적이다."""
    body = {"verdicts": {"a.png#0#width": "hit", "a.png#1#missing": "miss"}}
    put = client.put(f"/api/datasets/{dataset}/verdicts", json=body)
    assert put.status_code == 200
    assert put.json()["updated_at"]

    got = client.get(f"/api/datasets/{dataset}/verdicts").json()
    assert got["verdicts"] == body["verdicts"]


def test_put_replaces_rather_than_merges(client, dataset):
    """부분 갱신이 아니라 전체 교체다.

    병합을 넣으면 '지운 판정이 되살아나는' 쪽이 더 흔한 사고가 된다.
    """
    client.put(f"/api/datasets/{dataset}/verdicts",
               json={"verdicts": {"a#0#width": "hit", "b#1#missing": "hit"}})
    client.put(f"/api/datasets/{dataset}/verdicts",
               json={"verdicts": {"a#0#width": "miss"}})
    got = client.get(f"/api/datasets/{dataset}/verdicts").json()
    assert got["verdicts"] == {"a#0#width": "miss"}


def test_unknown_verdict_value_is_rejected(client, dataset):
    res = client.put(f"/api/datasets/{dataset}/verdicts",
                     json={"verdicts": {"a#0#width": "maybe"}})
    assert res.status_code == 400
    assert "maybe" in res.json()["detail"]


def test_too_many_verdicts_is_rejected(client, dataset, monkeypatch):
    monkeypatch.setattr(upload, "MAX_VERDICTS", 3)
    res = client.put(f"/api/datasets/{dataset}/verdicts",
                     json={"verdicts": {f"k{i}": "hit" for i in range(5)}})
    assert res.status_code == 413


def test_unknown_dataset_is_404(client):
    assert client.get("/api/datasets/000000000000/verdicts").status_code == 404
    assert client.put("/api/datasets/000000000000/verdicts",
                      json={"verdicts": {}}).status_code == 404


def test_broken_file_does_not_block_review(client, dataset, tmp_path):
    """깨진 파일 때문에 검수를 못 하게 되면 안 된다."""
    (tmp_path / "uploads" / dataset / upload.VERDICTS_FILE).write_text(
        "{깨진", encoding="utf-8")
    assert client.get(f"/api/datasets/{dataset}/verdicts").json()["verdicts"] == {}


def test_deleting_the_dataset_removes_verdicts(client, dataset, tmp_path):
    """서버에서 지웠으면 판정도 같이 가야 한다 — 브라우저 쪽과 같은 규칙이다."""
    client.put(f"/api/datasets/{dataset}/verdicts",
               json={"verdicts": {"a#0#width": "hit"}})
    assert client.delete(f"/api/datasets/{dataset}").status_code == 204
    assert not (tmp_path / "uploads" / dataset).exists()
