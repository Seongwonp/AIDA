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
