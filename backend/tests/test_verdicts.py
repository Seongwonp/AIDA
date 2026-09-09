"""검수 판정을 서버에 남기기 (docs/22 계획 5번).

브라우저에만 두면 기계를 옮길 때 사라진다. 검수는 한 번에 끝나지 않는
일이라(그래서 지난 진단을 다시 여는 기능이 있다) 진행이 기계에 묶이면 반쪽이다.
"""
import io
import zipfile
from pathlib import Path

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


# --- 빈 판정의 세 가지 뜻 (docs/25 R3) ----------------------------------------
#
# 화면은 "서버가 비었으면 브라우저 것을 쓴다"였는데, 서버가 비는 이유가 셋이고
# 뜻이 다르다. 지운 판정이 브라우저 사본으로 되살아나던 것이 그래서다.
#
# `updated_at`이 "한 번도 저장 안 됨"과 "저장했는데 비었다"를 가른다.
# **그 계약을 여기서 고정한다** — 화면이 이것에 기대고 있다.

def test_never_saved_has_no_timestamp(client, dataset):
    body = client.get(f"/api/datasets/{dataset}/verdicts").json()
    assert body["verdicts"] == {}
    assert body["updated_at"] is None, "저장된 적 없음은 시각이 없어야 한다"


def test_saved_empty_keeps_its_timestamp(client, dataset):
    """전부 지운 것도 '저장'이다 — 그 사실이 남아야 한다."""
    client.put(f"/api/datasets/{dataset}/verdicts", json={"verdicts": {"a#0#width": "hit"}})
    client.put(f"/api/datasets/{dataset}/verdicts", json={"verdicts": {}})

    body = client.get(f"/api/datasets/{dataset}/verdicts").json()
    assert body["verdicts"] == {}
    assert body["updated_at"] is not None, \
        "지운 뒤에도 시각이 있어야 '지웠다'와 '아직 없다'가 갈린다"


# --- 파일이 깨지거나 쓰다 끊기면 (docs/25 R4) ---------------------------------
#
# 깨진 파일을 빈 판정으로 돌려주면 **검수는 이어지지만 손상이 정상으로
# 위장된다.** R3에서 화면은 "판정 없음 · updated_at 없음"을 "아직 저장 안 됨"
# 으로 읽기로 했다 — 그러면 깨진 서버 상태를 보고 브라우저 사본을 살린다.
# 서버가 사실 무엇을 갖고 있는지 모르는 채로.
#
# 그리고 저장이 전체 덮어쓰기라, 쓰다 끊기면 **있던 판정까지 잃는다.**

def test_broken_file_is_reported_as_damaged(client, dataset, tmp_path):
    """검수는 막지 않되 **손상됐다고 말한다.**"""
    (tmp_path / "uploads" / dataset / upload.VERDICTS_FILE).write_text(
        "{깨진", encoding="utf-8")
    body = client.get(f"/api/datasets/{dataset}/verdicts").json()
    assert body["verdicts"] == {}           # 기존 계약: 막지 않는다
    assert body["damaged"] is True, "손상을 정상적인 빈 판정으로 숨기면 안 된다"


def test_healthy_file_is_not_damaged(client, dataset):
    client.put(f"/api/datasets/{dataset}/verdicts", json={"verdicts": {"a#0#width": "hit"}})
    assert client.get(f"/api/datasets/{dataset}/verdicts").json()["damaged"] is False


def test_never_saved_is_not_damaged(client, dataset):
    """파일이 없는 것은 손상이 아니다 — R3가 그 둘을 갈라 쓴다."""
    body = client.get(f"/api/datasets/{dataset}/verdicts").json()
    assert body["damaged"] is False
    assert body["updated_at"] is None


def test_failed_write_keeps_the_previous_verdicts(client, dataset, tmp_path, monkeypatch):
    """쓰다 끊겨도 있던 판정은 살아야 한다.

    예전에는 write_text로 곧장 덮어썼다. 여는 순간 잘리므로 **쓰기가 실패하면
    있던 것까지 사라진다.**
    """
    client.put(f"/api/datasets/{dataset}/verdicts", json={"verdicts": {"a#0#width": "hit"}})

    real = Path.replace

    def boom(self, target):                 # 교체 직전에 끊긴다
        raise OSError("디스크 꽉 참")

    monkeypatch.setattr(Path, "replace", boom)
    resp = client.put(f"/api/datasets/{dataset}/verdicts",
                      json={"verdicts": {"b#1#height": "miss"}})
    monkeypatch.setattr(Path, "replace", real)

    assert resp.status_code >= 500, "저장 실패를 성공으로 보고하면 안 된다"
    body = client.get(f"/api/datasets/{dataset}/verdicts").json()
    assert body["verdicts"] == {"a#0#width": "hit"}, "있던 판정이 사라졌다"
    assert body["damaged"] is False


def test_no_temp_file_is_left_behind(client, dataset, tmp_path, monkeypatch):
    """실패한 임시 파일이 남아 다음 읽기를 헷갈리게 하면 안 된다."""
    def boom(self, target):
        raise OSError("디스크 꽉 참")

    monkeypatch.setattr(Path, "replace", boom)
    client.put(f"/api/datasets/{dataset}/verdicts", json={"verdicts": {"a#0#width": "hit"}})
    monkeypatch.undo()

    leftovers = [p.name for p in (tmp_path / "uploads" / dataset).iterdir()
                 if p.name != upload.VERDICTS_FILE and "verdict" in p.name]
    assert leftovers == [], f"임시 파일이 남았다: {leftovers}"
