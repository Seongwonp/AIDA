"""고객 데이터셋 업로드 → 진단 API (docs/21 C).

업로드된 zip은 UPLOADS_DIR/<dataset_id>/에 풀리고, 실제 추론(ultralytics/
torch 의존)은 backend가 아니라 experiment/venv 쪽에서 서브프로세스로
돌린다 — report.py가 experiment/의 결과 CSV만 읽고 무거운 ML 의존성을
backend에 얹지 않는 것과 같은 구조다.
"""
import html
import json
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

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


def _dataset_counts(dataset_dir: Path) -> tuple[int, int]:
    images_dir = dataset_dir / "images"
    labels_dir = dataset_dir / "labels"
    n_images = sum(1 for p in images_dir.iterdir() if p.is_file()) if images_dir.is_dir() else 0
    n_labels = sum(1 for _ in labels_dir.glob("*.txt")) if labels_dir.is_dir() else 0
    return n_images, n_labels


def _render_report_html(result: UploadDiagnosisResult, n_images: int, n_labels: int) -> str:
    esc = html.escape
    generated = result.generated_at.replace("T", " ").split(".")[0] + " UTC"
    v = result.performance_vector

    candidate_rows = "\n".join(
        f"""<tr>
              <td>{i + 1}</td>
              <td>{esc(c.label)}</td>
              <td>{esc(c.closest_condition)} ({c.closest_magnitude:+g})</td>
              <td>{c.distance:.4f}</td>
            </tr>"""
        for i, c in enumerate(result.candidates)
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>AIDA 데이터 품질검증 리포트 — {esc(result.dataset_id)}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Malgun Gothic", sans-serif;
          max-width: 720px; margin: 48px auto; padding: 0 24px; color: #111;
          line-height: 1.6; }}
  h1 {{ font-size: 22px; border-bottom: 2px solid #111; padding-bottom: 12px; }}
  h2 {{ font-size: 16px; margin-top: 36px; }}
  .meta {{ color: #666; font-size: 13px; margin-bottom: 24px; }}
  .score {{ font-size: 48px; font-weight: 700; }}
  .score-max {{ font-size: 18px; color: #666; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 12px; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #ddd; }}
  th {{ color: #666; font-weight: 600; font-size: 12px; }}
  .caveat {{ background: #fafafa; border: 1px solid #ddd; padding: 16px;
             font-size: 13px; color: #444; margin-top: 32px; }}
  .footer {{ margin-top: 40px; font-size: 12px; color: #999; }}
</style>
</head>
<body>
  <h1>AIDA 데이터 품질검증 리포트</h1>
  <p class="meta">
    데이터셋 ID: {esc(result.dataset_id)} · 이미지 {n_images:,}장 · 라벨 {n_labels:,}개
    · 생성 시각: {esc(generated)}
  </p>

  <div class="score">{result.quality_score}<span class="score-max">/100</span></div>
  <p class="meta">Precision × Recall 기반 추정 품질 점수</p>

  <h2>실측 성능 지표</h2>
  <table>
    <tr><th>mAP@0.5</th><th>mAP@0.5:0.95</th><th>Precision</th><th>Recall</th></tr>
    <tr>
      <td>{v.map50:.3f}</td><td>{v.map50_95:.3f}</td>
      <td>{v.precision:.3f}</td><td>{v.recall:.3f}</td>
    </tr>
  </table>

  <h2>의심 오류 유형 (재검수 우선순위)</h2>
  <table>
    <tr><th>순위</th><th>오류 유형</th><th>가장 가까운 기준 조건</th><th>거리(가까울수록 유력)</th></tr>
    {candidate_rows}
  </table>

  <div class="caveat">{esc(result.caveat)}</div>

  <p class="footer">
    AIDA — 국방과학연구소 특허(10-2664201) 기반 오류 조건별 성능 패턴 DB와
    비교한 확률적 진단 결과입니다. 완벽한 자동 판정이 아니라, 더 빠르고
    근거 있는 재검수 의사결정을 돕는 것이 목적입니다.
  </p>
</body>
</html>
"""


@router.get("/{dataset_id}/report")
def get_dataset_report(dataset_id: str) -> HTMLResponse:
    dataset_dir = UPLOADS_DIR / dataset_id
    if not dataset_dir.is_dir():
        raise HTTPException(404, "데이터셋을 찾을 수 없습니다.")

    result = _load_diagnosis_json(dataset_id)
    n_images, n_labels = _dataset_counts(dataset_dir)
    html_content = _render_report_html(result, n_images, n_labels)

    return HTMLResponse(
        content=html_content,
        headers={"Content-Disposition": f'attachment; filename="aida_report_{dataset_id}.html"'},
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
