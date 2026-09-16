"""외부 데이터(nuImages 등) YOLO 폴더로 자를 학습하는 준비 단계 (docs/nuimages-data-plan.md).

**학습 자체는 검사하지 않는다**(GPU·시간). 여기서는 학습 전에 막아야 할 것을 본다 — 폴더 모양,
클래스 목록 일치, 이미 있는 실행을 덮어쓰지 않기, 데이터 설정 파일 내용.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import train_external_ruler as T  # noqa: E402


def yolo_folder(root: Path, classes=("Car",), images=2):
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    for i in range(images):
        (root / "images" / f"{i}.jpg").write_bytes(b"\xff\xd8")
        (root / "labels" / f"{i}.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
    (root / "classes.txt").write_text("".join(c + "\n" for c in classes), encoding="utf-8")
    return root


def test_폴더_모양을_확인하고_클래스_목록을_돌려준다(tmp_path):
    folder = yolo_folder(tmp_path / "train")
    assert T.check_folder(folder) == (["Car"], 2)


def test_이미지나_라벨이_없으면_거부한다(tmp_path):
    with pytest.raises(ValueError, match="images"):
        T.check_folder(tmp_path / "없음")
    folder = yolo_folder(tmp_path / "train", images=0)
    with pytest.raises(ValueError, match="이미지가 없다"):
        T.check_folder(folder)


def test_학습과_검증의_클래스_목록이_다르면_거부한다(tmp_path):
    train = yolo_folder(tmp_path / "train", classes=("Car",))
    val = yolo_folder(tmp_path / "val", classes=("Car", "Van"))
    with pytest.raises(ValueError, match="클래스"):
        T.prepare(train, val, tmp_path / "runs", "car_v1")


def test_이미_있는_실행_이름은_덮어쓰지_않는다(tmp_path):
    train = yolo_folder(tmp_path / "train")
    val = yolo_folder(tmp_path / "val")
    (tmp_path / "runs" / "car_v1").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        T.prepare(train, val, tmp_path / "runs", "car_v1")


def test_데이터_설정에_학습_검증_경로와_클래스가_들어간다(tmp_path):
    train = yolo_folder(tmp_path / "train")
    val = yolo_folder(tmp_path / "val")
    plan = T.prepare(train, val, tmp_path / "runs", "car_v1")
    data = json.loads(plan["data_yaml"].read_text(encoding="utf-8"))   # JSON은 YAML의 부분집합이다
    assert data == {"train": str((train / "images").resolve()),
                    "val": str((val / "images").resolve()),
                    "names": {"0": "Car"}}
    assert plan["run_dir"] == tmp_path / "runs" / "car_v1"
    assert plan["counts"] == {"train_images": 2, "val_images": 2}


def test_점검만_하면_실행_폴더를_만들지_않는다(tmp_path):
    """만들면 다음 실제 학습이 "이미 있다"로 막힌다."""
    train = yolo_folder(tmp_path / "train")
    val = yolo_folder(tmp_path / "val")
    plan = T.prepare(train, val, tmp_path / "runs", "car_v1", write=False)
    assert not plan["run_dir"].exists()
    T.prepare(train, val, tmp_path / "runs", "car_v1")          # 그 뒤 실제 준비는 된다
