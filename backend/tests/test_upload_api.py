"""업로드 엔드포인트 — 제품의 현관.

`_validate_dataset_dir`은 단위로 따로 검사한다(test_upload_layout.py). 여기서
보는 건 zip을 실제로 풀어 넘기는 길 전체다. 폴더째 압축한 zip을 거절하던 버그가
바로 이 구간에 있었는데, 여기까지 오는 검사가 하나도 없었다.
"""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import upload

# 1x1 PNG. 내용을 보지는 않지만 실제 바이트여야 나중에 이미지로 열린다.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c630001000005000101"
    "0d0a2db40000000049454e44ae426082"
)
LABEL = b"0 0.5 0.5 0.2 0.2\n"


def make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "UPLOADS_DIR", tmp_path / "uploads")
    return TestClient(app)


def post(client, data: bytes, filename="ds.zip"):
    return client.post(
        "/api/datasets/upload",
        files={"file": (filename, data, "application/zip")},
    )


def test_flat_zip(client):
    res = post(client, make_zip({
        "images/a.png": PNG, "images/b.png": PNG,
        "labels/a.txt": LABEL, "labels/b.txt": LABEL,
    }))
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["num_images"], body["num_labels"]) == (2, 2)
    assert body["label_class_ids"] == [0]


def test_folder_zipped_whole(client):
    """폴더를 우클릭해 압축한 모양. 가장 흔한데 거절하고 있었다."""
    res = post(client, make_zip({
        "mydata/images/a.png": PNG,
        "mydata/labels/a.txt": LABEL,
    }))
    assert res.status_code == 200, res.text
    assert res.json()["num_images"] == 1


def test_folder_zipped_on_macos(client):
    """맥이 끼워 넣는 __MACOSX 때문에 "폴더가 하나"가 깨지면 안 된다."""
    res = post(client, make_zip({
        "mydata/images/a.png": PNG,
        "mydata/labels/a.txt": LABEL,
        "__MACOSX/._a.png": b"\x00",
        ".DS_Store": b"\x00",
    }))
    assert res.status_code == 200, res.text
    assert res.json()["num_images"] == 1


def test_two_top_folders_is_rejected_with_a_useful_message(client):
    """train/ val/ 로 나눠 담은 것. 벗길 게 아니라 사용자가 고쳐야 한다."""
    res = post(client, make_zip({
        "train/images/a.png": PNG, "train/labels/a.txt": LABEL,
        "val/images/b.png": PNG, "val/labels/b.txt": LABEL,
    }))
    assert res.status_code == 400
    assert "images/" in res.json()["detail"]


def test_labels_in_another_format_is_rejected(client):
    """.json 라벨. 0건으로 통과시키면 전부 '누락 의심'으로 나와 원인을 못 찾는다."""
    res = post(client, make_zip({
        "images/a.png": PNG, "labels/a.json": b"{}",
    }))
    assert res.status_code == 400
    assert ".txt" in res.json()["detail"]


def test_non_zip_is_rejected(client):
    res = post(client, b"not a zip", filename="data.tar.gz")
    assert res.status_code == 400


def test_corrupt_zip_is_rejected(client):
    res = post(client, b"PK\x03\x04 garbage")
    assert res.status_code == 400


def test_rejected_upload_leaves_nothing_behind(client, tmp_path):
    """실패한 업로드가 폴더를 남기면 진단 이력 목록에 빈 항목으로 끼어든다."""
    post(client, make_zip({"images/a.png": PNG, "labels/a.json": b"{}"}))
    uploads = tmp_path / "uploads"
    assert not uploads.exists() or list(uploads.iterdir()) == []


def test_history_lists_the_upload(client):
    ds = post(client, make_zip({
        "images/a.png": PNG, "labels/a.txt": LABEL,
    })).json()["dataset_id"]
    rows = client.get("/api/datasets/history").json()
    assert [r["dataset_id"] for r in rows] == [ds]
    # 아직 진단 전이라 재검수 목록이 없다 — 화면은 '열기' 대신 그렇게 표시한다
    assert rows[0]["has_label_diagnosis"] is False


def test_delete_removes_the_dataset(client, tmp_path):
    ds = post(client, make_zip({
        "images/a.png": PNG, "labels/a.txt": LABEL,
    })).json()["dataset_id"]
    assert client.delete(f"/api/datasets/{ds}").status_code == 204
    assert client.get("/api/datasets/history").json() == []
    assert not (tmp_path / "uploads" / ds).exists()


def test_delete_missing_dataset_is_404(client):
    assert client.delete("/api/datasets/nope").status_code == 404


@pytest.mark.parametrize("bad", ["..", "%2e%2e", "a%2Fb"])
def test_delete_cannot_escape_the_uploads_dir(client, tmp_path, bad):
    """지우는 동작이라 한 번 틀리면 되돌릴 수 없다."""
    outside = tmp_path / "keep_me"
    outside.mkdir()
    res = client.delete(f"/api/datasets/{bad}")
    assert res.status_code in (400, 404, 405), res.text
    assert outside.is_dir()


@pytest.fixture
def guard_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "UPLOADS_DIR", tmp_path / "uploads")
    (tmp_path / "uploads" / "ok").mkdir(parents=True)
    outside = tmp_path / "keep_me"
    outside.mkdir()
    return outside


