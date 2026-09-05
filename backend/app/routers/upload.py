"""고객 데이터셋 업로드 → 진단 API (docs/21 C).

업로드된 zip은 UPLOADS_DIR/<dataset_id>/에 풀리고, 실제 추론(ultralytics/
torch 의존)은 backend가 아니라 experiment/venv 쪽에서 서브프로세스로
돌린다 — report.py가 experiment/의 결과 CSV만 읽고 무거운 ML 의존성을
backend에 얹지 않는 것과 같은 구조다.
"""
import html
import json
import os
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from app.config import EXPERIMENT_PYTHON, EXPERIMENT_ROOT, UPLOADS_DIR
from app.models import (
    DatasetHistoryItem,
    ErrorTypeCandidate,
    LabelDiagnosisResult,
    PerformanceVector,
    ReliabilityProfileInfo,
    RulerFit,
    RulerInfo,
    TypeRobustness as ReliabilityRow,
    ReviewQueueItem,
    SuspicionTypeCount,
    UploadDiagnosisResult,
    UploadedDatasetInfo,
)
from app.routers.report import TYPE_LABELS

router = APIRouter(prefix="/api/datasets", tags=["upload"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB

# **압축 후 크기만으로는 부족하다.** 0으로 채운 zip은 1000배 넘게 부푼다
# (실측 0.97MB → 0.98GB). 이 한도를 안 두면 200MB 업로드로 디스크를 수백 GB
# 채울 수 있다. 이미지는 원래 잘 안 눌리므로 200MB zip이 정상적으로 풀리면
# 200~400MB다 — 2GB면 넉넉하다.
MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024   # 2GB
# 작은 파일 수십만 개로도 같은 짓을 할 수 있다. KITTI 전체가 이미지+라벨
# 15,000개 정도다.
MAX_ZIP_ENTRIES = 100_000

DIAGNOSE_TIMEOUT_SEC = 300

# 프로파일 파일 이름 → 사람이 읽을 이름. 없으면 파일 이름을 그대로 쓴다.
PROFILE_LABELS = {"mc": "다중 클래스 (Car/Van/Pedestrian/Cyclist 실측)"}

# 박스 단위 의심 유형 한글 라벨. report.py의 TYPE_LABELS(조건 type 기준)와
# 겹치는 이름이 많지만, 여기엔 missing/duplicate가 "라벨이 빠졌다/겹쳤다"는
# 박스 단위 의미로 들어가므로 별도로 둔다.
SUSPICION_LABELS = {
    "width": "가로 길이 어긋남",
    "height": "세로 길이 어긋남",
    "scale": "전체 크기 어긋남",
    "translation_x": "중심점 가로 이동",
    "translation_y": "중심점 세로 이동",
    "missing": "라벨 누락 의심",
    "duplicate": "라벨 중복 의심",
    # 다중 클래스에서만 나온다. 빠뜨리면 화면에 class_mismatch가 그대로 뜬다
    # — report.py의 TYPE_LABELS, 프론트의 사본 두 개와 같이 맞춰야 한다.
    "class_mismatch": "클래스 오기입 의심",
}


# 유형별 도메인 강건성 — docs/21 Y의 실측치.
# 같은 데이터를 자기 도메인 자와 다른 도메인 자로 각각 진단해 얻었다.
#
# 왜 유형마다 다른가: 진단은 기준 모델의 예측을 자로 삼는데, 판정에 따라
# 그 자를 쓰는 방식이 다르다. 기하 오류는 예측 박스를 정밀한 자로 쓰므로
# 자가 흔들리면 잰 값이 무의미해진다. 중복은 "이 두 라벨이 같은 것을
# 가리킨다"는 판정이라 예측을 위치만 아는 닻으로 쓴다 — 박스가 정확할
# 필요도, 클래스가 맞을 필요도 없어서 도메인이 어긋나도 버틴다.
DOMAIN_ROBUSTNESS = {
    # suspicion: (도메인 맞을 때, 어긋났을 때)
    "duplicate": (0.631, 0.665),
    "class_mismatch": (0.991, 0.620),
    "missing": (0.839, 0.439),
    "scale": (0.777, 0.624),
    "translation_y": (0.798, 0.647),
    "height": (0.658, 0.504),
    "width": (0.422, 0.291),
    "translation_x": (0.404, 0.402),
}
# 어긋난 도메인에서 이 정밀도를 넘으면 "그래도 볼 만하다"로 본다. 중복(66.5%)은
# 넘고 나머지는 못 넘는다 — 경계가 아니라 실제로 갈리는 지점이다.
ROBUST_THRESHOLD = 0.65

# 위 DOMAIN_ROBUSTNESS는 **같은 KITTI 안에서 프레임 구성만 바꿔** 잰 값이라
# 낙관적이다. 진짜 다른 데이터셋(COCO)으로 재보니 훨씬 심했다(docs/21 AI,
# 상위 10% 기준):
#
#   누락      94.9% → 76.7%  (81% 유지 — 유일하게 확실히 살아남는다)
#   중복      82.6% → 40.8%  (절반. KITTI 안에서는 견뎠는데 여기선 아니다)
#   기하 오류 74~90% → 7~29% (전멸)
#
# 그래서 화면에는 이 값도 같이 말해야 한다. "기준 모델에 의존" 정도로는
# 고객이 위험을 못 읽는다.
CROSS_DATASET_ROBUSTNESS = {
    "missing": 0.767,
    "duplicate": 0.408,
    "width": 0.294,
    "height": 0.202,
    "scale": 0.099,
    "translation_x": 0.090,
    "translation_y": 0.075,
}


def _robustness(by_type: list) -> list[ReliabilityRow]:
    """이 데이터셋에서 실제로 나온 유형에 대해서만 강건성을 붙인다."""
    rows = []
    for entry in by_type:
        t = entry["suspicion"]
        if t not in DOMAIN_ROBUSTNESS:
            continue
        matched, shifted = DOMAIN_ROBUSTNESS[t]
        rows.append(ReliabilityRow(
            suspicion=t,
            label=SUSPICION_LABELS.get(t, t),
            matched_domain=matched,
            shifted_domain=shifted,
            robust=shifted >= ROBUST_THRESHOLD,
            cross_dataset=CROSS_DATASET_ROBUSTNESS.get(t),
        ))
    return rows


# 맥이 zip에 끼워 넣는 메타데이터. 이게 있으면 "최상위 폴더가 하나"가
# 아니게 되어 한 겹 벗기기가 안 먹는다.
_ZIP_NOISE = {"__MACOSX", ".DS_Store", "Thumbs.db"}


def _check_zip_is_safe(zf: zipfile.ZipFile, dest: Path) -> None:
    """풀기 전에 목록만 보고 거절할 것을 거절한다.

    목록(`infolist`)은 압축을 풀지 않고 읽히므로, 폭탄을 디스크에 쏟기 전에
    막을 수 있다. 보는 것은 셋이다.

    **압축률.** 업로드 바이트만 재고 있었는데 그것으로는 부족하다. 0으로 채운
    1MB짜리 zip이 풀면 1GB가 된다(실측 1028배). 200MB 한도를 지키면서 디스크를
    수백 GB 채울 수 있다.

    **개수.** 작은 파일 수십만 개로도 같은 짓을 할 수 있다.

    **경로.** CPython의 `extractall`은 "../"와 절대경로를 실제로 제거하므로
    지금도 밖으로 나가지는 않는다(확인함). 그래도 여기서 한 번 더 보는 이유는,
    그 보장이 표준 라이브러리 구현에 딸린 것이라 코드만 읽어서는 안 보이고
    검사로 고정해두지 않으면 다음 사람이 알 수 없기 때문이다.
    """
    entries = zf.infolist()
    if len(entries) > MAX_ZIP_ENTRIES:
        raise HTTPException(
            400, f"zip 안 파일이 너무 많습니다 ({len(entries):,}개). "
                 f"{MAX_ZIP_ENTRIES:,}개까지만 받습니다.")

    total = 0
    for info in entries:
        total += info.file_size
        if total > MAX_EXTRACTED_BYTES:
            gb = MAX_EXTRACTED_BYTES / 1024 / 1024 / 1024
            raise HTTPException(
                413, f"압축을 풀면 {gb:.0f}GB를 넘습니다. 압축률이 비정상적으로 "
                     f"높거나 데이터셋이 너무 큽니다.")

        # 목록에 적힌 이름 그대로가 dest 안에 떨어지는지 본다
        name = info.filename
        if name.endswith("/"):
            continue                       # 폴더 항목
        landed = (dest / name).resolve()
        if not landed.is_relative_to(dest.resolve()):
            raise HTTPException(400, f"허용되지 않은 경로가 들어 있습니다: {name}")


def _unwrap_single_dir(dataset_dir: Path) -> None:
    """폴더째 압축한 zip의 한 겹을 벗긴다.

    윈도우·맥 둘 다 폴더를 우클릭해 압축하면 안이 mydata/images/... 로 한 겹
    싸인다. 가장 흔한 방식인데 그대로 두면 "images/ 폴더가 없다"고 거절하게
    된다 — 사용자 눈에는 분명히 있는데 없다고 하는 셈이다.

    경로를 다르게 돌려주지 않고 파일을 실제로 옮긴다. 이 뒤로
    dataset_dir/images 를 그대로 쓰는 곳이 여럿이라 한 군데서 끝내는 게 낫다.
    """
    if (dataset_dir / "images").is_dir():
        return                       # 이미 제대로 된 모양이면 건드리지 않는다

    entries = [e for e in dataset_dir.iterdir() if e.name not in _ZIP_NOISE]
    if len(entries) != 1 or not entries[0].is_dir():
        return                       # 한 겹이 아니면 벗길 게 없다

    inner = entries[0]
    if not (inner / "images").is_dir():
        return                       # 안에도 images/가 없으면 어차피 다른 문제다

    # 잡동사니를 먼저 치운다. 안 치우면 inner 안에도 같은 이름이 있을 때
    # 올리다가 부딪힌다.
    for junk in dataset_dir.iterdir():
        if junk == inner:
            continue                 # 위에서 걸러 이것 말고는 전부 잡동사니다
        if junk.is_dir():
            shutil.rmtree(junk, ignore_errors=True)
        else:
            junk.unlink()

    # inner의 자식을 한 겹 위로 올린다. 옆에 임시 폴더를 만들지 않는 이유는
    # 중간에 실패하면 그게 UPLOADS_DIR에 남아 진단 이력 목록에 끼기 때문이다.
    for child in list(inner.iterdir()):
        child.rename(dataset_dir / child.name)
    inner.rmdir()


def _validate_dataset_dir(dataset_dir: Path) -> tuple[int, int]:
    _unwrap_single_dir(dataset_dir)

    images_dir = dataset_dir / "images"
    labels_dir = dataset_dir / "labels"
    if not images_dir.is_dir() or not labels_dir.is_dir():
        raise HTTPException(
            400,
            "zip 안에 images/ 와 labels/ 폴더가 있어야 합니다 "
            "(YOLO 포맷: images/xxx.jpg + labels/xxx.txt). "
            "폴더째 압축한 zip은 한 겹 벗겨서 읽으니 그대로 올리셔도 됩니다.",
        )
    n_images = sum(1 for p in images_dir.iterdir() if p.is_file())
    n_labels = sum(1 for _ in labels_dir.glob("*.txt"))
    if n_images == 0:
        raise HTTPException(400, "images/ 폴더가 비어 있습니다.")
    if n_labels == 0:
        # 라벨이 한 장도 없으면 진단할 게 없다. 대개 확장자가 .txt가 아니거나
        # (.json·.xml) 라벨을 다른 폴더에 둔 경우다.
        raise HTTPException(
            400,
            "labels/ 폴더에 .txt 라벨이 없습니다. YOLO 포맷(한 줄에 "
            "class cx cy w h, 0~1로 정규화)의 .txt 파일이어야 합니다.",
        )
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
                _check_zip_is_safe(zf, dataset_dir)
                zf.extractall(dataset_dir)
        except zipfile.BadZipFile:
            raise HTTPException(400, "손상된 zip 파일입니다.")
        zip_path.unlink(missing_ok=True)

        n_images, n_labels = _validate_dataset_dir(dataset_dir)
    except HTTPException:
        shutil.rmtree(dataset_dir, ignore_errors=True)
        raise

    class_ids = _label_class_ids(dataset_dir)
    suggested, reason = _suggest_profile(class_ids)
    return UploadedDatasetInfo(
        dataset_id=dataset_id,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        num_images=n_images,
        num_labels=n_labels,
        label_class_ids=sorted(class_ids),
        suggested_profile=suggested,
        suggestion_reason=reason,
    )


def _profile_env(profile: str | None) -> dict[str, str]:
    """진단 서브프로세스에 넘길 신뢰도 프로파일 환경변수.

    유형 신뢰도 상수는 도메인을 탄다 — 다중 클래스로 검증해보니 "부재 시"
    값이 크게 흔들렸다(누락 88% → 22%, docs/21 L). 그래서 데이터셋마다
    보정 프로파일을 골라 쓸 수 있게 한다. 안 고르면 기본값(KITTI Car 실측).
    """
    if not profile:
        return {}
    path = _resolve_profile(profile)
    classes_for_check = _profile_classes(path)
    dataset = _profile_dataset(path)
    if not _weights_exist(classes_for_check, dataset):
        raise HTTPException(
            400,
            f"'{profile}' 프로파일의 기준 모델이 이 환경에 없습니다 "
            f"(클래스: {', '.join(classes_for_check) or 'Car'}). "
            "해당 구성으로 clean 조건을 먼저 학습하세요.",
        )
    env = {"AIDA_RELIABILITY_PROFILE": str(path)}
    # 상수만 갈아끼우면 반쪽이다 — 그 상수는 특정 클래스 구성에서 잰 값이므로
    # 진단도 같은 구성(같은 기준 모델·같은 클래스 인덱스)으로 돌려야 한다.
    classes = _profile_classes(path)
    if classes:
        env["AIDA_CLASSES"] = ",".join(classes)
    if dataset and dataset != "kitti":
        # 상수만 갈아끼우고 데이터셋을 안 넘기면 진단이 KITTI 자를 연다.
        env["AIDA_DATASET"] = dataset
    return env


def _profile_classes(path: Path) -> list[str]:
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("classes", []))
    except (OSError, json.JSONDecodeError):
        return []


def _resolve_profile(name: str) -> Path:
    """프로파일 이름을 파일 경로로 바꾼다.

    이름만 받고 경로는 서버가 정한다 — 사용자가 준 문자열을 그대로 경로로
    쓰면 임의 파일을 읽히는 통로가 된다.
    """
    if name not in _available_profiles():
        raise HTTPException(400, f"알 수 없는 신뢰도 프로파일: {name}")
    return EXPERIMENT_ROOT / f"reliability_profile_{name}.json"


def _available_profiles() -> list[str]:
    """experiment/reliability_profile_<이름>.json 에서 이름만 뽑는다."""
    if not EXPERIMENT_ROOT.is_dir():
        return []
    return sorted(
        p.stem[len("reliability_profile_"):]
        for p in EXPERIMENT_ROOT.glob("reliability_profile_*.json")
    )


# 학습 시드만 바꿔 같은 자를 일곱 번 만들었을 때 상위 10% 정밀도의 표준편차
# (%p, docs/21 AG, 조건 29개 = clean 제외). 평균만 보면 안 보이는 값이다.
#
# **안정성을 정하는 건 클래스 폭이 아니라 데이터와의 궁합이다.** 4클래스
# 자끼리도 자기 도메인 자는 ±2.20인데 도메인이 어긋난 자는 ±5.45로 2.5배
# 차이가 난다. AF에서는 "좁은 자가 안 흔들린다"고 봤는데, 자 4종을 다 재보니
# 가장 안정적인 게 4클래스 자기 도메인 자였다.
#
# 여기 값은 **고객 도메인을 모르는 상황**을 가정한다 — 제품이 실제로 놓인
# 처지다. 그래서 클래스 수로 키를 잡되, 각각 그 처지에 해당하는 자의
# 실측치를 쓴다: 1클래스는 먼 이동 자(±2.59), 4클래스는 약한 이동 자(±5.45).
# 자가 고객 데이터에 잘 맞는다면 실제로는 이보다 작을 것이다.
RULER_SEED_SPREAD_PP = {1: 2.59, 4: 5.45}
DEFAULT_SEED_SPREAD_PP = 5.45


def _ruler_weights(classes: list[str], dataset: str = "kitti") -> Path:
    """이 구성에서 자로 쓸 가중치 경로.

    config.py의 접미사 규칙을 그대로 따라야 진단 서브프로세스가 실제로 여는
    파일과 일치한다. 순서도 같아야 한다 — 클래스(_mc)가 먼저, 데이터셋이
    그다음이다.

    **데이터셋을 빼먹으면 조용히 틀린다.** COCO 프로파일은 클래스가 ["Car"]
    하나라, 클래스만 보면 KITTI 자(runs/)를 가리킨다. 엉뚱한 자로 진단해도
    오류가 안 나고, 화면에는 "COCO 프로파일"이라 찍힌다. AI에서 그 조합의
    상위 10%가 26.0%까지 무너지는 걸 쟀다.
    """
    suffix = "" if classes in ([], ["Car"]) else "_mc"
    if dataset and dataset != "kitti":
        suffix += f"_{dataset}"
    return EXPERIMENT_ROOT / f"runs{suffix}" / "clean" / "weights" / "best.pt"


def _weights_exist(classes: list[str], dataset: str = "kitti") -> bool:
    """이 구성의 기준 모델이 이 환경에 있는가.

    없는 프로파일을 고르면 진단이 서브프로세스 오류로 실패하는데, 고르기
    전에 알려주는 편이 낫다.
    """
    return _ruler_weights(classes, dataset).exists()


def _profile_dataset(path: Path) -> str:
    """프로파일이 어느 데이터셋에서 잰 것인지. 안 적혀 있으면 kitti."""
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("dataset", "kitti")
    except (OSError, json.JSONDecodeError):
        return "kitti"


def _label_class_ids(dataset_dir: Path, cap: int = 2000) -> set[int]:
    """업로드된 라벨에 실제로 등장하는 클래스 인덱스.

    자가 아는 클래스보다 데이터에 많은 클래스가 있으면, 그 자는 나머지를
    아예 못 본다 — 오탐이 아니라 침묵이라 화면에 아무 흔적도 안 남는다.
    그래서 고르기 전에 알려줘야 한다. 파일을 전부 열 필요는 없으므로
    앞에서 cap장만 본다.
    """
    ids: set[int] = set()
    labels_dir = dataset_dir / "labels"
    if not labels_dir.is_dir():
        return ids
    for i, path in enumerate(sorted(labels_dir.rglob("*.txt"))):
        if i >= cap:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            parts = line.split()
            if parts:
                try:
                    ids.add(int(float(parts[0])))
                except ValueError:
                    pass
    return ids


def _suggest_profile(class_ids: set[int]) -> tuple[str | None, str]:
    """이 데이터에 맞는 기준 모델을 고른다.

    AA와 AD의 결론은 "대상 분포에서의 실력이 전부"인데, 서버가 고객 분포를
    미리 알 수는 없다. 다만 **자가 아예 모르는 클래스가 있는지**는 라벨만
    보고도 안다. 그건 품질 문제가 아니라 구멍이다 — 그 클래스는 검사 자체가
    안 되고 화면에 아무 흔적도 안 남는다.

    그래서 추천은 여기까지만 한다: 데이터의 클래스를 덮는 자 중 가장 좁은
    것. Z·AA가 "실력이 비슷하면 좁은 쪽이 낫다"고 했으므로, 덮기만 하면
    넓힐 이유가 없다.
    """
    if not class_ids:
        return None, ""
    needed = max(class_ids) + 1

    candidates: list[tuple[int, str | None, list[str]]] = []
    default_classes = ["Car"]
    if _weights_exist(default_classes):
        candidates.append((len(default_classes), None, default_classes))
    for name in _available_profiles():
        classes = _profile_classes(EXPERIMENT_ROOT / f"reliability_profile_{name}.json")
        if classes and _weights_exist(classes):
            candidates.append((len(classes), name, classes))

    if not candidates:
        # 자가 한 대도 없다. "최대 0개까지만 압니다"로 빠지면 클래스를 줄이면
        # 될 것처럼 읽히는데, 실제로는 무엇을 해도 안 된다.
        return None, ("이 서버에 학습된 기준 모델이 없습니다. "
                      "clean 조건을 먼저 학습해야 진단할 수 있습니다.")

    covering = sorted(c for c in candidates if c[0] >= needed)
    if not covering:
        widest = max(c[0] for c in candidates)
        return None, (f"라벨에 클래스 인덱스 {sorted(class_ids)}가 있는데, "
                      f"이 서버의 기준 모델은 최대 {widest}개까지만 압니다. "
                      f"모르는 클래스는 검사되지 않습니다.")
    n_classes, name, classes = covering[0]
    if name is None:
        return None, ""                    # 기본값으로 충분하다
    return name, (f"라벨에 클래스 인덱스 {sorted(class_ids)}가 있어 "
                  f"{n_classes}개 클래스를 아는 기준 모델이 필요합니다 "
                  f"({', '.join(classes)}).")


def _ruler_info(profile: str | None, dataset_dir: Path) -> RulerInfo:
    """이 진단이 어느 자를 쓰는지. 진단 시점에 확정해 사이드카로 남긴다."""
    name = profile or ""
    path = _resolve_profile(name) if name else None
    classes = (_profile_classes(path) if path else ["Car"]) or ["Car"]
    dataset = _profile_dataset(path) if path else "kitti"
    unknown = sorted(i for i in _label_class_ids(dataset_dir) if i >= len(classes))
    return RulerInfo(
        profile=name,
        profile_label=(PROFILE_LABELS.get(name, name) if name
                       else "기본 (KITTI Car 단일 클래스 실측)"),
        classes=classes,
        weights=_ruler_weights(classes, dataset).parent.parent.parent.name,
        # 자가 아는 클래스 수와 데이터의 클래스 수가 맞아야 클래스 대조를 한다
        # (docs/21 Z). 여기서는 자가 2개 이상 알면 대조하는 것으로 본다.
        class_aware=len(classes) > 1 and not unknown,
        seed_spread_pp=RULER_SEED_SPREAD_PP.get(len(classes), DEFAULT_SEED_SPREAD_PP),
        unknown_class_ids=unknown,
    )


@router.get("/reliability-profiles", response_model=list[ReliabilityProfileInfo])
def list_reliability_profiles() -> list[ReliabilityProfileInfo]:
    """고를 수 있는 신뢰도 프로파일 목록. 기본값(프로파일 없음)이 항상 첫 항목."""
    profiles = [ReliabilityProfileInfo(
        name="", label="기본 (KITTI Car 단일 클래스 실측)", types=[], classes=["Car"],
        available=_weights_exist(["Car"]),
    )]
    for name in _available_profiles():
        try:
            data = json.loads(
                (EXPERIMENT_ROOT / f"reliability_profile_{name}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        profiles.append(ReliabilityProfileInfo(
            name=name,
            label=PROFILE_LABELS.get(name, name),
            types=sorted(data.get("present", {})),
            classes=list(data.get("classes", [])),
            available=_weights_exist(list(data.get("classes", [])),
                                     data.get("dataset", "kitti")),
        ))
    return profiles


def _run_experiment_script(dataset_id: str, script_name: str, extra_args: list[str],
                           env_extra: dict[str, str] | None = None) -> None:
    """experiment/venv 파이썬으로 진단 스크립트를 돌린다.

    ultralytics/torch를 backend에 얹지 않으려고 서브프로세스로 분리한 구조라,
    데이터셋/라벨 단위 진단이 이 함수를 공유한다.
    """
    dataset_dir = UPLOADS_DIR / dataset_id
    if not dataset_dir.is_dir():
        raise HTTPException(404, "데이터셋을 찾을 수 없습니다. 먼저 업로드하세요.")

    if not EXPERIMENT_PYTHON.exists():
        raise HTTPException(
            500,
            f"{EXPERIMENT_PYTHON} 없음 — experiment/venv가 이 서버 환경에 없습니다 "
            "(진단은 GPU가 있는 로컬 환경에서만 가능).",
        )

    script = EXPERIMENT_ROOT / script_name
    try:
        proc = subprocess.run(
            [str(EXPERIMENT_PYTHON), str(script), *extra_args],
            capture_output=True,
            text=True,
            timeout=DIAGNOSE_TIMEOUT_SEC,
            cwd=str(EXPERIMENT_ROOT),
            env={**os.environ, **(env_extra or {})},
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"진단이 {DIAGNOSE_TIMEOUT_SEC}초 안에 끝나지 않았습니다.")

    if proc.returncode != 0:
        raise HTTPException(500, f"진단 실패: {proc.stderr[-2000:]}")


@router.post("/{dataset_id}/diagnose", response_model=UploadDiagnosisResult)
def diagnose_dataset(dataset_id: str) -> UploadDiagnosisResult:
    _run_experiment_script(dataset_id, "diagnose_upload.py", [dataset_id])
    return _load_diagnosis_json(dataset_id)


RULER_SIDECAR = "ruler.json"


def _save_ruler_sidecar(dataset_id: str, ruler: RulerInfo) -> None:
    """어느 자로 쟀는지 결과 옆에 남긴다.

    label_diagnosis.json은 실험 스크립트가 쓰는 것이라 프로파일 선택을
    모른다. 그렇다고 진단 응답에만 담으면, 나중에 GET으로 결과를 다시
    불러왔을 때 자가 사라진다 — 리포트를 나중에 여는 게 정상 사용이므로
    파일로 남겨야 한다.
    """
    (UPLOADS_DIR / dataset_id / RULER_SIDECAR).write_text(
        ruler.model_dump_json(indent=2), encoding="utf-8")


def _load_ruler_sidecar(dataset_id: str) -> RulerInfo | None:
    path = UPLOADS_DIR / dataset_id / RULER_SIDECAR
    if not path.exists():
        return None                    # 이 기능 전에 만든 결과 — 자를 모른다
    try:
        return RulerInfo.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_label_diagnosis_json(dataset_id: str) -> LabelDiagnosisResult:
    result_path = UPLOADS_DIR / dataset_id / "label_diagnosis.json"
    if not result_path.exists():
        raise HTTPException(404, "아직 라벨 단위 진단을 하지 않았습니다.")

    data = json.loads(result_path.read_text(encoding="utf-8"))
    summary = data["summary"]
    dominant = summary["dominant_type"]

    return LabelDiagnosisResult(
        dataset_id=dataset_id,
        generated_at=data["generated_at"],
        total_labels=summary["total_labels"],
        total_findings=summary["total_findings"],
        suspicion_ratio=summary["suspicion_ratio"],
        dominant_type=dominant,
        dominant_label=SUSPICION_LABELS.get(dominant, dominant) if dominant else None,
        dominant_ratio=summary["dominant_ratio"],
        systematic=summary["systematic"],
        by_type=[
            SuspicionTypeCount(
                suspicion=t["suspicion"],
                label=SUSPICION_LABELS.get(t["suspicion"], t["suspicion"]),
                count=t["count"],
                ratio=t["ratio"],
            )
            for t in summary["by_type"]
        ],
        review_queue=[
            ReviewQueueItem(
                rank=item["rank"],
                image=item["image"],
                label_index=item["label_index"],
                suspicion=item["suspicion"],
                label=SUSPICION_LABELS.get(item["suspicion"], item["suspicion"]),
                severity=item["severity"],
                detail=item["detail"],
                box=item.get("box"),
            )
            for item in data["review_queue"]
        ],
        robustness=_robustness(summary["by_type"]),
        ruler=_load_ruler_sidecar(dataset_id),
        ruler_fit=(RulerFit(**summary["ruler_fit"])
                   if summary.get("ruler_fit") else None),
        caveat=data["caveat"] + (
            " 이 수치는 기준 모델이 이 데이터와 같은 도메인일 때의 것입니다. "
            "도메인이 어긋나면 유형마다 다르게 무너지며, 아래 유형별 신뢰도를 "
            "참고하세요 (docs/21 Y 실측)."
        ),
    )


@router.post("/{dataset_id}/diagnose-labels", response_model=LabelDiagnosisResult)
def diagnose_dataset_labels(dataset_id: str, profile: str | None = None) -> LabelDiagnosisResult:
    """박스 단위 진단 — 재검수 우선순위 목록을 만든다.

    /diagnose(데이터셋 단위 성능 비교)와 달리 예측 박스와 라벨을 1:1로
    대조하므로, "어느 이미지의 어느 박스를 다시 봐야 하는지"까지 나온다.
    27개 조건 실측 기준 진단 정확도 92.6%
    (experiment/label_diagnosis_eval.json).
    """
    dataset_dir = UPLOADS_DIR / dataset_id
    if not dataset_dir.is_dir():
        raise HTTPException(404, "데이터셋을 찾을 수 없습니다.")
    # 자 정보를 먼저 확정해 남긴다 — 진단이 끝난 뒤에는 어떤 프로파일로
    # 돌렸는지 알 길이 없다.
    _save_ruler_sidecar(dataset_id, _ruler_info(profile, dataset_dir))
    _run_experiment_script(dataset_id, "diagnose_labels.py", ["--upload-id", dataset_id],
                           env_extra=_profile_env(profile))
    return _load_label_diagnosis_json(dataset_id)


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
IMAGE_MEDIA_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".bmp": "image/bmp", ".webp": "image/webp",
}


