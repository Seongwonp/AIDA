"""zip 안의 폴더 모양 — 처음 온 사람이 가장 먼저 걸리는 곳.

윈도우·맥 둘 다 폴더를 우클릭해 압축하면 안이 mydata/images/... 로 한 겹
싸인다. 가장 흔한 방식인데, 그걸 거절하면 사용자 눈에는 분명히 있는 images/를
없다고 하는 셈이 된다.

여기서 검사하는 것은 두 가지다. 한 겹은 벗기되, **벗기면 안 되는 경우에는
건드리지 않는다** — 폴더가 둘 이상이거나 안에도 images/가 없으면 그건 다른
문제이고, 잘못 벗기면 원인이 더 가려진다.
"""
import pytest
from fastapi import HTTPException

from app.routers.upload import _validate_dataset_dir


def make(root, layout: dict[str, list[str]]):
    """{"images": ["a.png"], "labels": ["a.txt"]} 모양으로 폴더를 만든다."""
    for folder, names in layout.items():
        d = root / folder
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            d.joinpath(n).write_text("0 0.5 0.5 0.2 0.2", encoding="utf-8")


def test_flat_zip_passes(tmp_path):
    """images/ labels/ 가 바로 있는 것 — 원래 되던 모양."""
    make(tmp_path, {"images": ["a.png", "b.png"], "labels": ["a.txt", "b.txt"]})
    assert _validate_dataset_dir(tmp_path) == (2, 2)


def test_folder_zipped_whole_is_unwrapped(tmp_path):
    """mydata/images/... 한 겹을 벗겨서 받아들인다."""
    make(tmp_path / "mydata", {"images": ["a.png"], "labels": ["a.txt"]})
    assert _validate_dataset_dir(tmp_path) == (1, 1)
    # 경로를 다르게 돌려주는 게 아니라 실제로 위로 올라와 있어야 한다 —
    # 이 뒤로 dataset_dir/images 를 그대로 쓰는 곳이 여럿이다.
    assert (tmp_path / "images" / "a.png").is_file()
    assert not (tmp_path / "mydata").exists()


def test_macos_metadata_does_not_block_unwrap(tmp_path):
    """맥이 끼워 넣는 __MACOSX 때문에 "폴더가 하나"가 깨지면 안 된다."""
    make(tmp_path / "mydata", {"images": ["a.png"], "labels": ["a.txt"]})
    (tmp_path / "__MACOSX").mkdir()
    (tmp_path / ".DS_Store").write_text("", encoding="utf-8")
    assert _validate_dataset_dir(tmp_path) == (1, 1)


def test_two_top_folders_is_left_alone(tmp_path):
    """폴더가 둘이면 벗길 게 아니다. 잘못 고르면 원인이 더 가려진다."""
    make(tmp_path / "train", {"images": ["a.png"], "labels": ["a.txt"]})
    make(tmp_path / "val", {"images": ["b.png"], "labels": ["b.txt"]})
    with pytest.raises(HTTPException) as e:
        _validate_dataset_dir(tmp_path)
    assert e.value.status_code == 400


def test_nested_without_images_is_left_alone(tmp_path):
    """한 겹 안에도 images/가 없으면 그건 다른 문제다."""
    make(tmp_path / "mydata", {"pics": ["a.png"], "anno": ["a.txt"]})
    with pytest.raises(HTTPException):
        _validate_dataset_dir(tmp_path)
    assert (tmp_path / "mydata" / "pics").is_dir()   # 원래 모양 그대로


def test_empty_images_is_rejected(tmp_path):
    make(tmp_path, {"images": [], "labels": ["a.txt"]})
    with pytest.raises(HTTPException) as e:
        _validate_dataset_dir(tmp_path)
    assert "images/" in e.value.detail


def test_no_txt_labels_says_what_is_wrong(tmp_path):
    """.json·.xml 라벨을 넣은 경우. 그냥 0건으로 통과시키면 모든 라벨이
    '누락 의심'으로 나와서 원인을 못 찾는다."""
    make(tmp_path, {"images": ["a.png"], "labels": ["a.json"]})
    with pytest.raises(HTTPException) as e:
        _validate_dataset_dir(tmp_path)
    assert ".txt" in e.value.detail