@pytest.mark.parametrize("bad", ["..", "../keep_me", "ok/../../keep_me", ""])
def test_delete_guard_rejects_traversal_directly(tmp_path, guard_dirs, bad):
    """HTTP 계층이 경로를 미리 정규화해 버리면 요청으로 하는 검사는 헐거워진다.
    핸들러를 직접 불러 가드 자체를 확인한다."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        upload.delete_dataset(bad)
    assert e.value.status_code == 400
    assert guard_dirs.is_dir()
    assert (tmp_path / "uploads" / "ok").is_dir()


def test_delete_guard_and_backslash(tmp_path, guard_dirs):
    r"""역슬래시는 플랫폼을 탄다.

    윈도우에서 "..\keep_me"는 경로 두 조각이라 가드가 400으로 막는다. 리눅스
    에서는 그냥 그런 이름의 파일 하나라 애초에 나갈 수가 없고, 없는 폴더라
    404가 난다. **어느 쪽이든 바깥은 안전하다** — 상태 코드를 한쪽으로 못
    박으면 다른 플랫폼에서 거짓으로 깨진다. 실제로 CI에서 그렇게 깨졌다.
    """
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        upload.delete_dataset("..\\keep_me")
    assert e.value.status_code in (400, 404)
    assert guard_dirs.is_dir()
    assert (tmp_path / "uploads" / "ok").is_dir()


# --- 압축 폭탄 --------------------------------------------------------------
#
# 업로드 바이트만 200MB로 재고 있었다. 압축률은 안 봤다 — 0으로 채운 1MB짜리
# zip이 풀면 1GB가 된다(실측 1028배). 코덱스 리뷰가 잡아준 것이다.

def bomb_zip(entries: int = 2, each: int = 100 * 1024 * 1024) -> bytes:
    """압축하면 작고 풀면 큰 zip. 0으로 채우면 1000배 넘게 눌린다."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("images/a.png", PNG)
        zf.writestr("labels/a.txt", LABEL)
        for i in range(entries):
            zf.writestr(f"images/big{i}.png", b"\x00" * each)
    return buf.getvalue()


def test_compression_ratio_is_the_actual_danger():
    """업로드 바이트만 재면 왜 부족한지부터 못 박는다.

    200MB가 풀려서 200MB가 되는 게 아니다. 여기 만든 zip이 몇 배로 부푸는지
    실제로 세어, 한도의 근거가 상상이 아니라는 것을 남긴다.
    """
    data = bomb_zip()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        expanded = sum(i.file_size for i in zf.infolist())
    assert len(data) < 5 * 1024 * 1024, "압축된 것은 업로드 한도에 한참 못 미친다"
    assert expanded / len(data) > 100, f"부푸는 배율 {expanded / len(data):.0f}배"


def test_zip_bomb_is_rejected_before_extracting(client, tmp_path, monkeypatch):
    # 실제 한도는 2GB지만 그걸 넘기는 zip을 테스트에서 만들면 느리다. 한도를
    # 낮춰 같은 길을 탄다 — 보는 것은 "풀기 전에 막는가"다.
    monkeypatch.setattr(upload, "MAX_EXTRACTED_BYTES", 50 * 1024 * 1024)
    data = bomb_zip()
    assert len(data) < 200 * 1024 * 1024, "이 zip 자체는 업로드 한도를 통과한다"

    res = post(client, data)
    assert res.status_code == 413, res.text
    # 풀기 전에 막아야 의미가 있다 — 디스크에 남은 게 없어야 한다
    uploads = tmp_path / "uploads"
    assert not uploads.exists() or list(uploads.iterdir()) == []


def test_too_many_entries_is_rejected(client, monkeypatch):
    monkeypatch.setattr(upload, "MAX_ZIP_ENTRIES", 5)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("labels/a.txt", LABEL)
        for i in range(10):
            zf.writestr(f"images/{i}.png", PNG)
    res = post(client, buf.getvalue())
    assert res.status_code == 400
    assert "너무 많습니다" in res.json()["detail"]


def test_normal_dataset_still_passes_the_size_guard(client):
    """정상 데이터셋을 실수로 막으면 안 된다."""
    res = post(client, make_zip({
        "images/a.png": PNG, "images/b.png": PNG,
        "labels/a.txt": LABEL, "labels/b.txt": LABEL,
    }))
    assert res.status_code == 200, res.text


def test_zip_slip_paths_are_rejected(client, tmp_path):
    """CPython의 extractall이 "../"를 실제로 제거하므로 지금도 밖으로 나가지는
    않는다. 그 보장이 표준 라이브러리 구현에 딸린 것이라 코드만 읽어서는 안
    보이므로, 우리가 직접 막는다는 것을 검사로 고정한다."""
    outside = tmp_path / "keep_me"
    outside.mkdir()
    res = post(client, make_zip({
        "../../keep_me/pwned.txt": b"x",
        "images/a.png": PNG,
        "labels/a.txt": LABEL,
    }))
    assert res.status_code == 400
    assert "허용되지 않은 경로" in res.json()["detail"]
    assert list(outside.iterdir()) == []
