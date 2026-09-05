"""업로드된 이미지 서빙 — 경로가 위험 지점이다.

이미지 이름은 사용자가 올린 zip에서 온 값이다. 그대로 경로에 이어붙이면
"../../.env" 같은 것으로 데이터셋 폴더 밖을 읽을 수 있다. 재검수 목록이
문제 박스를 그려 보여주려면 이 엔드포인트가 필요한데, 그 편의가 구멍이
되면 안 된다.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import upload


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    """images/ 아래 진짜 PNG 한 장이 있는 업로드 폴더."""
    root = tmp_path / "uploads"
    images = root / "ds1" / "images"
    images.mkdir(parents=True)
    # 1x1 PNG. 내용을 검사하지는 않지만 실제 바이트여야 FileResponse가 연다.
    images.joinpath("000001.png").write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000a49444154789c6300010000050001"
        "0d0a2db40000000049454e44ae426082"
    ))
    # 폴더 밖에 두는 비밀 파일 — 여기에 닿으면 안 된다
    (tmp_path / "secret.env").write_text("TOKEN=1234", encoding="utf-8")
    monkeypatch.setattr(upload, "UPLOADS_DIR", root)
    return root


@pytest.fixture
def client(dataset):
    return TestClient(app)


def test_serves_an_uploaded_image(client):
    r = client.get("/api/datasets/ds1/images/000001.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content.startswith(b"\x89PNG")


def test_missing_image_is_404(client):
    assert client.get("/api/datasets/ds1/images/nope.png").status_code == 404


def test_unknown_dataset_is_404(client):
    assert client.get("/api/datasets/없는것/images/000001.png").status_code == 404


@pytest.mark.parametrize("name", [
    "../secret.env",
    "../../secret.env",
    "..%2Fsecret.env",
    "images/../../secret.env",
])
def test_path_traversal_cannot_escape(client, name):
    """폴더 밖 파일에 닿으면 안 된다. 200이 나오는 것 자체가 실패다."""
    r = client.get(f"/api/datasets/ds1/images/{name}")
    assert r.status_code != 200, f"{name}이 통과했다"
    assert b"TOKEN" not in r.content


def test_non_image_extension_is_rejected(client):
    """확장자로 한 번 거른다 — 이미지가 아닌 것을 내보낼 이유가 없다."""
    r = client.get("/api/datasets/ds1/images/config.py")
    assert r.status_code == 400