@router.get("/history", response_model=list[DatasetHistoryItem])
def list_dataset_history() -> list[DatasetHistoryItem]:
    """지난 진단 목록. 최근 것부터.

    이 파일의 "/{dataset_id}/..." 는 전부 두 조각이라 한 조각짜리 이 경로와는
    서로 가리지 않는다 — 선언 순서는 상관없다. 한 조각짜리 "/{dataset_id}" 를
    나중에 추가한다면 그때는 이 경로가 먼저 와야 한다.
    """
    if not UPLOADS_DIR.is_dir():
        return []

    rows: list[tuple[float, DatasetHistoryItem]] = []
    for d in UPLOADS_DIR.iterdir():
        if not d.is_dir():
            continue
        label_path = d / "label_diagnosis.json"
        summary: dict = {}
        when: str | None = None
        if label_path.exists():
            try:
                data = json.loads(label_path.read_text(encoding="utf-8"))
                summary = data.get("summary", {})
                when = data.get("generated_at")
            except (OSError, json.JSONDecodeError):
                pass                       # 깨진 결과는 목록에서 빼지 않고 빈칸으로 둔다

        n_images, n_labels = _dataset_counts(d)
        dominant = summary.get("dominant_type")
        rows.append((
            label_path.stat().st_mtime if label_path.exists() else d.stat().st_mtime,
            DatasetHistoryItem(
                dataset_id=d.name,
                diagnosed_at=when,
                num_images=n_images,
                num_labels=n_labels,
                has_label_diagnosis=label_path.exists(),
                total_findings=summary.get("total_findings"),
                dominant_label=(SUSPICION_LABELS.get(dominant, dominant)
                                if dominant else None),
            ),
        ))

    rows.sort(key=lambda r: r[0], reverse=True)
    return [item for _mtime, item in rows]


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str) -> Response:
    """업로드한 데이터셋과 진단 결과를 지운다.

    이력을 화면에 꺼내 놓고 보니 지우는 길이 없었다. 쌓이는 용량도 문제지만,
    **고객 데이터가 서버에 무기한 남는 게** 더 문제다 — 검수가 끝나면 지울 수
    있어야 한다.

    dataset_id는 우리가 만든 uuid지만 요청으로 오는 값이다. 지우는 동작이라
    한 번 틀리면 되돌릴 수 없으므로, 한 조각짜리 이름인지 보고 해석한 경로가
    정말 UPLOADS_DIR의 바로 아래인지 다시 확인한다.
    """
    # 우리가 만드는 id는 uuid4().hex[:12]다. 형식을 강제해 **지우는 사정거리를
    # 데이터셋으로 좁힌다** — 경로 검사만으로도 밖으로는 못 나가지만, 그러면
    # UPLOADS_DIR 바로 아래 아무 폴더나 지울 수 있다. 파괴적인 동작이라
    # "밖으로 못 나간다"보다 "이것만 지운다"가 맞는 계약이다.
    if not re.fullmatch(r"[0-9a-f]{12}", dataset_id):
        raise HTTPException(400, "데이터셋 id 형식이 아닙니다.")
    if dataset_id != Path(dataset_id).name:
        raise HTTPException(400, "허용되지 않은 경로입니다.")

    root = UPLOADS_DIR.resolve()
    target = (UPLOADS_DIR / dataset_id).resolve()
    # 심볼릭 링크로 밖을 가리킬 수 있으니 부모가 정말 UPLOADS_DIR인지 본다
    if target.parent != root:
        raise HTTPException(400, "허용되지 않은 경로입니다.")
    if not target.is_dir():
        raise HTTPException(404, "데이터셋을 찾을 수 없습니다.")

    shutil.rmtree(target)
    return Response(status_code=204)


