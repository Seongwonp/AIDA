"""nuImages train을 자 학습용 / 적합도 확인용으로 나누기 (docs/nuimages-data-plan.md).

지키는 것 셋.

1. **val·test를 읽지 않는다.** 평가용 부분은 사전 등록 전까지 열지 않는다.
2. **같은 주행 기록(log)이 양쪽에 들어가지 않는다.** 같은 기록의 이웃 프레임이 학습과 확인에
   갈라 들어가면 확인 수치가 부풀려진다.
3. **씨앗으로 다시 만들 수 있다.**

손계산 세계 — 기록 넷, 키프레임 여덟(기록마다 둘). sweep 하나는 세지 않는다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nuimages_split as S  # noqa: E402


def tables():
    logs = ["L1", "L2", "L3", "L4"]
    sample, sample_data = [], []
    for i, log in enumerate(logs):
        for j in range(2):
            s = f"s{i}{j}"
            cam = "sf" if j == 0 else "sb"
            sample.append({"token": s, "log_token": log})
            sample_data.append({"token": f"d{i}{j}", "sample_token": s, "is_key_frame": True,
                                "calibrated_sensor_token": cam, "filename": f"samples/x/{s}.jpg"})
    sample_data.append({"token": "sweep", "sample_token": "s00", "is_key_frame": False,
                        "calibrated_sensor_token": "sf", "filename": "sweeps/x/p.jpg"})
    return {
        "log": [{"token": t, "location": "boston-seaport" if t in ("L1", "L2") else "singapore-onenorth"}
                for t in logs],
        "sensor": [{"token": "s_front", "channel": "CAM_FRONT"},
                   {"token": "s_back", "channel": "CAM_BACK"}],
        "calibrated_sensor": [{"token": "sf", "sensor_token": "s_front"},
                              {"token": "sb", "sensor_token": "s_back"}],
        "sample": sample,
        "sample_data": sample_data,
    }


def test_train이_아닌_분할은_거부한다():
    for version in ("v1.0-val", "v1.0-test", "v1.0-mini"):
        with pytest.raises(ValueError, match="train"):
            S.check_version(version)
    S.check_version("v1.0-train")


def test_기록이_양쪽에_겹치지_않는다():
    split = S.split_by_log(tables(), fit_check_images=4, ruler_train_images=4, seed=1)
    ruler_logs = {r["log_token"] for r in split["ruler_train"]}
    check_logs = {r["log_token"] for r in split["fit_check"]}
    assert ruler_logs and check_logs
    assert not ruler_logs & check_logs


def test_목표_수만큼_뽑고_모자라면_있는_만큼만():
    split = S.split_by_log(tables(), fit_check_images=2, ruler_train_images=100, seed=1)
    assert len(split["fit_check"]) == 2                 # 기록 하나가 키프레임 둘
    assert len(split["ruler_train"]) == 6               # 남은 기록 셋 × 둘
    assert split["summary"]["ruler_train_shortfall"] == 94


def test_씨앗으로_다시_만들_수_있다():
    a = S.split_by_log(tables(), fit_check_images=4, ruler_train_images=4, seed=7)
    b = S.split_by_log(tables(), fit_check_images=4, ruler_train_images=4, seed=7)
    c = S.split_by_log(tables(), fit_check_images=4, ruler_train_images=4, seed=8)
    tokens = lambda s: ([r["sample_data_token"] for r in s["fit_check"]],
                        [r["sample_data_token"] for r in s["ruler_train"]])
    assert tokens(a) == tokens(b)
    assert any(tokens(a) != tokens(S.split_by_log(tables(), 4, 4, seed=s)) for s in range(8, 20))
    assert c["summary"]["seed"] == 8


def test_카메라로_거를_수_있다():
    split = S.split_by_log(tables(), fit_check_images=2, ruler_train_images=2, seed=1,
                           cameras={"CAM_FRONT"})
    assert {r["camera"] for r in split["fit_check"] + split["ruler_train"]} == {"CAM_FRONT"}


def test_sweep은_세지_않는다():
    split = S.split_by_log(tables(), fit_check_images=100, ruler_train_images=100, seed=1)
    all_tokens = [r["sample_data_token"] for r in split["fit_check"] + split["ruler_train"]]
    assert "sweep" not in all_tokens
    assert len(all_tokens) == 8


def test_요약에_기록_수와_지역이_남는다():
    split = S.split_by_log(tables(), fit_check_images=4, ruler_train_images=4, seed=1)
    summary = split["summary"]
    assert summary["fit_check_logs"] + summary["ruler_train_logs"] <= 4
    assert set(summary["ruler_train_by_location"]) | set(summary["fit_check_by_location"]) <= {
        "boston-seaport", "singapore-onenorth"}


def test_학습_검증용은_학습용과_확인용_어느_쪽과도_기록이_겹치지_않는다():
    """학습 중 best.pt를 고르는 데 확인용을 쓰면 확인 수치가 부풀려진다. 그래서 따로 둔다."""
    split = S.split_by_log(tables(), fit_check_images=2, ruler_train_images=100, seed=3,
                           ruler_val_images=2)
    logs = {name: {r["log_token"] for r in split[name]}
            for name in ("fit_check", "ruler_val", "ruler_train")}
    assert all(logs.values())
    assert not logs["fit_check"] & logs["ruler_val"]
    assert not logs["fit_check"] & logs["ruler_train"]
    assert not logs["ruler_val"] & logs["ruler_train"]
    assert split["summary"]["ruler_val_images"] == 2


def test_학습_검증용을_안_달라면_비어_있다():
    split = S.split_by_log(tables(), fit_check_images=2, ruler_train_images=2, seed=3)
    assert split["ruler_val"] == [] and split["summary"]["ruler_val_images"] == 0
