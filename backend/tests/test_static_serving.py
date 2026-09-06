"""빌드된 프론트를 같이 서빙할 때 API가 안 가려지는가.

Dockerfile이 프론트 빌드를 /app/static에 넣고 백엔드가 그걸 서빙한다.
**마운트 순서를 잘못 잡으면 "/" 가 /api/* 를 통째로 삼킨다** — 그러면 화면은
뜨는데 데이터가 전부 index.html로 돌아온다.

로컬 개발에는 static 폴더가 없으므로 이 검사들은 그때 건너뛴다.
"""
import shutil

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def served(tmp_path, monkeypatch):
    """static 폴더가 있는 상태의 앱을 새로 만든다."""
    import importlib
    import app.main as m

    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>AIDA</html>", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (static / "favicon.ico").write_bytes(b"\x00")

    monkeypatch.setattr(m.Path, "resolve", m.Path.resolve)  # 원본 유지
    monkeypatch.setenv("AIDA_STATIC_FOR_TEST", str(static))

    # main은 import 시점에 static 위치를 정하므로 다시 읽어야 한다
    src = (static.parent / "patched_main.py")
    module_src = (m.__file__)
    text = open(module_src, encoding="utf-8").read().replace(
        'Path(__file__).resolve().parent.parent / "static"',
        f'Path(r"{static}")')
    src.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("patched_main", src)
    patched = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patched)
    return TestClient(patched.app)


def test_api_still_answers_when_static_is_mounted(served):
    """이게 핵심이다. "/" 마운트가 /api/* 를 삼키면 안 된다."""
    res = served.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_unknown_path_falls_back_to_index(served):
    """라우팅은 브라우저가 한다 — 어느 경로든 index.html을 줘야 한다."""
    res = served.get("/some/spa/route")
    assert res.status_code == 200
    assert "AIDA" in res.text


def test_real_files_are_served_as_themselves(served):
    """favicon이 index.html로 나가면 안 된다."""
    assert served.get("/favicon.ico").content == b"\x00"
    assert "console.log" in served.get("/assets/app.js").text


def test_static_absent_means_no_spa_route():
    """로컬 개발에는 static이 없다. 그때 SPA 폴백이 붙으면 안 된다."""
    from app.main import _STATIC, app
    if _STATIC.is_dir():
        pytest.skip("이 환경에는 빌드된 프론트가 있다")
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/health" in paths
    assert "/{full_path:path}" not in paths, "static이 없는데 SPA 폴백이 붙었다"