@router.get("/{dataset_id}/images/{name}")
def get_dataset_image(dataset_id: str, name: str) -> FileResponse:
    """업로드된 이미지 한 장. 재검수 목록이 문제 박스를 그려 보여줄 때 쓴다.

    이름은 사용자가 올린 zip에서 온 값이라 그대로 경로에 붙이면 안 된다.
    Path(name).name으로 디렉터리 부분을 떼고, 해석한 경로가 정말 그 데이터셋
    폴더 안인지 한 번 더 확인한다.
    """
    images_dir = (UPLOADS_DIR / dataset_id / "images").resolve()
    if not images_dir.is_dir():
        raise HTTPException(404, "데이터셋을 찾을 수 없습니다.")

    safe = Path(name).name                      # ../ 같은 것을 떼어낸다
    suffix = Path(safe).suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        raise HTTPException(400, f"이미지 파일이 아닙니다: {safe}")

    # zip 안에서 하위 폴더에 들어 있을 수 있어 재귀로 찾는다
    matches = [p for p in images_dir.rglob(safe) if p.is_file()]
    if not matches:
        raise HTTPException(404, f"이미지가 없습니다: {safe}")

    path = matches[0].resolve()
    # 심볼릭 링크 등으로 폴더 밖을 가리킬 수 있으니 마지막으로 확인한다
    if not path.is_relative_to(images_dir):
        raise HTTPException(400, "허용되지 않은 경로입니다.")

    return FileResponse(path, media_type=IMAGE_MEDIA_TYPES.get(suffix, "image/png"))


@router.get("/{dataset_id}/label-diagnosis", response_model=LabelDiagnosisResult)
def get_label_diagnosis(dataset_id: str) -> LabelDiagnosisResult:
    return _load_label_diagnosis_json(dataset_id)


@router.get("/{dataset_id}/diagnosis", response_model=UploadDiagnosisResult)
def get_dataset_diagnosis(dataset_id: str) -> UploadDiagnosisResult:
    return _load_diagnosis_json(dataset_id)
