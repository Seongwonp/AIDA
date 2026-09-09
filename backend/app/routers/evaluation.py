"""평가용 가림 판정 (docs/evaluation-adjudication-design.md).

**제품의 재검수 판정과 섞지 않는다.** 제품 판정은 순위와 의심 유형을 보고
매기지만, 평가 판정은 그것을 가린 채 매겨야 결과가 안 휜다. 파일도 따로 쓴다 —
기존 `verdicts.json`은 읽지도 고치지도 않는다.

이 모듈이 만드는 것은 **판정을 기록할 길**이다. 판정 자체는 아직 사람이 하고,
그 사람이 지금은 개발자다. **"독립된 사람이 정답을 확정했다"가 아니다.**
"""
import hashlib
import itertools
import json
import random
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import EXPERIMENT_ROOT, UPLOADS_DIR
from ..models import (BlindCandidate, BlindQueue, EVALUATION_SCHEMA_VERSION,
                      EvaluationAdjudication, EvaluationAdjudications,
                      EvaluationCandidate, EvaluationSnapshot)

router = APIRouter(prefix="/api/datasets", tags=["evaluation"])

SNAPSHOT_FILE = "snapshot.json"
ADJUDICATIONS_FILE = "adjudications.json"
VALID_VERDICTS = {"hit", "miss", "hold"}
# 누락 객체의 이름. 판정자가 이미지 안에서 번호를 매긴다.
MISSING_ID = re.compile(r"^M\d+$")


