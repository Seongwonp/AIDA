"""고객 데이터셋 업로드 → 진단 API (docs/21 C).

업로드된 zip은 UPLOADS_DIR/<dataset_id>/에 풀리고, 실제 추론(ultralytics/
torch 의존)은 backend가 아니라 experiment/venv 쪽에서 서브프로세스로
돌린다 — report.py가 experiment/의 결과 CSV만 읽고 무거운 ML 의존성을
backend에 얹지 않는 것과 같은 구조다.
"""
import json
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.config import EXPERIMENT_PYTHON, EXPERIMENT_ROOT, UPLOADS_DIR
from app.models import ErrorTypeCandidate, PerformanceVector, UploadDiagnosisResult, UploadedDatasetInfo
from app.routers.report import TYPE_LABELS

router = APIRouter(prefix="/api/datasets", tags=["upload"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB
DIAGNOSE_TIMEOUT_SEC = 300


def _validate_dataset_dir(dataset_dir: Path) -> tuple[int, int]:
    images_dir = dataset_dir / "images"
    labels_dir = dataset_dir / "labels"
    if not images_dir.is_dir() or not labels_dir.is_dir():
        raise HTTPException(
            400,
            "zip 안에 images/ 와 labels/ 폴더가 있어야 합니다 "
            "(YOLO 포맷: images/xxx.jpg + labels/xxx.txt, 클래스는 1개만 지원).",
        )
    n_images = sum(1 for p in images_dir.iterdir() if p.is_file())
    n_labels = sum(1 for _ in labels_dir.glob("*.txt"))
    if n_images == 0:
        raise HTTPException(400, "images/ 폴더가 비어 있습니다.")
    return n_images, n_labels


def _load_diagnosis_json(dataset_id: str) -> UploadDiagnosisResult:
    result_path = UPLOADS_DIR / dataset_id / "diagnosis.json"
    if not result_path.exists():
        raise HTTPException(404, "아직 진단하지 않았습니다. POST .../diagnose를 먼저 호출하세요.")

    data = json.loads(result_path.read_text(encoding="utf-8"))
    candidates = [
        ErrorTypeCandidate(
            error_type=c["error_type"],
            label=TYPE_LABELS.get(c["error_type"], c["error_type"]),
            closest_condition=c["closest_condition"],
            closest_magnitude=c["closest_magnitude"],
            distance=c["distance"],
        )
        for c in data["candidates"]
    ]
    return UploadDiagnosisResult(
        dataset_id=data["dataset_id"],
        generated_at=data["generated_at"],
        performance_vector=PerformanceVector(**data["performance_vector"]),
        quality_score=data["quality_score"],
        candidates=candidates,
        caveat=data["caveat"],
    )


@router.post("/upload", response_model=UploadedDatasetInfo)
async def upload_dataset(file: UploadFile) -> UploadedDatasetInfo:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "zip 파일만 업로드할 수 있습니다.")

    dataset_id = uuid.uuid4().hex[:12]
    dataset_dir = UPLOADS_DIR / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)

    zip_path = dataset_dir / "upload.zip"
    size = 0
    try:
        with zip_path.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "업로드 용량은 200MB를 넘을 수 없습니다.")
                f.write(chunk)

        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(dataset_dir)
        except zipfile.BadZipFile:
            raise HTTPException(400, "손상된 zip 파일입니다.")
        zip_path.unlink(missing_ok=True)

        n_images, n_labels = _validate_dataset_dir(dataset_dir)
    except HTTPException:
        shutil.rmtree(dataset_dir, ignore_errors=True)
        raise

    return UploadedDatasetInfo(
        dataset_id=dataset_id,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        num_images=n_images,
        num_labels=n_labels,
    )


@router.post("/{dataset_id}/diagnose", response_model=UploadDiagnosisResult)
def diagnose_dataset(dataset_id: str) -> UploadDiagnosisResult:
    dataset_dir = UPLOADS_DIR / dataset_id
    if not dataset_dir.is_dir():
        raise HTTPException(404, "데이터셋을 찾을 수 없습니다. 먼저 업로드하세요.")

    if not EXPERIMENT_PYTHON.exists():
        raise HTTPException(
            500,
            f"{EXPERIMENT_PYTHON} 없음 — experiment/venv가 이 서버 환경에 없습니다 "
            "(진단은 GPU가 있는 로컬 환경에서만 가능).",
        )

    script = EXPERIMENT_ROOT / "diagnose_upload.py"
    try:
        proc = subprocess.run(
            [str(EXPERIMENT_PYTHON), str(script), dataset_id],
            capture_output=True,
            text=True,
            timeout=DIAGNOSE_TIMEOUT_SEC,
            cwd=str(EXPERIMENT_ROOT),
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"진단이 {DIAGNOSE_TIMEOUT_SEC}초 안에 끝나지 않았습니다.")

    if proc.returncode != 0:
        raise HTTPException(500, f"진단 실패: {proc.stderr[-2000:]}")

    return _load_diagnosis_json(dataset_id)


@router.get("/{dataset_id}/diagnosis", response_model=UploadDiagnosisResult)
def get_dataset_diagnosis(dataset_id: str) -> UploadDiagnosisResult:
    return _load_diagnosis_json(dataset_id)
