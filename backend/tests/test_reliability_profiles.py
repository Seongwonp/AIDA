"""신뢰도 프로파일 API.

유형 신뢰도 상수는 도메인을 탄다 — 다중 클래스로 검증했을 때 "그 유형이
없을 때"의 값이 크게 흔들렸다(docs/21 L, 누락 88% → 22%). 그래서 데이터셋마다
보정 프로파일을 골라 쓸 수 있어야 한다.
"""
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


def _profiles_with_weights() -> list[str]:
    """프로파일 파일이 있고 **그 자(가중치)까지 있는** 것만.

    프로파일 JSON은 저장소에 들어 있지만 학습 가중치는 아니다. 자가 없으면
    _profile_env가 400을 내는 게 맞는 동작이므로, 여기서 그걸 실패로 셀 일이
    아니다 — 이 검사가 보려는 건 환경변수 배선이다.
    """
    out = []
    for name in upload._available_profiles():
        path = upload._resolve_profile(name)
        if upload._weights_exist(upload._profile_classes(path),
                                 upload._profile_dataset(path)):
            out.append(name)
    return out


def test_known_profile_resolves_under_experiment_root():
    names = _profiles_with_weights()
    if not names:
        pytest.skip("이 환경에 기준 모델이 학습돼 있는 프로파일이 없음")
    env = upload._profile_env(names[0])
    assert env["AIDA_RELIABILITY_PROFILE"].endswith(f"reliability_profile_{names[0]}.json")


def test_profile_carries_its_class_configuration():
    """상수만 갈아끼우고 클래스 구성이 그대로면 반쪽짜리다.

    그 상수는 특정 클래스 구성에서 잰 값이라, 진단도 같은 구성(같은 기준
    모델·같은 클래스 인덱스)으로 돌아가야 한다.
    """
    names = [n for n in _profiles_with_weights()
             if upload._profile_classes(upload._resolve_profile(n))]
    if not names:
        pytest.skip("클래스 구성이 적혀 있고 기준 모델도 있는 프로파일이 없음")
    env = upload._profile_env(names[0])
    assert "AIDA_CLASSES" in env and env["AIDA_CLASSES"]


def test_profile_listing_exposes_classes(client):
    rows = client.get("/api/datasets/reliability-profiles").json()
    assert rows[0]["classes"] == ["Car"]


def test_unavailable_profile_is_rejected_before_running(monkeypatch):
    """기준 모델이 없는 프로파일은 서브프로세스 오류가 아니라 400으로 막는다."""
    from fastapi import HTTPException
    names = upload._available_profiles()
    if not names:
        pytest.skip("보정 프로파일 파일이 이 환경에 없음")
    # _weights_exist는 이제 데이터셋도 받는다 — 프로파일이 어느 데이터셋의
    # 자를 쓰는지 밝히지 않으면 COCO 프로파일이 KITTI 자를 조용히 연다.
    monkeypatch.setattr(upload, "_weights_exist", lambda classes, dataset="kitti": False)
    with pytest.raises(HTTPException) as e:
        upload._profile_env(names[0])
    assert e.value.status_code == 400


def test_listing_marks_availability(client):
    rows = client.get("/api/datasets/reliability-profiles").json()
    assert all("available" in row for row in rows)
