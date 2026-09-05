import os
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
FIXTURE_CSV = TESTS_DIR / "fixtures" / "metrics.csv"
FIXTURE_IOU_CSV = TESTS_DIR / "fixtures" / "iou_table.csv"
FIXTURE_AGG_CSV = TESTS_DIR / "fixtures" / "metrics_agg.csv"

# app.config는 import 시점에 환경변수를 읽으므로, app을 import하기 전에 설정해야 한다.
os.environ.setdefault("METRICS_CSV_PATH", str(FIXTURE_CSV))
os.environ.setdefault("IOU_TABLE_CSV_PATH", str(FIXTURE_IOU_CSV))
os.environ.setdefault("AGG_METRICS_CSV_PATH", str(FIXTURE_AGG_CSV))
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fake_experiment(tmp_path, monkeypatch):
    """자리표시자 자가 놓인 가짜 experiment 루트.

    `_weights_exist`는 파일이 있는지만 보므로, 경로 규칙과 프로파일 해석을
    검사하는 데는 진짜 가중치가 필요 없다. 이렇게 해야 CI에서도 돌고 **로컬
    환경에 따라 결과가 달라지지 않는다**.

    돌려주는 것은 (experiment_root, uploads_dir).
    """
    from tests import fake_experiment as fake
    from app.routers import upload

    root = tmp_path / "experiment"
    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    fake.build(root, uploads)

    monkeypatch.setattr(upload, "EXPERIMENT_ROOT", root)
    monkeypatch.setattr(upload, "EXPERIMENT_PYTHON", fake.python_path())
    monkeypatch.setattr(upload, "UPLOADS_DIR", uploads)
    return root, uploads
