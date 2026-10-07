"""자료 출처(provenance) 관문 — 분석 입력과 외부 전송 입력을 가른다.

두 가지를 막는다.

1. **분석 입력.** 등록부(`experiment/planning_evidence/dataset_provenance_registry.json`)에 연습(practice)이나
   출처 손상(damaged)으로 적힌 데이터셋·평가, 그리고 출처 표시가 `synthetic_dryrun`인 산출물(합성 비용 드라이런)은
   공식 분석(`analyze_qa.py`)·AI 일치도의 입력이 될 수 없다.
2. **외부 전송 입력.** 제3자 API로 보낼 그림은 합성 드라이런 생성기(`experiment/make_synthetic_ai_dryrun.py`)가
   만든 것만 받는다. nuImages 경로·파일 이름 모양·업로드된 nuImages 데이터셋 원본 그림의 SHA-256 거부 목록에
   걸리면 거부한다. nuImages 이미지의 외부 전송은 라이선스·외부 전송 허가를 따로 확인하기 전까지 막혀 있다
   (사전 등록 5-4절, 2026-10-07 사용자 결정).

네트워크를 쓰지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .schema import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "experiment" / "planning_evidence" / "dataset_provenance_registry.json"

SYNTHETIC_DRYRUN = "synthetic_dryrun"
# 분석 입력이 될 수 없는 출처 표시
NON_EVIDENCE_PROVENANCE = frozenset({SYNTHETIC_DRYRUN})
# 외부 전송을 허용하는 출처 표시 — 지금은 합성뿐이다
EXTERNAL_TRANSFER_ALLOWED = frozenset({SYNTHETIC_DRYRUN})
SYNTHETIC_GENERATOR = "experiment/make_synthetic_ai_dryrun.py"
PROVENANCE_FILE = "provenance.json"

# 경로(소문자, 슬래시 통일)에 들어 있으면 nuImages 자료로 본다
NUIMAGES_PATH_MARKERS = ("nuimages", "aida-eval", "v1.0-", "backend/app/data/uploads")
# nuImages 파일 이름 모양: n005-2018-07-10-16-39-03+0800__CAM_BACK__1531211947687642.jpg
NUIMAGES_FILENAME_RE = re.compile(r"n\d{3}-\d{4}-\d{2}-\d{2}-.*__cam_", re.IGNORECASE)
# 업로드된 nuImages 데이터셋(연습 train fit_check) — 원본 그림의 SHA-256을 거부 목록으로 쓴다
DEFAULT_DENY_IMAGE_DIRS = (REPO_ROOT / "backend" / "app" / "data" / "uploads" / "006e49d2cbc9" / "images",)
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


class ProvenanceError(ValidationError):
    """출처 규칙에 걸린다 — 분석하지 않거나 보내지 않는다."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 1. 분석 입력 ─────────────────────────────────────────────────────────────

