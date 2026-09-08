"""업로드 경로 설정과 진단 스크립트의 경로 사용이 일치하는가 (docs/24 B).

백엔드의 `UPLOADS_DIR`은 환경변수로 바꿀 수 있다(Docker 볼륨 등). 진단은
서브프로세스로 도는데 `--upload-id`만 받고 **환경은 그대로 물려받는다.**

그런데 스크립트가 그 환경변수를 안 읽고 경로를 박아두면 백엔드는 X에 쓰고
스크립트는 Y에서 찾는다. 진단이 "데이터셋을 찾을 수 없습니다"로 죽거나 —
더 나쁘게는 **다른 데이터셋을 읽는다.** 실제로 그랬다.

수치가 아니라 규칙이라 CI에서 잴 수 있다. 경로 해석을 `config`에 둔 이유도
그것이다 — 진단 스크립트는 ultralytics를 물어서 백엔드 환경에서 못 부른다.
"""
import sys
from pathlib import Path

import pytest

EXPERIMENT = Path(__file__).resolve().parents[2] / "experiment"
if str(EXPERIMENT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT))


@pytest.fixture()
def experiment_config():
    return pytest.importorskip("config", reason="experiment/ 코드를 못 읽는 환경")


def test_default_matches_the_backend(experiment_config):
    from app.config import UPLOADS_DIR as backend_dir
    assert experiment_config.uploads_dir() == backend_dir, \
        "실험 쪽 기본 업로드 경로가 백엔드와 다르다"


def test_env_override_is_honoured(experiment_config, monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "somewhere"))
    assert experiment_config.uploads_dir() == tmp_path / "somewhere", \
        "UPLOADS_DIR 환경변수를 무시한다"


def test_read_at_call_time_not_import_time(experiment_config, monkeypatch, tmp_path):
    """모듈을 불러온 뒤에 환경이 바뀌어도 따라가야 한다.

    서브프로세스는 매번 새로 뜨지만 검사와 다른 호출자는 그렇지 않다.
    상수로 굳혀 두면 이 검사가 잡는다.
    """
    first = experiment_config.uploads_dir()
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "later"))
    assert experiment_config.uploads_dir() != first
    assert experiment_config.uploads_dir() == tmp_path / "later"


def test_scripts_use_the_shared_resolver():
    """경로를 다시 박아 넣으면 잡는다."""
    for name in ("diagnose_labels.py", "diagnose_upload.py"):
        src = (EXPERIMENT / name).read_text(encoding="utf-8")
        assert "config.uploads_dir()" in src, f"{name}이 공용 해석기를 안 쓴다"
        assert '"backend" / "app" / "data" / "uploads"' not in src, \
            f"{name}이 업로드 경로를 박아뒀다"


def test_backend_forwards_the_environment():
    """서브프로세스가 환경을 물려받는지. 안 물려받으면 위의 것들이 소용없다."""
    src = (Path(__file__).resolve().parents[1] / "app" / "routers"
           / "upload.py").read_text(encoding="utf-8")
    assert "env={**os.environ" in src, "서브프로세스가 환경을 못 물려받는다"
