"""신뢰도 프로파일 API.

유형 신뢰도 상수는 도메인을 탄다 — 다중 클래스로 검증했을 때 "그 유형이
없을 때"의 값이 크게 흔들렸다(docs/21 L, 누락 88% → 22%). 그래서 데이터셋마다
보정 프로파일을 골라 쓸 수 있어야 한다.
"""
import shutil

import pytest

from app.routers import upload


def test_default_profile_is_always_first(client):
    """프로파일 파일이 하나도 없어도 기본값은 고를 수 있어야 한다."""
    rows = client.get("/api/datasets/reliability-profiles").json()
    assert rows[0]["name"] == ""


def test_profiles_expose_their_calibrated_types(client):
    rows = client.get("/api/datasets/reliability-profiles").json()
    for row in rows[1:]:
        assert row["types"], f"{row['name']}에 보정된 유형이 없음"


def test_unknown_profile_is_rejected():
    """이름을 그대로 경로로 쓰면 임의 파일을 읽히는 통로가 된다."""
    from fastapi import HTTPException
    for bad in ["../../etc/passwd", "없는프로파일", "/tmp/x"]:
        with pytest.raises(HTTPException) as e:
            upload._resolve_profile(bad)
        assert e.value.status_code == 400


def test_no_profile_means_no_env_override():
    """기본값을 골랐으면 진단 서브프로세스에 아무것도 안 넘긴다."""
    assert upload._profile_env(None) == {}
    assert upload._profile_env("") == {}


def test_known_profile_resolves_under_experiment_root(fake_experiment):
    """이 검사가 보는 건 자가 진짜인지가 아니라 **배선이 맞는지**다.

    그래서 자리표시자 자를 놓은 가짜 루트에서 돈다. 원래는 이 기계에 학습된
    자가 없으면 건너뛰었는데, 그러면 CI에서 통째로 빠지고 "여기서만 통과하는
    검사"가 된다.
    """
    env = upload._profile_env("mc")
    assert env["AIDA_RELIABILITY_PROFILE"].endswith("reliability_profile_mc.json")
    root, _ = fake_experiment
    assert env["AIDA_RELIABILITY_PROFILE"].startswith(str(root))


def test_profile_carries_its_class_configuration(fake_experiment):
    """상수만 갈아끼우고 클래스 구성이 그대로면 반쪽짜리다.

    그 상수는 특정 클래스 구성에서 잰 값이라, 진단도 같은 구성(같은 기준
    모델·같은 클래스 인덱스)으로 돌아가야 한다.
    """
    env = upload._profile_env("mc")
    assert env["AIDA_CLASSES"] == "Car,Van,Pedestrian,Cyclist"


def test_profile_without_its_ruler_is_refused(fake_experiment):
    """프로파일 파일은 있는데 그 자가 없으면 진단을 시작하면 안 된다.

    상수만 바꾸고 엉뚱한 자로 돌면 화면에는 그 프로파일 이름이 찍히는데
    실제로는 다른 자로 잰 결과가 된다 (docs/21 AI에서 26.0%까지 무너졌다).
    """
    from fastapi import HTTPException

    root, _ = fake_experiment
    shutil.rmtree(root / "runs_mc")            # 자만 치운다
    with pytest.raises(HTTPException) as e:
        upload._profile_env("mc")
    assert e.value.status_code == 400


def test_profile_listing_exposes_classes(client):
    rows = client.get("/api/datasets/reliability-profiles").json()
    assert rows[0]["classes"] == ["Car"]


def test_unavailable_profile_is_rejected_before_running(fake_experiment, monkeypatch):
    """기준 모델이 없는 프로파일은 서브프로세스 오류가 아니라 400으로 막는다."""
    from fastapi import HTTPException
    names = upload._available_profiles()
    assert names, "가짜 루트에 프로파일이 있어야 한다"
    # _weights_exist는 이제 데이터셋도 받는다 — 프로파일이 어느 데이터셋의
    # 자를 쓰는지 밝히지 않으면 COCO 프로파일이 KITTI 자를 조용히 연다.
    monkeypatch.setattr(upload, "_weights_exist", lambda classes, dataset="kitti": False)
    with pytest.raises(HTTPException) as e:
        upload._profile_env(names[0])
    assert e.value.status_code == 400


def test_listing_marks_availability(client):
    rows = client.get("/api/datasets/reliability-profiles").json()
    assert all("available" in row for row in rows)
