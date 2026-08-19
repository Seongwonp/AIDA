"""환경변수 기반 설정. 값은 .env 파일(없으면 OS 환경변수)에서 읽는다.

실제 값은 .env에 두고, .env.example에는 키 목록과 기본값만 문서화한다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
CORS_ORIGINS = _split_csv(os.environ.get("CORS_ORIGINS", "http://localhost:5173"))
METRICS_CSV_PATH = Path(os.environ.get("METRICS_CSV_PATH", str(BACKEND_ROOT / "app" / "data" / "metrics.csv")))
OBB_METRICS_CSV_PATH = Path(os.environ.get("OBB_METRICS_CSV_PATH", str(BACKEND_ROOT / "app" / "data" / "metrics_obb.csv")))
IOU_TABLE_CSV_PATH = Path(os.environ.get("IOU_TABLE_CSV_PATH", str(PROJECT_ROOT / "experiment" / "iou_table.csv")))
