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


# --- 기준 모델 추천 -------------------------------------------------------
#
# 서버는 고객 분포를 미리 알 수 없다. 다만 "자가 아예 모르는 클래스가 있는가"는
# 라벨만 보고도 안다 — 그건 품질 문제가 아니라 구멍이다.

def test_no_suggestion_when_default_covers_the_data():
    """Car 하나뿐이면 기본 기준 모델로 충분하다. 넓힐 이유가 없다."""
    name, reason = upload._suggest_profile({0})
    assert name is None
    assert reason == ""


def test_empty_labels_get_no_suggestion():
    assert upload._suggest_profile(set()) == (None, "")


def test_suggests_a_wider_ruler_when_classes_exceed_default():
    """클래스 3이 있으면 4개를 아는 자가 필요하다."""
    name, reason = upload._suggest_profile({0, 3})
    if not upload._weights_exist(["Car", "Van", "Pedestrian", "Cyclist"]):
        pytest.skip("다중 클래스 기준 모델이 이 환경에 없음")
    assert name, "더 넓은 자가 있는데 추천하지 않았다"
    assert "3" in reason


def test_suggestion_explains_itself_when_nothing_covers():
    """덮는 자가 없으면 조용히 넘어가지 말고 왜인지 말해야 한다."""
    name, reason = upload._suggest_profile({0, 99})
    assert name is None
    assert reason, "덮는 자가 없는데 아무 설명이 없다"
    assert "검사되지 않습니다" in reason


def test_suggestion_prefers_the_narrowest_covering_ruler():
    """Z·AA: 실력이 비슷하면 좁은 쪽이 낫다. 덮기만 하면 넓힐 이유가 없다."""
    name, _ = upload._suggest_profile({0})
    assert name is None, "Car만 있는 데이터에 더 넓은 자를 권했다"