def eval_dir(dataset_id: str, evaluation_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", dataset_id):
        raise HTTPException(400, "데이터셋 id 형식이 아닙니다.")
    if not re.fullmatch(r"[0-9a-z_-]{1,40}", evaluation_id):
        raise HTTPException(400, "평가 id 형식이 아닙니다.")
    return UPLOADS_DIR / dataset_id / "evaluations" / evaluation_id


def _write_atomic(path: Path, text: str) -> None:
    """같은 폴더 임시 파일 + 교체 (docs/25 R4와 같은 규칙).

    곧장 덮어쓰면 여는 순간 잘려 **쓰다 끊길 때 있던 판정까지 잃는다.**
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise HTTPException(500, f"저장하지 못했습니다: {exc}") from exc


def candidate_set_hash(candidates: list[EvaluationCandidate]) -> str:
    """후보 집합의 지문. 목록이 바뀌면 값이 바뀐다."""
    joined = "\n".join(sorted(c.canonical_candidate_id for c in candidates))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def canonical_id(image: str, label_index: int | None, suspicion: str,
                 occurrence: int = 0) -> str:
    """후보의 영구 이름 (docs/evaluation-adjudication-design.md).

    **결정론적이다** — 같은 이미지·같은 라벨·같은 유형이면 언제 만들어도 같은
    이름이다. 그래서 묶음을 다시 만들어도 서로 대조할 수 있다.

    세 가지를 동시에 지켜야 한다.

    1. **이미지를 담는다.** `label_index`는 이미지 안에서만 번호다. 이름에
       이미지가 없으면 `a.jpg`의 0번과 `b.jpg`의 0번이 같은 이름이 되어 한쪽에
       내린 판정이 다른 쪽에 붙는다.
    2. **의심 유형을 드러내지 않는다.** 이름은 가림 판정 화면에 그대로 간다.
       `L0#width`처럼 적으면 무엇을 의심하는지 보이고, 그걸 보고 판단하면
       결과가 휜다 — 가림의 이유가 사라진다.
    3. **순위를 드러내지 않는다.** 진단 순서대로 번호를 매기면 `C0000`이 1순위임이
       보인다. 그래서 순번이 아니라 **내용을 요약한 값**으로 만든다.

    좌표는 넣지 않는다. 자가 바뀌면 예측이 흔들려 좌표도 흔들린다 — 좌표는
    **근거 데이터**이지 실제 오류의 이름이 아니다(docs/25 R5).

    `occurrence`는 **같은 (이미지, 라벨, 유형)이 여러 번 나올 때만** 쓴다.
    한 이미지에서 누락 후보가 여럿일 때가 그렇다.
    """
    seed = chr(10).join([image, str(label_index), suspicion, str(occurrence)])
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return ("L" if label_index is not None else "C") + digest



def load_label_diagnosis(dataset_id: str) -> dict:
    """진단 결과 파일을 **가공 없이** 읽는다.

    화면용 변환(`_load_label_diagnosis_json`)을 거치지 않는다 — 한국어 라벨을
    붙이고 문구를 덧대는 층이라, 얼릴 대상은 그 아래의 원본이다.
    """
    path = UPLOADS_DIR / dataset_id / "label_diagnosis.json"
    if not path.exists():
        raise HTTPException(404, "아직 라벨 단위 진단을 하지 않았습니다.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"진단 결과를 읽지 못했습니다: {exc}") from exc


def _code_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace",
                             cwd=str(EXPERIMENT_ROOT), timeout=20)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None



# 방법 이름. 기준선을 늘릴 때 이 자리에 붙인다.
AIDA = "aida"
IOU_BASELINE = "iou_baseline"


def _scores(item: dict) -> dict[str, float]:
    """이 후보에 각 방법이 매긴 점수.

    **기준선 점수를 여기서 지어내지 않는다.** 진단이 `label_iou`를 적어 준
    후보에만 붙는다 — 누락 후보에는 대조할 라벨이 없어 그 값이 없고, 그
    자리에 임의 공식을 넣으면 그건 IoU 기준선이 아닌 다른 것을 재게 된다
    (docs/evaluation-adjudication-design.md).

    옛 진단 결과 파일에는 `label_iou`가 없다. 그때는 AIDA 점수만 붙고,
    기준선을 넣어 내보내려 하면 `export_for_aggregation`이 막는다 — 조용히
    0점을 주는 것보다 낫다.
    """
    scores = {AIDA: float(item.get("severity", 0.0))}
    label_iou = item.get("label_iou")
    if item.get("label_index") is not None and label_iou is not None:
        # 안 맞을수록 의심. 이 한 줄이 기준선의 전부다.
        scores[IOU_BASELINE] = round(1.0 - float(label_iou), 4)
    return scores


def build_snapshot(dataset_id: str, evaluation_id: str, diagnosis: dict,
                   ruler=None, shuffle_seed: int = 0) -> EvaluationSnapshot:
    """진단 결과를 얼려 평가 묶음을 만든다.

    **재진단해도 이 묶음은 안 바뀐다.** 판정 도중에 후보가 바뀌면 이미 내린
    판정이 무엇을 가리키는지 알 수 없게 된다.
    """
    queue = diagnosis.get("review_queue") or []
    # 같은 (이미지, 라벨, 유형)이 여러 번 나올 때만 번호가 필요하다 —
    # 한 이미지에 누락 후보가 여럿인 경우다.
    seen = defaultdict(itertools.count)
    candidates = [
        EvaluationCandidate(
            canonical_candidate_id=canonical_id(
                item.get("image", ""), item.get("label_index"),
                item.get("suspicion", ""),
                occurrence=next(seen[(item.get("image", ""),
                                      item.get("label_index"),
                                      item.get("suspicion", ""))])),
            image=item.get("image", ""),
            label_index=item.get("label_index"),
            suspicion=item.get("suspicion", ""),
            box=item.get("box"),
            scores=_scores(item),
        )
        for item in queue
    ]
    snapshot = EvaluationSnapshot(
        evaluation_id=evaluation_id, dataset_id=dataset_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        diagnosis_generated_at=diagnosis.get("generated_at"),
        code_commit=_code_commit(), ruler=ruler,
        candidates=candidates, shuffle_seed=shuffle_seed,
    )
    return snapshot.model_copy(
        update={"candidate_set_hash": candidate_set_hash(candidates)})


def save_snapshot(dataset_id: str, snapshot: EvaluationSnapshot) -> None:
    _write_atomic(eval_dir(dataset_id, snapshot.evaluation_id) / SNAPSHOT_FILE,
                  snapshot.model_dump_json(indent=2))


def load_snapshot(dataset_id: str, evaluation_id: str) -> EvaluationSnapshot:
    path = eval_dir(dataset_id, evaluation_id) / SNAPSHOT_FILE
    if not path.exists():
        raise HTTPException(404, "평가 묶음이 없습니다. 먼저 시작하세요.")
    try:
        return EvaluationSnapshot.model_validate_json(
            path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # 묶음이 깨지면 판정이 무엇을 가리키는지 알 수 없다. 여기서는 막는다.
        raise HTTPException(500, f"평가 묶음이 손상됐습니다: {exc}") from exc


def load_adjudications(dataset_id: str, evaluation_id: str,
                       expected_hash: str) -> EvaluationAdjudications:
    """판정을 읽되 **다른 묶음에 붙은 것이면 읽지 않는다.**"""
    path = eval_dir(dataset_id, evaluation_id) / ADJUDICATIONS_FILE
    if not path.exists():
        return EvaluationAdjudications(evaluation_id=evaluation_id,
                                       candidate_set_hash=expected_hash)
    try:
        saved = EvaluationAdjudications.model_validate_json(
            path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # 판정을 막지 않되 **손상을 정상적인 빈 판정으로 숨기지 않는다.**
        return EvaluationAdjudications(evaluation_id=evaluation_id,
                                       candidate_set_hash=expected_hash,
                                       damaged=True)
    if saved.candidate_set_hash != expected_hash:
        raise HTTPException(
            409, "이 판정은 다른 후보 목록에 붙은 것입니다. 되살리면 무엇을 "
                 "가리키는지 알 수 없어 읽지 않습니다.")
    return saved


def validate_adjudications(snapshot: EvaluationSnapshot,
                           rows: list[EvaluationAdjudication]) -> None:
    """판정이 규약을 지키는가 (docs/evaluation-adjudication-design.md)."""
    by_id = {c.canonical_candidate_id: c for c in snapshot.candidates}
    seen: set[str] = set()

    for r in rows:
        cand = by_id.get(r.canonical_candidate_id)
        if cand is None:
            raise HTTPException(
                400, f"이 묶음에 없는 후보입니다: {r.canonical_candidate_id}")
        if r.canonical_candidate_id in seen:
            raise HTTPException(
                400, f"같은 후보가 두 번 나왔습니다: {r.canonical_candidate_id}")
        seen.add(r.canonical_candidate_id)

        if r.verdict is not None and r.verdict not in VALID_VERDICTS:
            raise HTTPException(400, f"알 수 없는 판정: {r.verdict}")

        if r.verdict in (None, "miss", "hold"):
            if r.unique_error_id:
                raise HTTPException(
                    400, "오류로 판정하지 않은 것에는 고유 오류 id를 붙이지 "
                         f"않습니다: {r.canonical_candidate_id}")
            continue

        # 여기부터는 hit이다.
        if cand.label_index is not None:
            # 기존 라벨은 서버가 정한다 — 판정자가 고를 것이 없다.
            expected = f"{cand.image}/L{cand.label_index}"
            if r.unique_error_id not in (None, expected):
                raise HTTPException(
                    400, f"기존 라벨의 고유 오류 id는 자동으로 정해집니다 "
                         f"(기대 {expected}, 받은 {r.unique_error_id})")
            continue

        # 누락 후보는 판정자가 어느 객체인지 정해야 한다.
        if not r.unique_error_id:
            raise HTTPException(
                400, f"누락 후보를 오류로 판정하려면 어느 객체인지 정해야 "
                     f"합니다: {r.canonical_candidate_id}. 후보 id로 대신하면 "
                     "겹친 후보가 서로 다른 오류로 세어져 고유 오류 수가 "
                     "부풀려집니다.")
        if _missing_error_id(cand.image, r.unique_error_id) is None:
            raise HTTPException(
                400, "누락 객체 이름은 'M<번호>' 꼴이어야 합니다 (그 후보의 "
                     f"이미지에 한해 '<이미지>/M<번호>'도 받습니다): "
                     f"{r.unique_error_id!r}")



def _missing_error_id(image: str, raw: str | None) -> str | None:
    """누락 객체 이름을 `{image}/M{n}`으로 맞춘다. 아니면 `None`.

    **번호는 이미지 안에서 매기고 이미지는 서버가 붙인다** — 기존 라벨과 같은
    방식이다. 판정자가 다른 이미지의 이름을 달면 두 이미지의 오류가 한 오류로
    세어진다.

    이미 붙은 형태(`a.jpg/M1`)도 받는다. 화면이 저장된 판정을 그대로 다시
    보내는 것이 정상 흐름이라, 서버가 돌려준 값을 서버가 거절하면 안 된다.
    """
    if not raw:
        return None
    if MISSING_ID.fullmatch(raw):
        return f"{image}/{raw}"
    prefix, sep, name = raw.rpartition("/")
    if sep and prefix == image and MISSING_ID.fullmatch(name):
        return raw
    return None


def resolve_unique_error_ids(snapshot: EvaluationSnapshot,
                             rows: list[EvaluationAdjudication],
                             ) -> list[EvaluationAdjudication]:
    """기존 라벨 hit의 고유 오류 id를 서버가 채운다.

    `suspicion`이 달라도 같은 라벨이면 **같은 실제 오류**다 — 그래야 같은 오류를
    두 번 지목한 것이 성과로 세어지지 않는다.
    """
    by_id = {c.canonical_candidate_id: c for c in snapshot.candidates}
    out = []
    for r in rows:
        cand = by_id[r.canonical_candidate_id]
        if r.verdict == "hit" and cand.label_index is not None:
            r = r.model_copy(
                update={"unique_error_id": f"{cand.image}/L{cand.label_index}"})
        elif r.verdict == "hit":
            r = r.model_copy(update={
                "unique_error_id": _missing_error_id(cand.image,
                                                     r.unique_error_id)})
        out.append(r)
    return out


def save_adjudications(dataset_id: str, evaluation_id: str,
                       snapshot: EvaluationSnapshot,
                       rows: list[EvaluationAdjudication],
                       ) -> EvaluationAdjudications:
    validate_adjudications(snapshot, rows)
    resolved = resolve_unique_error_ids(snapshot, rows)
    saved = EvaluationAdjudications(
        evaluation_id=evaluation_id,
        candidate_set_hash=snapshot.candidate_set_hash,
        adjudications=resolved,
        updated_at=datetime.now(timezone.utc).isoformat())
    _write_atomic(eval_dir(dataset_id, evaluation_id) / ADJUDICATIONS_FILE,
                  saved.model_dump_json(indent=2))
    return saved


def blind_queue(snapshot: EvaluationSnapshot,
                saved: EvaluationAdjudications) -> BlindQueue:
    """판정 화면에 보낼 목록. **점수·순위·진단 문구를 뺀다.**

    순서는 묶음에 적힌 씨앗으로 섞는다 — 순위대로 주면 그것이 곧 힌트다.
    """
    by_id = {a.canonical_candidate_id: a for a in saved.adjudications}
    items = []
    for c in snapshot.candidates:
        a = by_id.get(c.canonical_candidate_id)
        items.append(BlindCandidate(
            canonical_candidate_id=c.canonical_candidate_id,
            image=c.image, label_index=c.label_index, box=c.box,
            verdict=a.verdict if a else None,
            unique_error_id=a.unique_error_id if a else None))
    random.Random(snapshot.shuffle_seed).shuffle(items)
    return BlindQueue(evaluation_id=snapshot.evaluation_id,
                      dataset_id=snapshot.dataset_id,
                      candidate_set_hash=snapshot.candidate_set_hash,
                      candidates=items, damaged=saved.damaged)


# ── 내보내기 ──────────────────────────────────────────────────────────────────

class ExportBlocked(Exception):
    """내보낼 수 없다. 이유를 담는다."""


def export_for_aggregation(snapshot: EvaluationSnapshot,
                           saved: EvaluationAdjudications,
                           methods: list[str]) -> dict:
    """집계 모듈이 그대로 받는 JSON.

    **후보 집합이 방법마다 다르면 거부한다** — 정렬 효과는 같은 후보 안에서만
    잰다(docs/evaluation-protocol.md).

    **누락 후보의 단순 기준선 점수는 아직 정의되지 않았다.** 임의 공식을 만들지
    않고 그 비교를 막는다 — 예측 신뢰도를 쓰면 IoU 기준선이 아니라 신뢰도
    기준선이 되고, 가장 가까운 라벨과의 IoU를 쓰면 전부 동점이 된다.
    """
    for method in methods:
        without = [c for c in snapshot.candidates if method not in c.scores]
        if not without:
            continue
        missing = [c for c in without if c.label_index is None]
        if missing:
            raise ExportBlocked(
                f"'{method}'가 누락 후보에 줄 점수가 정해지지 않았습니다 "
                f"({len(missing)}건). 임의 공식을 만들지 않습니다 — 기존 라벨 "
                "후보만 견주거나 누락을 별도 층으로 평가할지 먼저 정해야 "
                "합니다(docs/evaluation-adjudication-design.md).")
        raise ExportBlocked(
            f"'{method}'의 점수가 없는 후보가 {len(without)}건 있습니다. "
            "후보 집합이 다르면 정렬 효과가 아니라 작업 전체 효과입니다.")

    by_id = {a.canonical_candidate_id: a for a in saved.adjudications}
    adjudications = []
    rankings = []
    for c in snapshot.candidates:
        a = by_id.get(c.canonical_candidate_id)
        adjudications.append({
            "canonical_candidate_id": c.canonical_candidate_id,
            "image": c.image, "label_index": c.label_index,
            "suspicion": c.suspicion,
            "verdict": a.verdict if a else None,
            "unique_error_id": a.unique_error_id if a else None,
            "group_id": None,
            "complete": bool(a and a.verdict is not None),
        })
        for method in methods:
            rankings.append({"method": method,
                             "canonical_candidate_id": c.canonical_candidate_id,
                             "severity": c.scores[method]})

    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "evaluation_id": snapshot.evaluation_id,
        "dataset_id": snapshot.dataset_id,
        "snapshot_hash": snapshot.candidate_set_hash,
        "methods": methods,
        "adjudications": adjudications,
        "rankings": rankings,
    }


# ── API ───────────────────────────────────────────────────────────────────────

class StartEvaluation(BaseModel):
    """평가를 시작한다. 지금 후보 목록을 얼린다."""
    evaluation_id: str
    shuffle_seed: int = 0


class SaveAdjudications(BaseModel):
    # 다른 묶음에 붙은 판정을 받지 않으려고 함께 보낸다.
    candidate_set_hash: str
    adjudications: list[EvaluationAdjudication] = []


@router.post("/{dataset_id}/evaluations", response_model=EvaluationSnapshot)
def start_evaluation(dataset_id: str, body: StartEvaluation) -> EvaluationSnapshot:
    """진단 결과를 얼려 평가 묶음을 만든다.

    이미 있으면 **덮어쓰지 않는다** — 판정 도중에 후보가 바뀌면 이미 내린 판정이
    무엇을 가리키는지 알 수 없다.
    """
    path = eval_dir(dataset_id, body.evaluation_id) / SNAPSHOT_FILE
    if path.exists():
        raise HTTPException(409, "이미 있는 평가입니다. 묶음은 덮어쓰지 않습니다.")

    from .upload import _load_ruler_sidecar
    diagnosis = load_label_diagnosis(dataset_id)
    snapshot = build_snapshot(dataset_id, body.evaluation_id, diagnosis,
                              ruler=_load_ruler_sidecar(dataset_id),
                              shuffle_seed=body.shuffle_seed)
    save_snapshot(dataset_id, snapshot)
    return snapshot


@router.get("/{dataset_id}/evaluations/{evaluation_id}/queue",
            response_model=BlindQueue)
def get_blind_queue(dataset_id: str, evaluation_id: str) -> BlindQueue:
    """가림 판정 목록. 점수·순위·진단 문구가 빠져 있다."""
    snapshot = load_snapshot(dataset_id, evaluation_id)
    saved = load_adjudications(dataset_id, evaluation_id,
                               snapshot.candidate_set_hash)
    return blind_queue(snapshot, saved)


@router.put("/{dataset_id}/evaluations/{evaluation_id}/adjudications",
            response_model=EvaluationAdjudications)
def put_adjudications(dataset_id: str, evaluation_id: str,
                      body: SaveAdjudications) -> EvaluationAdjudications:
    snapshot = load_snapshot(dataset_id, evaluation_id)
    if body.candidate_set_hash != snapshot.candidate_set_hash:
        raise HTTPException(
            409, "후보 목록이 그 사이에 바뀌었습니다. 판정을 저장하지 않습니다.")
    return save_adjudications(dataset_id, evaluation_id, snapshot,
                              body.adjudications)


@router.get("/{dataset_id}/evaluations/{evaluation_id}/export")
def get_export(dataset_id: str, evaluation_id: str,
               methods: str = "aida") -> dict:
    """집계 모듈에 그대로 넣는 JSON.

    `methods`는 쉼표로 나눈다. 기준선을 넣었는데 점수가 없으면 **거부한다.**
    """
    snapshot = load_snapshot(dataset_id, evaluation_id)
    saved = load_adjudications(dataset_id, evaluation_id,
                               snapshot.candidate_set_hash)
    try:
        return export_for_aggregation(snapshot, saved,
                                      [m.strip() for m in methods.split(",") if m.strip()])
    except ExportBlocked as exc:
        raise HTTPException(409, str(exc)) from exc