def load_registry(path: Path | None = None) -> dict:
    p = Path(path) if path is not None else REGISTRY_PATH
    if not p.is_file():
        raise ProvenanceError(f"출처 등록부가 없다 — 분석 입력을 확인할 수 없다: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data.get("entries"), list):
        raise ProvenanceError("출처 등록부에 entries 목록이 없다")
    return data


def registry_matches(obj: dict, registry: dict) -> list[dict]:
    """obj의 dataset_id·evaluation_id에 걸리는 등록부 항목.

    항목에 dataset_id가 있으면 그 데이터셋의 **모든** 평가가 걸린다(연습 데이터셋은 통째로 공식 입력이 아니다).
    dataset_id 없이 evaluation_id만 있는 항목은 evaluation_id로 건다.
    """
    ds, ev = obj.get("dataset_id"), obj.get("evaluation_id")
    hits = []
    for entry in registry["entries"]:
        e_ds, e_ev = entry.get("dataset_id"), entry.get("evaluation_id")
        if e_ds is not None and ds is not None and str(e_ds) == str(ds):
            hits.append(entry)
        elif e_ds is None and e_ev is not None and ev is not None and str(e_ev) == str(ev):
            hits.append(entry)
    return hits


def assert_official_input(obj: Any, what: str = "분석 입력", registry: dict | None = None) -> None:
    """공식 분석·일치도 입력이 될 수 있는지. 안 되면 `ProvenanceError`."""
    if not isinstance(obj, dict):
        raise ProvenanceError(f"{what}이 JSON 객체가 아니다")
    prov = obj.get("provenance")
    if prov in NON_EVIDENCE_PROVENANCE:
        raise ProvenanceError(f"{what}의 출처가 '{prov}'다 — 비용·API 계약 점검용 합성 자료라 분석에 쓰지 않는다")
    reg = registry if registry is not None else load_registry()
    for entry in registry_matches(obj, reg):
        role, state = entry.get("role"), entry.get("provenance")
        if role == "practice" or state == "damaged":
            raise ProvenanceError(
                f"{what}의 dataset_id={obj.get('dataset_id')!r}·evaluation_id={obj.get('evaluation_id')!r}는 "
                f"출처 등록부에 role={role}, provenance={state}로 적혀 있다 — 허용 용도 "
                f"{entry.get('allowed_uses')}뿐이고 공식 평가 입력이 아니다")


# ── 2. 외부 전송 입력 ────────────────────────────────────────────────────────

def nuimages_path_hits(path: Path | str) -> list[str]:
    text = str(path).replace("\\", "/").lower()
    hits = [m for m in NUIMAGES_PATH_MARKERS if m in text]
    if NUIMAGES_FILENAME_RE.search(Path(text).name):
        hits.append("nuimages_filename")
    return hits


def build_image_deny_list(dirs: Iterable[Path] | None = None) -> dict:
    """업로드된 nuImages 데이터셋 원본 그림의 SHA-256 목록. 없는 폴더는 건너뛰고 그 사실을 남긴다."""
    shas: set[str] = set()
    sources = []
    for d in (DEFAULT_DENY_IMAGE_DIRS if dirs is None else dirs):
        d = Path(d)
        if not d.is_dir():
            sources.append({"dir": str(d), "present": False, "images": 0})
            continue
        n = 0
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
                shas.add(sha256_file(p))
                n += 1
        sources.append({"dir": str(d), "present": True, "images": n})
    return {"sha256": shas, "sources": sources}


def check_synthetic_inputs(images_root: Path, files: Iterable[str],
                           deny: dict | None = None) -> dict:
    """외부로 보낼 그림이 합성 드라이런 생성기의 산출물인지. 아니면 `ProvenanceError`.

    * `images_root`·각 파일 경로에 nuImages 표시가 없어야 한다.
    * `images_root/provenance.json`이 있고 `provenance == synthetic_dryrun`, 생성기가 저장소의 합성 생성기여야 한다.
    * 각 파일이 있고, 바이트 SHA-256이 provenance.json에 적힌 값과 같고, 거부 목록에 없어야 한다.
    """
    root = Path(images_root)
    hits = nuimages_path_hits(root.resolve())
    if hits:
        raise ProvenanceError(f"그림 폴더 경로가 nuImages 자료로 보인다({hits}) — 외부로 보내지 않는다: {root}")
    marker = root / PROVENANCE_FILE
    if not marker.is_file():
        raise ProvenanceError(f"합성 표시({PROVENANCE_FILE})가 없다 — 합성 드라이런 생성기의 산출물만 보낸다: {root}")
    meta = json.loads(marker.read_text(encoding="utf-8"))
    if meta.get("provenance") not in EXTERNAL_TRANSFER_ALLOWED:
        raise ProvenanceError(f"출처 표시가 {meta.get('provenance')!r}다 — 외부 전송은 {sorted(EXTERNAL_TRANSFER_ALLOWED)}만")
    if meta.get("generator") != SYNTHETIC_GENERATOR:
        raise ProvenanceError(f"생성기가 {meta.get('generator')!r}다 — {SYNTHETIC_GENERATOR}의 산출물만 보낸다")
    listed = meta.get("files") or {}
    deny = deny if deny is not None else build_image_deny_list()
    out = {}
    for name in files:
        path = root / name
        h = nuimages_path_hits(name)
        if h:
            raise ProvenanceError(f"파일 이름이 nuImages 자료로 보인다({h}): {name}")
        if not path.is_file():
            raise ProvenanceError(f"보낼 그림이 없다: {name}")
        sha = sha256_file(path)
        if listed.get(name) != sha:
            raise ProvenanceError(f"그림 SHA-256이 합성 표시에 적힌 값과 다르다(바뀌었거나 섞였다): {name}")
        if sha in deny["sha256"]:
            raise ProvenanceError(f"그림이 업로드된 nuImages 데이터셋의 그림과 같다(거부 목록): {name}")
        out[name] = sha
    return {"provenance": meta["provenance"], "generator": meta["generator"],
            "generator_sha256": meta.get("generator_sha256"), "seed": meta.get("seed"),
            "image_sha256": out,
            "deny_list_sources": deny.get("sources", []),
            "deny_list_size": len(deny["sha256"])}
