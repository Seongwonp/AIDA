"""보조 판정자 입력 그림 — 가림 규칙(점수·순위 없음), 상자 색·자르기."""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import render_adjudication_images as R  # noqa: E402


def make_dataset(tmp_path):
    (tmp_path / "images").mkdir(); (tmp_path / "labels").mkdir()
    Image.new("RGB", (200, 100), (255, 255, 255)).save(tmp_path / "images" / "a.png")
    # 라벨 두 개: [20,20,60,60], [120,30,180,80]
    (tmp_path / "labels" / "a.txt").write_text("0 0.2 0.4 0.2 0.4\n0 0.75 0.55 0.3 0.5\n", encoding="utf-8")
    return tmp_path


def test_라벨_후보는_빨강_실선_다른_라벨은_파랑(tmp_path):
    ds = make_dataset(tmp_path)
    queue = {"candidates": [{"canonical_candidate_id": "L1", "image": "a.png", "label_index": 0,
                             "box": [20.0, 20.0, 60.0, 60.0], "class_name": "Car"}]}
    m = R.render_queue(queue, ds / "images", ds / "labels", tmp_path / "out", margin=0.5)
    img = Image.open(tmp_path / "out" / "L1.png").convert("RGB")
    assert m[0]["task"] == "labelled" and "x1=20" in m[0]["caption"]
    crop = m[0]["crop_xyxy_px"]
    assert crop == [0, 0, 100, 100]                       # 여백 40px, 이미지 경계에서 멈춤
    px = img.getpixel((20 - crop[0], 40 - crop[1]))     # 판정 상자 왼쪽 변
    assert px[0] > 150 and px[2] < 100                   # 빨강


def test_누락_후보는_점선이고_기존_라벨은_파랑으로_남는다(tmp_path):
    ds = make_dataset(tmp_path)
    queue = {"candidates": [{"canonical_candidate_id": "C1", "image": "a.png", "label_index": None,
                             "box": [80.0, 10.0, 110.0, 40.0], "class_name": "Car"}]}
    m = R.render_queue(queue, ds / "images", ds / "labels", tmp_path / "out")
    assert m[0]["task"] == "missing" and "점선" in m[0]["caption"]
    img = Image.open(tmp_path / "out" / "C1.png").convert("RGB")
    crop = m[0]["crop_xyxy_px"]
    assert crop == [40, 0, 150, 80]
    # 두 번째 기존 라벨 [120,30,180,80]의 왼쪽 변(x=120)은 crop 안에 있고 파랑이어야 한다
    blue = img.getpixel((120 - crop[0], 55 - crop[1]))
    assert blue[2] > 150 and blue[0] < 100


def test_manifest에_점수나_순위가_없다(tmp_path):
    ds = make_dataset(tmp_path)
    queue = {"candidates": [{"canonical_candidate_id": "L1", "image": "a.png", "label_index": 0,
                             "box": [20.0, 20.0, 60.0, 60.0], "class_name": "Car"}]}
    R.render_queue(queue, ds / "images", ds / "labels", tmp_path / "out")
    text = (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")
    for forbidden in ("score", "rank", "severity", "suspicion", "random_sample", "source"):
        assert forbidden not in text


def test_full_context_preserves_other_labels_outside_crop(tmp_path):
    ds = make_dataset(tmp_path)
    q = {"candidates": [{"canonical_candidate_id": "L1", "image": "a.png", "label_index": 0,
                         "box": [20, 20, 60, 60], "class_name": "Car", "verdict": None}]}
    m = R.render_queue(q, ds / "images", ds / "labels", tmp_path / "out")
    full = Image.open(tmp_path / "out" / m[0]["full_file"]).convert("RGB")
    assert full.size == (200, 100)
    assert full.getpixel((120, 55)) == R.BLUE
    assert Image.open(tmp_path / "out" / m[0]["file"]).size == (100, 100)


@pytest.mark.parametrize("extra", [{"verdict": "hit"}, {"unique_error_id": "a/L0"},
                                    {"scores": {}}, {"coverage_extra": True}, {"method": "aida"}])
def test_library_rejects_unblinded_inputs_before_writing(tmp_path, extra):
    q = {"candidates": [{"canonical_candidate_id": "L1", **extra}]}
    with pytest.raises(ValueError):
        R.render_queue(q, tmp_path, tmp_path, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_누락_점선은_사람_화면과_같은_주황이다(tmp_path):
    # 사람 판정 화면(AdjudicationView MISSING_COLOR #d97706)과 같은 색 — open_items P9
    ds = make_dataset(tmp_path)
    queue = {"candidates": [{"canonical_candidate_id": "C1", "image": "a.png", "label_index": None,
                             "box": [80.0, 10.0, 110.0, 40.0], "class_name": "Car"}]}
    m = R.render_queue(queue, ds / "images", ds / "labels", tmp_path / "out")
    assert "주황 점선" in m[0]["caption"]
    img = Image.open(tmp_path / "out" / "C1.png").convert("RGB")
    crop = m[0]["crop_xyxy_px"]
    r, g, b = img.getpixel((82 - crop[0], 10 - crop[1]))   # 위쪽 변의 첫 점선 조각
    assert (r, g, b) == R.ORANGE == (217, 119, 6)
