"""nuImages → YOLO 폴더 변환 (docs/advice-w1-w5-2026-09-16.md 4·5절).

**손으로 만든 작은 표로 검사한다.** 실제 nuImages 파일은 저장소에 넣지 않는다(약관).

세계 — 이미지 둘(1600×900), 로그 둘.

| 키프레임 | 카메라 | 객체 |
|---|---|---|
| s1 (log A) | CAM_FRONT | car [100,200,300,400], truck [0,0,50,50], car [1590,880,1650,950](경계 밖으로 나감) |
| s2 (log B) | CAM_BACK | car [10,20,10,40](폭 0 — 버린다) |

sweep(비키프레임) 한 장은 변환하지 않는다.

YOLO 정규화 (car [100,200,300,400]):
cx = 200/1600 = 0.125, cy = 300/900 = 0.333333, w = 200/1600 = 0.125, h = 200/900 = 0.222222
경계 밖 car는 [1590,880,1600,900]으로 자른다 → cx = 1595/1600 = 0.996875, cy = 890/900 = 0.988889,
w = 10/1600 = 0.00625, h = 20/900 = 0.022222
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nuimages_to_yolo as N  # noqa: E402


def tables():
    return {
        "category": [{"token": "c_car", "name": "vehicle.car"},
                     {"token": "c_truck", "name": "vehicle.truck"}],
        "log": [{"token": "logA", "location": "boston-seaport"},
                {"token": "logB", "location": "singapore-onenorth"}],
        "sensor": [{"token": "sf", "channel": "CAM_FRONT"},
                   {"token": "sb", "channel": "CAM_BACK"}],
        "calibrated_sensor": [{"token": "cf", "sensor_token": "sf"},
                              {"token": "cb", "sensor_token": "sb"}],
        "sample": [{"token": "s1", "log_token": "logA", "key_camera_token": "d1"},
                   {"token": "s2", "log_token": "logB", "key_camera_token": "d2"}],
        "sample_data": [
            {"token": "d1", "sample_token": "s1", "is_key_frame": True, "width": 1600,
             "height": 900, "filename": "samples/CAM_FRONT/a.jpg", "calibrated_sensor_token": "cf"},
            {"token": "d2", "sample_token": "s2", "is_key_frame": True, "width": 1600,
             "height": 900, "filename": "samples/CAM_BACK/b.jpg", "calibrated_sensor_token": "cb"},
            {"token": "d3", "sample_token": "s1", "is_key_frame": False, "width": 1600,
             "height": 900, "filename": "sweeps/CAM_FRONT/a_prev.jpg", "calibrated_sensor_token": "cf"},
        ],
        "object_ann": [
            {"token": "o1", "sample_data_token": "d1", "category_token": "c_car", "bbox": [100, 200, 300, 400]},
            {"token": "o2", "sample_data_token": "d1", "category_token": "c_truck", "bbox": [0, 0, 50, 50]},
            {"token": "o3", "sample_data_token": "d1", "category_token": "c_car", "bbox": [1590, 880, 1650, 950]},
            {"token": "o4", "sample_data_token": "d2", "category_token": "c_car", "bbox": [10, 20, 10, 40]},
        ],
    }


def test_키프레임만_이미지로_삼는다():
    rows = N.keyframes(tables())
    assert [r["sample_data_token"] for r in rows] == ["d1", "d2"]
    assert [(r["camera"], r["log_token"], r["location"]) for r in rows] == [
        ("CAM_FRONT", "logA", "boston-seaport"), ("CAM_BACK", "logB", "singapore-onenorth")]


def test_카메라로_거를_수_있다():
    rows = N.keyframes(tables(), cameras={"CAM_FRONT"})
    assert [r["sample_data_token"] for r in rows] == ["d1"]


def test_고른_범주만_YOLO_줄이_되고_좌표를_정규화한다():
    lines, report = N.yolo_lines(tables(), "d1", 1600, 900, {"vehicle.car": 0})
    assert lines == ["0 0.125000 0.333333 0.125000 0.222222",
                     "0 0.996875 0.988889 0.006250 0.022222"]
    assert report == {"kept": 2, "other_category": 1, "clipped": 1, "degenerate": 0}


def test_폭이나_높이가_0인_상자는_버리고_센다():
    lines, report = N.yolo_lines(tables(), "d2", 1600, 900, {"vehicle.car": 0})
    assert lines == []
    assert report == {"kept": 0, "other_category": 0, "clipped": 0, "degenerate": 1}


def test_여러_범주를_한_클래스로_모을_수_있다():
    lines, _ = N.yolo_lines(tables(), "d1", 1600, 900, {"vehicle.car": 0, "vehicle.truck": 0})
    assert len(lines) == 3 and all(line.startswith("0 ") for line in lines)


def test_모르는_범주_이름은_거부한다():
    with pytest.raises(ValueError, match="vehicle.van"):
        N.check_categories(tables(), {"vehicle.van": 0})


def test_변환하면_YOLO_폴더와_출처_명세가_생긴다(tmp_path):
    src = tmp_path / "nuimages"
    (src / "v1.0-mini").mkdir(parents=True)
    for name, rows in tables().items():
        (src / "v1.0-mini" / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")
    for rel in ("samples/CAM_FRONT/a.jpg", "samples/CAM_BACK/b.jpg"):
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_bytes(b"\xff\xd8fake")
    out = tmp_path / "yolo"

    manifest = N.convert(src, "v1.0-mini", out, {"vehicle.car": 0}, class_names=["Car"])

    assert sorted(p.name for p in (out / "images").iterdir()) == ["a.jpg", "b.jpg"]
    assert (out / "labels" / "a.txt").read_text(encoding="utf-8").splitlines() == [
        "0 0.125000 0.333333 0.125000 0.222222", "0 0.996875 0.988889 0.006250 0.022222"]
    assert (out / "labels" / "b.txt").read_text(encoding="utf-8") == ""   # 빈 라벨도 남긴다
    assert (out / "classes.txt").read_text(encoding="utf-8").splitlines() == ["Car"]
    assert manifest["images"] == 2 and manifest["labels"] == 2
    assert manifest["report"] == {"kept": 2, "other_category": 1, "clipped": 1, "degenerate": 1}
    rows = {r["image"]: r for r in manifest["rows"]}
    assert rows["a.jpg"]["log_token"] == "logA" and rows["b.jpg"]["camera"] == "CAM_BACK"
    assert json.loads((out / "nuimages_manifest.json").read_text(encoding="utf-8")) == manifest


def test_이미_있는_출력_폴더에는_쓰지_않는다(tmp_path):
    out = tmp_path / "yolo"
    (out / "images").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        N.convert(tmp_path / "없음", "v1.0-mini", out, {"vehicle.car": 0}, class_names=["Car"])
