"""클래스 **의미**가 대응되는가 (docs/24 B).

지금까지 자를 고를 때 **인덱스 개수만** 봤다 — "라벨에 인덱스 0~3이 있으니
4개를 아는 자가 필요하다". 그런데 그것으로는 **고객의 인덱스 2가 자의 인덱스
2와 같은 뜻인지** 알 수 없다.

순서가 다르면 진단이 통째로 어긋난다. 클래스 오기입 지목은 헛것이 되고,
적합도는 멀쩡해 보인다 — **아무 흔적도 안 남는다.**

이 프로젝트에 이미 근거가 있다: COCO `bicycle`(자전거)과 KITTI `Cyclist`
(탄 사람)는 의미가 다르다(docs/21 AI). 그래서 COCO 실험은 `Car` 하나만 썼다.

YOLO 라벨(.txt)에는 이름이 없고 숫자뿐이다. 그래서 **zip 안의 클래스 이름
파일**을 읽어야 한다. 없으면 없다고 말해야 한다 — 조용히 같다고 가정하면 안 된다.
"""
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.routers.upload import read_class_names, compare_class_names  # noqa: E402


def write(d: Path, name: str, text: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p


# --- 이름을 어디서 읽는가 -----------------------------------------------------

def test_reads_data_yaml(tmp_path):
    write(tmp_path, "data.yaml", "names:\n  0: Car\n  1: Van\n")
    assert read_class_names(tmp_path) == ["Car", "Van"]


def test_reads_data_yaml_list_form(tmp_path):
    write(tmp_path, "data.yaml", "names: [Car, Van, Pedestrian]\n")
    assert read_class_names(tmp_path) == ["Car", "Van", "Pedestrian"]


def test_reads_classes_txt(tmp_path):
    write(tmp_path, "classes.txt", "Car\nVan\n\nPedestrian\n")
    assert read_class_names(tmp_path) == ["Car", "Van", "Pedestrian"]


def test_none_when_absent(tmp_path):
    """없으면 없다고 해야 한다 — 빈 목록으로 뭉개면 '이름이 다 비었다'가 된다."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    assert read_class_names(tmp_path) is None


def test_broken_file_does_not_crash(tmp_path):
    write(tmp_path, "data.yaml", "names: [oops\n")
    assert read_class_names(tmp_path) is None


# --- 무엇을 말하는가 ----------------------------------------------------------

def test_same_names_same_order_is_quiet(tmp_path):
    assert compare_class_names(["Car", "Van"], ["Car", "Van"]) == ""


def test_case_and_space_do_not_matter(tmp_path):
    assert compare_class_names([" car ", "VAN"], ["Car", "Van"]) == ""


def test_reordered_names_are_flagged(tmp_path):
    """가장 위험한 경우다 — 개수가 같아 지금까지 아무 말도 안 했다."""
    msg = compare_class_names(["Van", "Car"], ["Car", "Van"])
    assert "순서" in msg
    assert "Car" in msg and "Van" in msg


def test_unknown_name_is_flagged(tmp_path):
    msg = compare_class_names(["Car", "Bicycle"], ["Car", "Van"])
    assert "Bicycle" in msg


def test_no_names_says_it_is_assuming(tmp_path):
    """이름을 못 찾았으면 '같다고 가정한다'를 말해야 한다."""
    msg = compare_class_names(None, ["Car", "Van"])
    assert "가정" in msg


def test_ruler_without_names_is_quiet(tmp_path):
    assert compare_class_names(["Car"], []) == ""
