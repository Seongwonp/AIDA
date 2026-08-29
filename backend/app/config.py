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
AGG_METRICS_CSV_PATH = Path(os.environ.get("AGG_METRICS_CSV_PATH", str(BACKEND_ROOT / "app" / "data" / "metrics_agg.csv")))
OBB_AGG_METRICS_CSV_PATH = Path(os.environ.get("OBB_AGG_METRICS_CSV_PATH", str(BACKEND_ROOT / "app" / "data" / "metrics_obb_agg.csv")))
IOU_TABLE_CSV_PATH = Path(os.environ.get("IOU_TABLE_CSV_PATH", str(PROJECT_ROOT / "experiment" / "iou_table.csv")))

# 고객 데이터셋 업로드 (docs/21 C). 실제 추론(ultralytics/torch 필요)은 backend가
# 아니라 experiment/venv 쪽에서 서브프로세스로 돌린다 — report.py가 experiment/의
# 결과 CSV만 읽고 무거운 ML 의존성을 backend에 얹지 않는 것과 같은 이유다.
UPLOADS_DIR = Path(os.environ.get("UPLOADS_DIR", str(BACKEND_ROOT / "app" / "data" / "uploads")))
EXPERIMENT_ROOT = Path(os.environ.get("EXPERIMENT_ROOT", str(PROJECT_ROOT / "experiment")))


def _default_experiment_python() -> str:
    win_python = EXPERIMENT_ROOT / "venv" / "Scripts" / "python.exe"
    if win_python.exists():
        return str(win_python)
    return str(EXPERIMENT_ROOT / "venv" / "bin" / "python")


EXPERIMENT_PYTHON = Path(os.environ.get("EXPERIMENT_PYTHON", _default_experiment_python()))
