"""어느 자로 쟀는지 결과에 남기는가 (docs/21 AA·AD).

AA와 AD가 같은 말을 한다: 대상 분포에서의 실력이 전부다. 학습량도 클래스
폭도 그 자체로는 진단 품질을 정하지 않는다. 그런데 지금까지 결과에는 어느
기준 모델을 썼는지가 안 남아서, 사용자가 그 판단을 할 근거가 없었다.

특히 중요한 건 **자가 모르는 클래스**다. 그 라벨은 오탐으로도 안 나오고
아예 검사되지 않는다 — 화면에 아무 흔적이 없어서 "문제 없음"과 구별이 안 된다.
"""
import json

import pytest

from app.models import RulerInfo
from app.routers import upload


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    """labels/ 아래 라벨 몇 개가 있는 업로드 폴더."""
    root = tmp_path / "uploads"
    (root / "ds1" / "labels").mkdir(parents=True)
    monkeypatch.setattr(upload, "UPLOADS_DIR", root)
    return root / "ds1"


def write_label(dataset, name: str, class_ids: list[int]) -> None:
    (dataset / "labels" / name).write_text(
        "\n".join(f"{c} 0.5 0.5 0.2 0.2" for c in class_ids) + "\n", encoding="utf-8")


def test_default_ruler_is_single_class(dataset):
    write_label(dataset, "a.txt", [0, 0])
    info = upload._ruler_info(None, dataset)
    assert info.profile == ""
    assert info.classes == ["Car"]
    # 단일 클래스 자는 클래스 대조를 하지 않는다 — 비교할 클래스가 하나뿐이다
    assert info.class_aware is False
    assert info.unknown_class_ids == []


def test_unknown_class_ids_are_reported(dataset):
    """Car만 아는 자에 4클래스 데이터를 주면, 나머지는 조용히 빠진다."""
    write_label(dataset, "a.txt", [0, 1, 3])
    info = upload._ruler_info(None, dataset)
    assert info.unknown_class_ids == [1, 3]


def test_label_class_ids_ignores_broken_lines(dataset):
    """라벨이 깨져 경로 문자열이 들어 있어도 죽지 않아야 한다.

    실제로 겪은 사고다 — git이 심볼릭 링크를 경로가 담긴 텍스트 파일로
    복원했다(docs/21 AC).
    """
    (dataset / "labels" / "broken.txt").write_text(
        "C:/Users/x/labels/000001.txt\n", encoding="utf-8")
    write_label(dataset, "ok.txt", [2])
    assert upload._label_class_ids(dataset) == {2}


def test_seed_spread_differs_by_class_width(dataset):
    """단일 클래스 자가 다중 클래스 자보다 학습 시드에 덜 흔들린다 (AD)."""
    assert upload.RULER_SEED_SPREAD_PP[1] < upload.RULER_SEED_SPREAD_PP[4]


def test_sidecar_round_trip(dataset):
    """진단 뒤 GET으로 다시 불러와도 자가 남아 있어야 한다.

    리포트를 나중에 여는 게 정상 사용이므로, 응답에만 담으면 사라진다.
    """
    info = upload._ruler_info(None, dataset)
    upload._save_ruler_sidecar("ds1", info)
    assert upload._load_ruler_sidecar("ds1") == info


def test_missing_sidecar_is_not_an_error(dataset):
    """이 기능 전에 만든 결과에는 사이드카가 없다. 그때는 자를 모른다고 한다."""
    assert upload._load_ruler_sidecar("ds1") is None


def test_corrupt_sidecar_is_not_an_error(dataset):
    (dataset / upload.RULER_SIDECAR).write_text("{", encoding="utf-8")
    assert upload._load_ruler_sidecar("ds1") is None


def test_ruler_weights_follow_config_layout():
    """config.py가 클래스 구성마다 실행 폴더를 나눠 쓴다. 여기도 같아야 한다.

    다르면 화면에 표시하는 자와 진단이 실제로 여는 자가 어긋난다.
    """
    assert upload._ruler_weights(["Car"]).parent.parent.parent.name == "runs"
    assert upload._ruler_weights(
        ["Car", "Van", "Pedestrian", "Cyclist"]).parent.parent.parent.name == "runs_mc"


def test_sidecar_is_json_the_frontend_can_read(dataset):
    upload._save_ruler_sidecar("ds1", upload._ruler_info(None, dataset))
    data = json.loads((dataset / upload.RULER_SIDECAR).read_text(encoding="utf-8"))
    assert set(RulerInfo.model_fields) <= set(data)
