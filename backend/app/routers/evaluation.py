"""평가용 가림 판정 (docs/evaluation-adjudication-design.md).

**제품의 재검수 판정과 섞지 않는다.** 제품 판정은 순위와 의심 유형을 보고
매기지만, 평가 판정은 그것을 가린 채 매겨야 결과가 안 휜다. 파일도 따로 쓴다 —
기존 `verdicts.json`은 읽지도 고치지도 않는다.

이 모듈이 만드는 것은 **판정을 기록할 길**이다. 판정 자체는 아직 사람이 하고,
그 사람이 지금은 개발자다. **"독립된 사람이 정답을 확정했다"가 아니다.**
"""
import hashlib
import json
import math
import random
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import EXPERIMENT_ROOT, UPLOADS_DIR
from ..ranking import (LEGACY_RANKING_VERSION, RANKING_V1, RANKING_V2, RankingVersionError,
                       diagnosis_filename, ranking_version_of, require_version)
from ..agreement import agreement_report
from ..models import (BlindBundle, BlindCandidate, BlindQueue, EVALUATION_SCHEMA_VERSION,
                      EvaluationAdjudication, EvaluationAdjudications,
                      EvaluationCandidate, EvaluationSnapshot)

router = APIRouter(prefix="/api/datasets", tags=["evaluation"])

SNAPSHOT_FILE = "snapshot.json"
ADJUDICATIONS_FILE = "adjudications.json"
# 판정자 (사전 등록 D8). `primary`는 사람 판정이고 옛 파일 이름 그대로다. 다른 판정자는
# 자기 파일(`adjudications.<id>.json`)에 따로 저장한다 — 원본을 섞지 않는다.
PRIMARY_ADJUDICATOR = "primary"
ADJUDICATOR_PATTERN = re.compile(r"^[a-z0-9_-]{1,20}$")
AUXILIARY_ROUNDING = "ceil"


def require_adjudicator(adjudicator: str) -> str:
    if not ADJUDICATOR_PATTERN.fullmatch(adjudicator or ""):
        raise HTTPException(400, "판정자 id 형식이 아닙니다 (소문자·숫자·_·-, 20자 이내).")
    return adjudicator


def adjudications_file(adjudicator: str) -> str:
    require_adjudicator(adjudicator)
    return (ADJUDICATIONS_FILE if adjudicator == PRIMARY_ADJUDICATOR
            else f"adjudications.{adjudicator}.json")
# 작업 기록. **판정 결과와 섞지 않는다** — 수명도 쓰임도 다르다.
ACTIVITY_FILE = "activity.jsonl"
EVENT_SCHEMA_VERSION = 1
# 한 번에 받는 이벤트 수. 화면이 폭주해도 파일이 무한정 커지지 않게.
MAX_EVENTS_PER_REQUEST = 500
VALID_VERDICTS = {"hit", "miss", "hold"}
# 누락 객체의 이름. 판정자가 이미지 안에서 번호를 매긴다.
MISSING_ID = re.compile(r"^M\d+$")
# 이미지 → 연속 장면 묶음 이름. 데이터셋 폴더에 있으면 묶음을 만들 때 얼린다.
GROUPS_FILE = "groups.json"


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


def normalize_box(box) -> list[float] | None:
    """상자를 지문에 넣을 수 있는 모양으로. 없으면 None.

    소수점 아래를 자른다 — 같은 상자가 부동소수 표현 차이로 다른 지문을 내면
    "내용이 같은가"를 못 말한다.
    """
    if not box:
        return None
    return [round(float(v), 4) for v in box]


def canonical_payload(dataset_id: str, candidates: list[EvaluationCandidate],
                      shuffle_seed: int, ruler, diagnosis_generated_at,
                      judge_budget: int | None = None,
                      candidate_pool: str | None = None,
                      total_in_queue: int | None = None,
                      ranking_version: str | None = None,
                      random_sample_size: int | None = None,
                      random_sample_seed: int | None = None,
                      label_height_filter: dict | None = None,
                      auxiliary_sample: dict | None = None,
                      tie_seed: int | None = None,
                      bootstrap_coverage: dict | None = None,
                      display_plan: dict | None = None) -> dict:
    """지문을 만들 재료. **판정에 영향을 주는 것만, 전부.**

    빠지면 안 되는 것과 들어가면 안 되는 것이 둘 다 있다.

    | 넣는다 | 왜 |
    |---|---|
    | 후보의 상자 | 같은 라벨의 같은 유형이라도 다른 상자면 다른 것을 보라는 뜻이다 |
    | 방법별 점수 | 점수가 바뀌면 순위가 바뀌고, 예산 안에 드는 후보가 달라진다 |
    | AIDA 제품 순위 | AIDA 순서는 점수가 아니라 이것이다 |
    | `shuffle_seed` | 판정 순서가 달라지면 같은 묶음이 아니다 |
    | 자(`ruler`) | 어느 자로 잰 후보인가 |
    | 진단 생성 시각 | 어느 진단을 얼린 것인가 |
    | 판정 예산·후보 출처·전체 후보 수 | 무엇을 판정하고 무엇과 견줄 수 있는지가 바뀐다 |
    | 순위 버전 | 같은 후보라도 AIDA 순서의 뜻이 다르다 (docs/adr-ranking-separation.md) |
    | 장면 묶음(`group_id`) | 재표집 단위가 바뀌면 구간이 바뀐다. 판정 뒤에 묶음을 바꾸지 못하게 한다 |

    **`created_at`과 `code_commit`은 넣지 않는다.** 실행할 때마다 달라지거나
    내용과 무관해서, 넣으면 지문이 "내용이 같은가"를 못 말하게 된다.

    **순위 버전은 있을 때만 넣는다.** 옛 묶음(prelim1 등)에는 버전이 없고, 넣으면 그
    지문이 바뀌어 이미 내린 판정이 묶음에서 떨어진다.

    후보는 이름순으로, 사전 키도 정렬해 담는다 — 목록 순서가 지문을 바꾸면
    안 된다. 순서는 씨앗이 따로 정한다.
    """
    payload = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "shuffle_seed": shuffle_seed,
        "diagnosis_generated_at": diagnosis_generated_at,
        "judge_budget": judge_budget,
        "candidate_pool": candidate_pool,
        "total_in_queue": total_in_queue,
        "ruler": ruler.model_dump() if ruler is not None else None,
        "candidates": [
            {
                "canonical_candidate_id": c.canonical_candidate_id,
                "image": c.image,
                "label_index": c.label_index,
                "suspicion": c.suspicion,
                "box": normalize_box(c.box),
                "class_name": c.class_name,
                "scores": {k: c.scores[k] for k in sorted(c.scores)},
                "aida_rank": c.aida_rank,
                # 기본값이 아닐 때만 넣는다 — 옛 묶음의 지문이 그대로여야 한다.
                **({"source": c.source} if c.source != SOURCE_AIDA else {}),
                **({"random_sample": True} if c.random_sample else {}),
                **({"confidence": c.confidence} if c.confidence is not None else {}),
                **({"group_id": c.group_id} if c.group_id is not None else {}),
            }
            for c in sorted(candidates, key=lambda c: c.canonical_candidate_id)
        ],
    }
    if ranking_version is not None:
        payload["ranking_version"] = ranking_version
    if random_sample_size is not None:
        payload["random_sample"] = {"size": random_sample_size,
                                    "seed": random_sample_seed}
    if label_height_filter is not None:
        # 범위가 다르면 다른 묶음이다 — 옛 묶음(필터 없음)의 지문은 그대로다.
        payload["label_height_filter"] = label_height_filter
    if auxiliary_sample is not None:
        # 보조 표본은 판정 전에 고정된다. 규칙과 씨앗이 지문에 들어가야 나중에 바꿀 수 없다.
        payload["auxiliary_sample"] = {k: auxiliary_sample[k] for k in
                                       ("fraction", "seed", "rounding", "pool", "size")}
    if tie_seed is not None:
        # 동점 순서가 바뀌면 상위 N이 바뀐다 — 씨앗은 지문에 들어간다.
        payload["tie_seed"] = tie_seed
    if bootstrap_coverage is not None:
        # 계산 설정·입력 지문·최종 추가 목록이 지문에 든다 — 판정 전에 고정된다.
        payload["bootstrap_coverage"] = {k: bootstrap_coverage[k] for k in
                                         ("iterations", "seed", "budget", "methods",
                                          "input_fingerprint", "additional_candidate_ids")}
    if display_plan is not None:
        # 판정 화면의 묶음 나누기(층·묶음 경계·묶음 안 순서)는 판정 조건이다 — 지문에 넣는다.
        # 없을 때는 넣지 않아 옛 묶음(practice1·qa1)의 지문이 그대로다. 같은 내용에 계획만 더한
        # 묶음은 이 키를 뺀 지문(`content_hash`)이 옛 묶음과 같다.
        payload["display_plan"] = display_plan_fingerprint(display_plan)
    return payload


def candidate_set_hash(payload: dict) -> str:
    """묶음의 지문. **판정에 영향을 주는 것이 하나라도 바뀌면 값이 바뀐다.**

    예전에는 후보 id만 해시했다. 그러면 같은 id에 상자나 점수가 바뀌어도 지문이
    그대로라, 이미 내린 판정이 **다른 내용의 후보에 조용히 붙는다.**
    """
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_id(image: str, label_index: int | None, suspicion: str,
                 box=None) -> str:
    """후보의 영구 이름 (docs/evaluation-adjudication-design.md).

    **결정론적이고 순서에 안 기댄다.** 같은 내용이면 목록 어디에 있든 같은
    이름이다. 그래서 묶음을 다시 만들어도 서로 대조할 수 있다.

    네 가지를 동시에 지켜야 한다.

    1. **이미지를 담는다.** `label_index`는 이미지 안에서만 번호다. 이름에
       이미지가 없으면 `a.jpg`의 0번과 `b.jpg`의 0번이 같은 이름이 되어 한쪽에
       내린 판정이 다른 쪽에 붙는다.
    2. **의심 유형을 드러내지 않는다.** 이름은 가림 판정 화면에 그대로 간다.
       `L0#width`처럼 적으면 무엇을 의심하는지 보인다.
    3. **순위를 드러내지 않는다.** 진단 순서대로 번호를 매기면 `C0000`이 1순위임이
       보인다.
    4. **목록 순번에 기대지 않는다.** 순번으로 구분하면 진단이 순서를 바꾸는
       것만으로 두 후보의 이름이 서로 뒤바뀐다. 순서 규칙은 실제로 두 번
       바뀌었다(docs/21 AN·AO).

    그래서 **내용을 요약한 값**으로 만들고, 그 내용에 상자를 넣는다.

    **후보 이름에는 좌표를 써도 된다. 실제 오류의 이름(`unique_error_id`)에는
    안 된다.** 후보는 얼린 진단 안의 한 줄을 가리키므로 그 줄의 좌표가 곧
    정체다. 반면 실제 오류는 자가 바뀌어 좌표가 흔들려도 같은 오류여야 한다
    (docs/25 R5에서 판정이 사라지던 원인).
    """
    seed = json.dumps(
        {"image": image, "label_index": label_index, "suspicion": suspicion,
         "box": normalize_box(box)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return ("L" if label_index is not None else "C") + digest


def load_label_diagnosis(dataset_id: str, ranking_version: str = RANKING_V1) -> dict:
    """진단 결과 파일을 **가공 없이** 읽는다.

    화면용 변환(`_load_label_diagnosis_json`)을 거치지 않는다 — 한국어 라벨을
    붙이고 문구를 덧대는 층이라, 얼릴 대상은 그 아래의 원본이다.

    **순위 버전마다 파일이 다르고, 파일 안에 적힌 버전이 요청과 다르면 얼리지
    않는다** (docs/adr-ranking-separation.md).
    """
    try:
        name = diagnosis_filename(ranking_version)
    except RankingVersionError as exc:
        raise HTTPException(400, str(exc)) from exc
    path = UPLOADS_DIR / dataset_id / name
    if not path.exists():
        raise HTTPException(404, f"이 순위 버전({ranking_version})의 라벨 단위 진단이 없습니다.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"진단 결과를 읽지 못했습니다: {exc}") from exc
    _require_diagnosis_version(data, ranking_version, name)
    return data


def load_groups(dataset_id: str) -> dict[str, str] | None:
    """데이터셋 폴더의 `groups.json`(이미지 이름 → 묶음 이름). 없으면 None.

    **모양이 틀리면 얼리지 않는다.** 조용히 건너뛰면 이미지 단위로 재표집되어, 이웃 프레임이
    독립 표본처럼 세어진다.
    """
    path = UPLOADS_DIR / dataset_id / GROUPS_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"{GROUPS_FILE}를 읽지 못했습니다: {exc}") from exc
    if not isinstance(data, dict) or not data or not all(
            isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in data.items()):
        raise HTTPException(400, f"{GROUPS_FILE}는 비어 있지 않은 {{이미지 이름: 묶음 이름}}이어야 합니다.")
    return data


def _assign_groups(candidates: list[EvaluationCandidate],
                   groups: dict[str, str] | None) -> list[EvaluationCandidate]:
    """후보마다 묶음을 붙인다. **묶음 표에 없는 이미지가 하나라도 있으면 거부한다.**"""
    if groups is None:
        return candidates
    missing = sorted({c.image for c in candidates if c.image not in groups})
    if missing:
        raise HTTPException(
            400, f"{GROUPS_FILE}에 없는 이미지가 {len(missing)}장 있습니다 (예: {missing[0]}). "
                 "일부만 묶으면 재표집 단위가 섞입니다.")
    return [c.model_copy(update={"group_id": groups[c.image]}) for c in candidates]


def _require_diagnosis_version(diagnosis: dict, expected: str, where: str) -> None:
    try:
        found = ranking_version_of(diagnosis)
    except RankingVersionError as exc:
        raise HTTPException(409, f"{where}: {exc}") from exc
    if found != expected:
        raise HTTPException(
            409, f"{where}에 적힌 순위 버전({found})이 요청({expected})과 다릅니다. "
                 "다른 순서를 그 이름으로 얼리지 않습니다.")


def snapshot_ranking_version(snapshot: EvaluationSnapshot) -> str:
    """묶음의 순위 버전. 기록이 없는 옛 묶음은 v1이다 — v2 전에는 v1뿐이었다."""
    return snapshot.ranking_version or LEGACY_RANKING_VERSION


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
# 후보 생성까지 포함한 비교의 방법들 (docs/next-work-2026-09-15.md W3).
# **모집단이 AIDA 후보보다 넓다** — 규칙이 놓친 라벨과 필터가 버린 예측까지 본다.
ALL_LABEL_IOU = "all_label_iou"            # 모든 기존 라벨을 1 − label_iou로
UNMATCHED_CONFIDENCE = "unmatched_confidence"   # 필터 전 미매칭 예측을 확신도로
# Cleanlab ObjectLab 기준선 (experiment/objectlab_baseline.py). 진단이 점수를 적어 준 행에만 붙는다.
ALL_LABEL_OBJECTLAB = "all_label_objectlab"       # 모든 기존 라벨을 1 − objectlab_score로
UNMATCHED_OBJECTLAB = "unmatched_objectlab"       # 미매칭 예측을 1 − objectlab_overlooked로

# 후보의 출처. 무엇을 AIDA의 성과로 셀 수 있는지가 여기서 갈린다.
SOURCE_AIDA = "aida_candidate"
SOURCE_LABEL = "label"
SOURCE_PREDICTION = "unmatched_prediction"

# 비교 모드. **어느 모집단을 재는가**이고, 사전 등록이 이것을 고정한다.
WITHIN_AIDA = "within_aida_candidates"            # AIDA 후보 안의 재정렬 (prelim1과 같은 질문)
GENERATION_INCLUDED = "candidate_generation_included"   # 후보 생성까지 포함
COMPARISON_MODES = (WITHIN_AIDA, GENERATION_INCLUDED)
# 그 모드에서만 쓸 수 있는 방법 — 모집단이 AIDA 후보 밖으로 넓어지기 때문이다.
POPULATION_METHODS = (ALL_LABEL_IOU, UNMATCHED_CONFIDENCE, ALL_LABEL_OBJECTLAB, UNMATCHED_OBJECTLAB)


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



def _box_key(image: str, box) -> tuple:
    """상자로 같은 예측을 잇는 열쇠. 진단과 **같은 반올림**이라 그대로 맞는다."""
    return (image, tuple(normalize_box(box) or ()))


def _population_candidates(candidates: list[EvaluationCandidate],
                           diagnosis: dict) -> list[EvaluationCandidate]:
    """규칙 밖 모집단을 후보 목록에 더한다 (docs/next-work-2026-09-15.md W3).

    **같은 대상은 한 번만 얼린다.** AIDA가 이미 고른 라벨·예측은 새로 만들지 않고 그
    후보에 점수(와 확신도)만 붙인다 — 둘로 나누면 판정자가 같은 상자를 두 번 보고, 한
    오류가 두 번 세어질 자리가 생긴다.

    모집단이 없는 옛 진단은 **아무것도 바뀌지 않는다.**
    """
    labels = diagnosis.get("all_labels")
    predictions = diagnosis.get("unmatched_predictions")
    if labels is None and predictions is None:
        return candidates

    by_label = {(c.image, c.label_index): c for c in candidates
                if c.label_index is not None}
    by_box = {_box_key(c.image, c.box): c for c in candidates if c.label_index is None}
    out = list(candidates)

    for row in labels or []:
        value = row.get("label_iou")
        if value is None:
            # 점수를 지어내지 않는다. 그 라벨은 이 방법의 모집단에 못 들어간다.
            continue
        score = round(1.0 - float(value), 4)
        scores = {ALL_LABEL_IOU: score}
        ol = row.get("objectlab_score")
        if ol is not None:
            # 낮을수록 의심이라 뒤집는다. 없는 행은 이 방법의 모집단에 없다.
            scores[ALL_LABEL_OBJECTLAB] = round(1.0 - float(ol), 4)
        found = by_label.get((row.get("image", ""), row.get("label_index")))
        if found is not None:
            found.scores.update(scores)
            continue
        out.append(EvaluationCandidate(
            canonical_candidate_id=canonical_id(
                row.get("image", ""), row.get("label_index"), "", row.get("box")),
            image=row.get("image", ""), label_index=row.get("label_index"),
            suspicion="", box=row.get("box"), class_name=row.get("class_name"),
            scores=scores, source=SOURCE_LABEL))

    seen_boxes: set[tuple] = set()
    for row in predictions or []:
        value = row.get("confidence")
        if value is None:
            continue
        confidence = round(float(value), 4)
        key = _box_key(row.get("image", ""), row.get("box"))
        if key in seen_boxes:
            # 판정 화면은 이미지와 상자만 보여주고 후보 이름에도 클래스가 없다(옛 지문과
            # 호환되어야 한다). 조용히 하나를 덮어쓰면 그 후보의 확신도와 기준선 점수가
            # 다른 예측의 것이 되고, 새로 만들면 판정자가 구분할 수 없는 후보가 둘 생긴다.
            raise HTTPException(
                409, f"같은 이미지에서 상자가 같은 미매칭 예측이 둘 이상입니다 "
                     f"({row.get('image', '')} {row.get('box')}). 판정자가 둘을 구분할 "
                     "수 없어 얼리지 않습니다 — 진단 결과를 확인하세요.")
        seen_boxes.add(key)
        scores = {UNMATCHED_CONFIDENCE: confidence}
        ol = row.get("objectlab_overlooked")
        if ol is not None:
            scores[UNMATCHED_OBJECTLAB] = round(1.0 - float(ol), 4)
        found = by_box.get(key)
        if found is not None:
            found.scores.update(scores)
            found.confidence = confidence
            continue
        out.append(EvaluationCandidate(
            canonical_candidate_id=canonical_id(
                row.get("image", ""), None, "", row.get("box")),
            image=row.get("image", ""), label_index=None, suspicion="",
            box=row.get("box"), class_name=row.get("class_name"),
            scores=scores, confidence=confidence,
            source=SOURCE_PREDICTION))
    return out


def _box_height(box) -> float | None:
    if not box or len(box) < 4:
        return None
    return float(box[3]) - float(box[1])


def _apply_label_height_filter(candidates: list[EvaluationCandidate],
                               min_height_px: float | None,
                               ) -> tuple[list[EvaluationCandidate], dict | None]:
    """기존 라벨 층의 높이 필터 (사전 등록 D2).

    **어디에 거는가.** 진단이 아니라 묶음을 얼릴 때다. 진단에서 작은 라벨을 지우면 그
    자리의 예측이 짝을 잃어 **없던 누락 후보가 생긴다.** 여기서는 진단이 낸 후보·모집단을
    그대로 두고 평가 범위만 좁힌다 — 원본 라벨은 손대지 않는다.

    **무엇에 거는가.** `label_index`가 있는 후보 전부 — AIDA 후보, `all_label_iou`·ObjectLab
    모집단, 그리고 그 뒤에 뽑는 무작위 표본 K까지 같은 범위다. **누락 층(예측)에는 걸지
    않는다.** 작은 예측의 처리는 누락 층의 기존 규칙(AIDA는 확신도·가림 문턱, 기준선은
    필터 전 전부)을 그대로 따른다.

    높이는 후보의 `box`(원본 이미지 픽셀 좌표, y2 − y1)다. 경계값은 **미만 제외, 이상 포함**.
    상자가 없는 기존 라벨 후보는 높이를 알 수 없어 거부한다 — 조용히 남기면 범위가 어긋난다.
    """
    if min_height_px is None:
        return candidates, None
    if isinstance(min_height_px, bool) or not isinstance(min_height_px, (int, float)) \
            or not math.isfinite(min_height_px) or min_height_px <= 0:
        raise HTTPException(400, "기존 라벨 높이 필터는 0보다 큰 유한한 픽셀 값입니다.")
    kept: list[EvaluationCandidate] = []
    excluded = {SOURCE_AIDA: 0, SOURCE_LABEL: 0}
    for c in candidates:
        if c.label_index is None:
            kept.append(c)
            continue
        h = _box_height(c.box)
        if h is None:
            raise HTTPException(
                409, f"상자가 없는 기존 라벨 후보가 있어 높이 필터를 걸 수 없습니다: "
                     f"{c.image} 라벨 {c.label_index}")
        if h < min_height_px:
            excluded[c.source] = excluded.get(c.source, 0) + 1
            continue
        kept.append(c)
    record = {
        "min_height_px": float(min_height_px),
        "coordinate_space": "원본 이미지 픽셀 (box[3] − box[1])",
        "rule": "높이 < min_height_px 인 기존 라벨 후보 제외. 이상은 포함",
        "applies_to": "기존 라벨 층 전부 (AIDA 후보·all_label_iou·ObjectLab 모집단·무작위 표본 K)",
        "not_applied_to": "누락 층 (예측) — 작은 예측은 누락 층의 기존 규칙대로",
        "excluded_aida_candidates": excluded.get(SOURCE_AIDA, 0),
        "excluded_labels": excluded.get(SOURCE_LABEL, 0),
        "kept_labelled": sum(1 for c in kept if c.label_index is not None),
    }
    return kept, record


def _mark_random_sample(candidates: list[EvaluationCandidate],
                        size: int | None, seed: int | None) -> None:
    """규칙 밖 라벨에서 K건을 씨앗으로 뽑아 표시한다.

    **AIDA가 고른 후보는 표본이 아니다** — 이 층은 "규칙이 놓친 라벨에 오류가 얼마나
    있나"를 재고, 그러려면 규칙 밖에서 고르게 뽑아야 한다. 씨앗이 없으면 같은 표본을
    다시 만들 수 없으므로 거부한다.
    """
    if size is None:
        return
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise HTTPException(400, "무작위 표본 크기는 0 이상의 정수입니다.")
    if size and seed is None:
        raise HTTPException(400, "무작위 표본 씨앗을 함께 정하세요 — 없으면 같은 "
                                 "표본을 다시 만들 수 없습니다.")
    pool = sorted((c for c in candidates if c.source == SOURCE_LABEL),
                  key=lambda c: c.canonical_candidate_id)
    if size > len(pool):
        raise HTTPException(
            400, f"규칙 밖 기존 라벨이 {len(pool)}건인데 무작위 표본 {size}건을 "
                 "요청했습니다. 진단에 모든 라벨이 들어 있는지 확인하세요.")
    for candidate in random.Random(seed).sample(pool, size):
        candidate.random_sample = True


def _draw_auxiliary_sample(snapshot: EvaluationSnapshot, fraction: float | None,
                           seed: int | None) -> dict | None:
    """보조 판정 표본 (사전 등록 D8).

    **확정된 판정 대상**(예산이 있으면 층별 상위 N 합집합 ∪ 무작위 표본, 없으면 전부)에서
    단순 무작위로 뽑는다. 크기는 `ceil(fraction × 대상 수)` — 반올림 규칙을 기록한다.
    씨앗 없이는 같은 표본을 다시 만들 수 없으므로 거부한다. 뽑은 목록은 정렬해 저장하고,
    지문에는 규칙·씨앗·크기가 들어간다.
    """
    if fraction is None:
        return None
    if (isinstance(fraction, bool) or not isinstance(fraction, (int, float))
            or not math.isfinite(fraction) or not (0 < fraction <= 1)):
        raise HTTPException(400, "보조 표본 비율은 0 초과 1 이하입니다.")
    if seed is None:
        raise HTTPException(400, "보조 표본 씨앗을 함께 정하세요 — 없으면 같은 표본을 다시 만들 수 없습니다.")
    allowed = judge_ids(snapshot)
    pool = sorted(allowed if allowed is not None
                  else {c.canonical_candidate_id for c in snapshot.candidates})
    size = math.ceil(fraction * len(pool))
    picked = sorted(random.Random(seed).sample(pool, size))
    return {
        "fraction": float(fraction), "seed": seed, "rounding": AUXILIARY_ROUNDING,
        "pool": ("judge_ids (층별 방법 상위 N 합집합 ∪ 무작위 표본 K ∪ 고정 재표본 추가 후보)"
                 if allowed is not None else "all_candidates"),
        "represents": ("최종 판정 목록 전체에서의 사람–보조 판정 일치도. 원래 상위 N만의 일치도가 "
                       "아니며, 추가 후보와 K 표본이 섞여 있다"),
        "pool_size": len(pool), "size": size,
        "candidate_ids": picked,
        "blinding": "보조 판정자에게는 이 목록의 후보만, 점수·순위·방법·출처·표본 여부·다른 판정자의 판정 없이 보낸다",
    }


def _reject_duplicates(candidates: list[EvaluationCandidate]) -> None:
    """이름이 겹치는 후보가 있으면 얼리기를 **거부한다.**

    이름은 (이미지, 라벨, 유형, 상자)의 요약이므로, 겹친다는 것은 진단이
    **모든 항목이 같은 줄을 두 번 냈다**는 뜻이다. 판정자는 둘을 구분할 방법이
    없다 — 하나로 접으면 판정 하나가 소리 없이 사라지고, 그냥 두면 같은 것을
    두 번 세게 된다. 어느 쪽도 맞지 않으니 여기서 멈추고 진단 쪽을 보게 한다.
    """
    seen: set[str] = set()
    repeated = sorted({c.canonical_candidate_id for c in candidates
                       if c.canonical_candidate_id in seen
                       or seen.add(c.canonical_candidate_id)})
    if repeated:
        raise HTTPException(
            409, f"진단 결과에 완전히 같은 후보가 여러 번 있습니다 "
                 f"({len(repeated)}건). 판정자가 둘을 구분할 수 없어 얼리지 "
                 "않습니다 — 진단 결과를 먼저 확인하세요.")


def _rank(item: dict) -> int | None:
    rank = item.get("rank")
    return rank if isinstance(rank, int) and not isinstance(rank, bool) else None


def build_snapshot(dataset_id: str, evaluation_id: str, diagnosis: dict,
                   ruler=None, shuffle_seed: int = 0,
                   judge_budget: int | None = None,
                   ranking_version: str | None = None,
                   random_sample_size: int | None = None,
                   random_sample_seed: int | None = None,
                   groups: dict[str, str] | None = None,
                   min_label_height_px: float | None = None,
                   auxiliary_sample_fraction: float | None = None,
                   auxiliary_sample_seed: int | None = None,
                   tie_seed: int | None = None,
                   coverage_iterations: int | None = None,
                   coverage_seed: int | None = None,
                   display_plan: dict | None = None) -> EvaluationSnapshot:
    """진단 결과를 얼려 평가 묶음을 만든다.

    **재진단해도 이 묶음은 안 바뀐다.** 판정 도중에 후보가 바뀌면 이미 내린
    판정이 무엇을 가리키는지 알 수 없게 된다.

    **잘리기 전 후보 전부(`all_candidates`)를 얼린다.** `review_queue`는 AIDA
    순위 상위 N건이라 그것만 얼리면 기준선이 AIDA 하위 후보를 끌어올릴 기회가
    없다. 옛 진단에는 `all_candidates`가 없어 `review_queue`를 얼리고, 잘렸는지는
    `total_in_queue`와 대조해 두 방법을 내보낼 때 막는다.

    `ranking_version`을 주면 진단에 적힌 버전과 같아야 하고, 묶음에 얼리고 지문에
    넣는다. 안 주면 옛 방식 그대로다(버전 없음 = v1, 지문 재료도 예전과 같다).
    """
    if ranking_version is not None:
        try:
            require_version(ranking_version)
        except RankingVersionError as exc:
            raise HTTPException(400, str(exc)) from exc
        _require_diagnosis_version(diagnosis, ranking_version, "진단 결과")
    if ruler is not None and getattr(ruler, "weights_sha256", None):
        # 외부 자를 고른 진단은 결과에 실제로 연 자의 해시가 있어야 하고 같아야 한다.
        found = (diagnosis.get("ruler") or {}).get("sha256")
        if found != ruler.weights_sha256:
            raise HTTPException(
                409, f"자 기록의 SHA-256({ruler.weights_sha256[:12]}…)과 진단 결과의 자"
                     f"({str(found)[:12]}…)가 다릅니다. 다른 자로 잰 후보를 얼리지 않습니다.")
    if "all_candidates" in diagnosis:
        pool, queue = "all_candidates", diagnosis.get("all_candidates") or []
    else:
        pool, queue = "review_queue", diagnosis.get("review_queue") or []
    total = diagnosis.get("total_in_queue")
    if not isinstance(total, int) or isinstance(total, bool):
        total = None
    candidates = [
        EvaluationCandidate(
            canonical_candidate_id=canonical_id(
                item.get("image", ""), item.get("label_index"),
                item.get("suspicion", ""), item.get("box")),
            image=item.get("image", ""),
            label_index=item.get("label_index"),
            suspicion=item.get("suspicion", ""),
            box=item.get("box"),
            class_name=item.get("class_name"),
            scores=_scores(item),
            aida_rank=_rank(item),
        )
        for item in queue
    ]
    # 규칙 밖 모집단(모든 기존 라벨·필터 전 미매칭 예측)과 무작위 표본.
    candidates = _population_candidates(candidates, diagnosis)
    _reject_duplicates(candidates)
    # 높이 필터는 무작위 표본보다 **앞**이다 — 표본도 같은 범위에서 뽑아야 한다.
    candidates, height_filter = _apply_label_height_filter(candidates, min_label_height_px)
    _mark_random_sample(candidates, random_sample_size, random_sample_seed)
    candidates = _assign_groups(candidates, groups)
    snapshot = EvaluationSnapshot(
        evaluation_id=evaluation_id, dataset_id=dataset_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        diagnosis_generated_at=diagnosis.get("generated_at"),
        code_commit=_code_commit(), ruler=ruler,
        candidates=candidates, shuffle_seed=shuffle_seed,
        candidate_pool=pool, total_in_queue=total, judge_budget=judge_budget,
        ranking_version=ranking_version,
        random_sample_size=random_sample_size, random_sample_seed=random_sample_seed,
        label_height_filter=height_filter,
        tie_seed=tie_seed,
    )
    # 예산이 있으면 여기서 판정 대상을 한 번 골라 본다 — 못 고르는 묶음을 얼리지 않는다.
    base_pool = judge_ids(snapshot)
    if coverage_iterations is not None or coverage_seed is not None:
        # 고정 재표본 합집합 (안 (a)). 원래 판정 범위(상위 N 합집합 ∪ K)를 기준으로 추가분을 센다.
        coverage = compute_bootstrap_coverage(snapshot, coverage_iterations, coverage_seed,
                                              set(base_pool or ()))
        snapshot = snapshot.model_copy(update={"bootstrap_coverage": coverage})
    # 보조 표본은 판정 대상이 확정된 **뒤**에 뽑는다 — 대상 밖 후보가 표본에 들면 안 된다.
    # 합집합 추가분이 있으면 그것까지 포함한 **최종 판정 목록**에서 뽑는다.
    auxiliary = _draw_auxiliary_sample(snapshot, auxiliary_sample_fraction, auxiliary_sample_seed)
    snapshot = snapshot.model_copy(update={"auxiliary_sample": auxiliary})
    # 묶음 표시 계획은 **판정 대상과 보조 표본이 다 정해진 뒤**, 그 가림 순서에서 만든다 —
    # 대상·순서·표본을 바꾸지 않고 화면의 묶음 경계만 정한다.
    if display_plan is not None:
        snapshot = snapshot.model_copy(
            update={"display_plan": build_display_plan(snapshot, display_plan)})
    return snapshot.model_copy(
        update={"candidate_set_hash": candidate_set_hash(snapshot_payload(snapshot))})


def snapshot_payload(snapshot: EvaluationSnapshot,
                     include_display_plan: bool = True) -> dict:
    """얼린 묶음에서 지문 재료를 다시 만든다. `build_snapshot`이 지문을 낼 때도 이것을 쓴다.

    `include_display_plan=False`는 **내용 지문**의 재료다 — 묶음 표시 계획만 뺐으므로, 같은 진단·같은
    설정으로 얼린 계획 없는 묶음의 지문과 같아야 한다(qa1 ↔ qa1b 내용 동일성 확인).
    """
    return canonical_payload(
        snapshot.dataset_id, snapshot.candidates, snapshot.shuffle_seed, snapshot.ruler,
        snapshot.diagnosis_generated_at,
        judge_budget=snapshot.judge_budget, candidate_pool=snapshot.candidate_pool,
        total_in_queue=snapshot.total_in_queue, ranking_version=snapshot.ranking_version,
        random_sample_size=snapshot.random_sample_size,
        random_sample_seed=snapshot.random_sample_seed,
        label_height_filter=snapshot.label_height_filter,
        auxiliary_sample=snapshot.auxiliary_sample,
        tie_seed=snapshot.tie_seed,
        bootstrap_coverage=snapshot.bootstrap_coverage,
        display_plan=snapshot.display_plan if include_display_plan else None)


def content_hash(snapshot: EvaluationSnapshot) -> str:
    """묶음 표시 계획을 뺀 지문. 계획이 없는 묶음이면 `candidate_set_hash`와 같다."""
    return candidate_set_hash(snapshot_payload(snapshot, include_display_plan=False))


# ── 판정 화면의 묶음 나누기 (사전 등록 D5·D6) ─────────────────────────────────

DISPLAY_PLAN_VERSION = "layer_bundles_v1"
DISPLAY_LAYER_ORDER = ("labelled_candidates", "missing_candidates")
DISPLAY_PLAN_RULE = (
    "주 판정자(primary)의 가림 순서(shuffle_seed로 섞인 최종 판정 목록)에서 층마다 상대 순서를 그대로 "
    "두고, 기존 라벨 층을 labelled_bundles개의 연속 구간으로 나눈다(크기는 고르게, 나머지는 앞 묶음부터 "
    "1건씩). 누락 층은 별도 묶음 하나로 기존 라벨 묶음들 뒤에 둔다(D6). 빈 층은 묶음을 만들지 않는다. "
    "층과 목록 안 위치로만 정해지므로 방법·점수·출처·무작위 표본·재표본 추가·보조 표본 여부와 무관하다")
DISPLAY_PLAN_REST = (
    "묶음 경계에서 쉴 수 있다. 이것은 묶음 표시 규칙이며 5-2절의 약 150건 단위 휴식 계획(운영 규칙)과 "
    "별개다 — 둘 다 판정 대상·순서·C와 무관하다")


def _layer_of(label_index: int | None) -> str:
    return DISPLAY_LAYER_ORDER[0] if label_index is not None else DISPLAY_LAYER_ORDER[1]


def _even_sizes(total: int, parts: int) -> list[int]:
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def build_display_plan(snapshot: EvaluationSnapshot, request: dict) -> dict:
    """묶음 표시 계획을 만든다. **결정론적** — 얼린 묶음의 가림 순서만 재료로 쓴다.

    `request`는 `{"version": "layer_bundles_v1", "labelled_bundles": k}`. k는 사전 등록 D5가 정한
    묶음 수를 그대로 적는다(코드가 대신 정하지 않는다).
    """
    if not isinstance(request, dict):
        raise HTTPException(400, "묶음 표시 계획은 객체여야 합니다.")
    unknown = sorted(set(request) - {"version", "labelled_bundles"})
    if unknown:
        raise HTTPException(400, f"묶음 표시 계획에 모르는 항목이 있습니다: {unknown}")
    if request.get("version") != DISPLAY_PLAN_VERSION:
        raise HTTPException(400, f"묶음 표시 계획 버전은 {DISPLAY_PLAN_VERSION!r}입니다.")
    k = request.get("labelled_bundles")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise HTTPException(400, "labelled_bundles(기존 라벨 층 묶음 수)는 1 이상의 정수입니다.")
    order = _shuffled_ids(snapshot, judge_ids(snapshot))
    by_id = {c.canonical_candidate_id: c for c in snapshot.candidates}
    labelled = [cid for cid in order if _layer_of(by_id[cid].label_index) == DISPLAY_LAYER_ORDER[0]]
    missing = [cid for cid in order if _layer_of(by_id[cid].label_index) == DISPLAY_LAYER_ORDER[1]]
    if labelled and k > len(labelled):
        raise HTTPException(400, f"기존 라벨 판정 대상이 {len(labelled)}건인데 묶음 {k}개를 요청했습니다.")
    bundles = []
    at = 0
    for size in (_even_sizes(len(labelled), k) if labelled else []):
        bundles.append({"layer": DISPLAY_LAYER_ORDER[0], "candidate_ids": labelled[at:at + size]})
        at += size
    if missing:
        bundles.append({"layer": DISPLAY_LAYER_ORDER[1], "candidate_ids": missing})
    return {
        "version": DISPLAY_PLAN_VERSION,
        "request": {"version": DISPLAY_PLAN_VERSION, "labelled_bundles": k},
        "rule": DISPLAY_PLAN_RULE,
        "rest": DISPLAY_PLAN_REST,
        "source_order": "blind_queue(primary) — shuffle_seed로 섞인 최종 판정 목록 순서",
        "applies_to_adjudicator": PRIMARY_ADJUDICATOR,
        "layer_order": list(DISPLAY_LAYER_ORDER),
        "layer_sizes": {DISPLAY_LAYER_ORDER[0]: len(labelled), DISPLAY_LAYER_ORDER[1]: len(missing)},
        "bundle_sizes": [len(b["candidate_ids"]) for b in bundles],
        "bundles": bundles,
    }


def display_plan_fingerprint(plan: dict) -> dict:
    """지문에 넣는 계획의 재료 — 버전·층 순서·묶음마다 층과 후보 id 순서. 설명 문구는 뺀다."""
    return {"version": plan["version"], "layer_order": list(plan["layer_order"]),
            "bundles": [{"layer": b["layer"], "candidate_ids": list(b["candidate_ids"])}
                        for b in plan["bundles"]]}


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
                       expected_hash: str,
                       adjudicator: str = PRIMARY_ADJUDICATOR) -> EvaluationAdjudications:
    """판정을 읽되 **다른 묶음에 붙은 것이면 읽지 않는다.** 판정자마다 파일이 다르다."""
    path = eval_dir(dataset_id, evaluation_id) / adjudications_file(adjudicator)
    if not path.exists():
        return EvaluationAdjudications(evaluation_id=evaluation_id,
                                       candidate_set_hash=expected_hash,
                                       adjudicator=adjudicator)
    try:
        saved = EvaluationAdjudications.model_validate_json(
            path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # 판정을 막지 않되 **손상을 정상적인 빈 판정으로 숨기지 않는다.**
        return EvaluationAdjudications(evaluation_id=evaluation_id,
                                       candidate_set_hash=expected_hash,
                                       damaged=True, adjudicator=adjudicator)
    if saved.candidate_set_hash != expected_hash:
        raise HTTPException(
            409, "이 판정은 다른 후보 목록에 붙은 것입니다. 되살리면 무엇을 "
                 "가리키는지 알 수 없어 읽지 않습니다.")
    if saved.adjudicator != adjudicator:
        raise HTTPException(
            409, f"{path.name}에 적힌 판정자({saved.adjudicator})가 요청({adjudicator})과 다릅니다. "
                 "다른 판정자의 원본을 빌려 쓰지 않습니다.")
    return saved


def auxiliary_ids(snapshot: EvaluationSnapshot) -> set[str] | None:
    """보조 판정 표본의 후보 id. 표본이 없는 묶음이면 None."""
    if not snapshot.auxiliary_sample:
        return None
    return set(snapshot.auxiliary_sample.get("candidate_ids", []))


def validate_adjudications(snapshot: EvaluationSnapshot,
                           rows: list[EvaluationAdjudication]) -> None:
    """판정이 규약을 지키는가 (docs/evaluation-adjudication-design.md)."""
    by_id = {c.canonical_candidate_id: c for c in snapshot.candidates}
    seen: set[str] = set()
    allowed = judge_ids(snapshot)

    for r in rows:
        cand = by_id.get(r.canonical_candidate_id)
        if cand is None:
            raise HTTPException(
                400, f"이 묶음에 없는 후보입니다: {r.canonical_candidate_id}")
        if allowed is not None and r.canonical_candidate_id not in allowed:
            raise HTTPException(
                400, "판정 예산 밖의 후보입니다. 두 방법 상위 "
                     f"{snapshot.judge_budget}건의 합집합만 판정합니다: "
                     f"{r.canonical_candidate_id}")
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
                       adjudicator: str = PRIMARY_ADJUDICATOR,
                       ) -> EvaluationAdjudications:
    validate_adjudications(snapshot, rows)
    if adjudicator != PRIMARY_ADJUDICATOR:
        # 보조 판정자는 보조 표본만 판정한다. 표본 밖 판정은 받지 않는다.
        sample = auxiliary_ids(snapshot)
        if sample is None:
            raise HTTPException(409, "이 묶음에는 보조 판정 표본이 없습니다. 보조 판정을 받지 않습니다.")
        outside = [r.canonical_candidate_id for r in rows if r.canonical_candidate_id not in sample]
        if outside:
            raise HTTPException(400, f"보조 표본 밖의 후보를 판정했습니다: {outside[0]} 외 {len(outside) - 1}건")
    resolved = resolve_unique_error_ids(snapshot, rows)
    saved = EvaluationAdjudications(
        evaluation_id=evaluation_id,
        candidate_set_hash=snapshot.candidate_set_hash,
        adjudications=resolved,
        updated_at=datetime.now(timezone.utc).isoformat(),
        adjudicator=adjudicator)
    _write_atomic(eval_dir(dataset_id, evaluation_id) / adjudications_file(adjudicator),
                  saved.model_dump_json(indent=2))
    return saved


def blind_queue(snapshot: EvaluationSnapshot,
                saved: EvaluationAdjudications,
                adjudicator: str = PRIMARY_ADJUDICATOR) -> BlindQueue:
    """판정 화면에 보낼 목록. **점수·순위·진단 문구를 뺀다.**

    순서는 묶음에 적힌 씨앗으로 섞는다 — 순위대로 주면 그것이 곧 힌트다.
    """
    by_id = {a.canonical_candidate_id: a for a in saved.adjudications}
    items = []
    # 판정 예산이 있으면 두 방법 상위 N건의 합집합만 보낸다. 겹친 후보는 한 번만.
    allowed = judge_ids(snapshot)
    if adjudicator != PRIMARY_ADJUDICATOR:
        # 보조 판정자는 보조 표본만 본다. 다른 판정자의 판정은 `saved`가 자기 파일이라 섞이지 않는다.
        sample = auxiliary_ids(snapshot)
        if sample is None:
            raise HTTPException(409, "이 묶음에는 보조 판정 표본이 없습니다.")
        allowed = sample if allowed is None else (allowed & sample)
    # 묶음 표시 계획은 주 판정자 화면에만 쓴다. 보조 판정자(보조 표본만 보는 목록)는 묶음 없이 예전처럼.
    plan = snapshot.display_plan if adjudicator == PRIMARY_ADJUDICATOR else None
    bundle_of = _bundle_index(plan) if plan else {}
    for c in snapshot.candidates:
        if allowed is not None and c.canonical_candidate_id not in allowed:
            continue
        a = by_id.get(c.canonical_candidate_id)
        # `bundle`은 계획이 있을 때만 넣는다 — 계획 없는 묶음의 응답 필드 집합을 바꾸지 않는다.
        extra = ({"bundle": bundle_of[c.canonical_candidate_id]}
                 if c.canonical_candidate_id in bundle_of else {})
        items.append(BlindCandidate(
            canonical_candidate_id=c.canonical_candidate_id,
            image=c.image, label_index=c.label_index, box=c.box,
            class_name=c.class_name,
            verdict=a.verdict if a else None,
            unique_error_id=a.unique_error_id if a else None, **extra))
    # **섞기는 계획과 무관하게 같다.** 계획은 이 섞인 순서를 층별로 나눈 것이다.
    random.Random(snapshot.shuffle_seed).shuffle(items)
    if not plan:
        return BlindQueue(evaluation_id=snapshot.evaluation_id,
                          dataset_id=snapshot.dataset_id,
                          candidate_set_hash=snapshot.candidate_set_hash,
                          candidates=items, damaged=saved.damaged)
    items, bundles = _apply_display_plan(plan, items)
    return BlindQueue(evaluation_id=snapshot.evaluation_id,
                      dataset_id=snapshot.dataset_id,
                      candidate_set_hash=snapshot.candidate_set_hash,
                      candidates=items, damaged=saved.damaged, bundles=bundles)


def _shuffled_ids(snapshot: EvaluationSnapshot, allowed: set[str] | None) -> list[str]:
    """`blind_queue`(primary)와 같은 규칙의 섞인 후보 id 순서. 판정 상태와 무관하다."""
    ids = [c.canonical_candidate_id for c in snapshot.candidates
           if allowed is None or c.canonical_candidate_id in allowed]
    random.Random(snapshot.shuffle_seed).shuffle(ids)
    return ids


def _bundle_index(plan: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, b in enumerate(plan["bundles"]):
        for cid in b["candidate_ids"]:
            out[cid] = i
    return out


def _apply_display_plan(plan: dict, items: list[BlindCandidate]
                        ) -> tuple[list[BlindCandidate], list[BlindBundle]]:
    """섞인 목록을 계획의 묶음 순서로 놓는다. **계획과 판정 목록이 하나라도 다르면 멈춘다** —
    빠진 후보가 조용히 안 보이거나 묶음 밖 후보가 끼면 판정 대상이 바뀐다."""
    by_id = {i.canonical_candidate_id: i for i in items}
    planned = [cid for b in plan["bundles"] for cid in b["candidate_ids"]]
    if len(planned) != len(set(planned)) or set(planned) != set(by_id):
        raise HTTPException(500, "묶음 표시 계획이 판정 목록과 맞지 않습니다. 묶음 파일을 확인하세요.")
    ordered = [by_id[cid] for cid in planned]
    layers = [b["layer"] for b in plan["bundles"]]
    bundles = [BlindBundle(index=i, layer=layer,
                           layer_bundle=layers[:i + 1].count(layer),
                           layer_bundles=layers.count(layer),
                           size=len(plan["bundles"][i]["candidate_ids"]))
               for i, layer in enumerate(layers)]
    return ordered, bundles


# ── 내보내기 ──────────────────────────────────────────────────────────────────

class ExportBlocked(Exception):
    """내보낼 수 없다. 이유를 담는다."""


# 평가 층. **기존 라벨과 누락을 한 숫자로 합치지 않는다.**
LABELLED = "labelled_candidates"
MISSING = "missing_candidates"
ALL_DESCRIPTIVE = "all_descriptive"
SCOPES = (LABELLED, MISSING, ALL_DESCRIPTIVE)
# 층마다 정의된 방법. 여기 없는 방법을 그 층에 붙이면 거부한다 — 층이 다르면
# 같은 이름이라도 다른 것을 잰다.
SCOPE_METHODS = {LABELLED: (AIDA, IOU_BASELINE, ALL_LABEL_IOU, ALL_LABEL_OBJECTLAB),
                 MISSING: (AIDA, UNMATCHED_CONFIDENCE, UNMATCHED_OBJECTLAB),
                 ALL_DESCRIPTIVE: (AIDA,)}

_LIMITATION = {
    LABELLED:
        "AIDA가 만든 동일 후보 집합 안에서의 조건부 재정렬 효과입니다. "
        "후보 생성까지 포함한 전체 제품 효과가 아닙니다.",
    MISSING:
        "누락 후보에는 사전 정의된 비교군이 없습니다. 기술 통계만 내며 "
        "성공·실패를 판정하지 않습니다.",
    ALL_DESCRIPTIVE:
        "전체 후보 현황 확인용입니다. 층이 섞여 있어 방법 간 성공 판정에 "
        "쓰지 않습니다.",
}


def _in_scope(candidate: EvaluationCandidate, scope: str) -> bool:
    if scope == LABELLED:
        return candidate.label_index is not None
    if scope == MISSING:
        return candidate.label_index is None
    return True


def _exclusion_reason(candidate: EvaluationCandidate, scope: str, mode: str) -> str:
    """왜 뺐는가. **미정이라서가 아니라 층이나 모집단이 달라서다.**"""
    if _in_scope(candidate, scope) and candidate.source != SOURCE_AIDA:
        return ("AIDA 규칙 밖 모집단 — 후보 생성 포함 모드"
                f"(`{GENERATION_INCLUDED}`)에서만 센다")
    if scope == LABELLED:
        return "누락 후보 — 비교군이 없어 별도 층에서 기술 통계로만 본다"
    return "기존 라벨 후보 — 누락 층에 속하지 않는다"


AIDA_V2_LABELLED_BASIS = "score_1_minus_label_iou"


def method_order(candidates: list[EvaluationCandidate],
                 method: str, ranking_version: str = RANKING_V1,
                 scope: str | None = None) -> dict[str, float] | None:
    """방법이 후보를 줄 세우는 값. **클수록 먼저다.** 못 매기면 `None`.

    **모집단은 방법마다 다르다** (docs/next-work-2026-09-15.md W3). AIDA는 자기 규칙이
    만든 후보만, `all_label_iou`는 기존 라벨 전부, `unmatched_confidence`는 필터 전
    미매칭 예측 전부를 줄 세운다. 자기 모집단 밖 후보는 그 방법의 순서에 **없다** —
    맨 뒤로 보내면 그 방법이 만들지도 않은 후보를 본 것처럼 세어진다.

    집계 모듈(`evaluation.ranking`)은 이 값을 `severity`로 받아 내림차순, 같으면
    이미지·후보 id 순으로 자른다. 판정 대상 고르기와 내보내기가 **같은 값**을
    쓰도록 여기 하나만 둔다 — 둘이 다르면 예산 안에 판정 안 한 후보가 들어간다.

    **AIDA는 진단의 `rank`다.** 제품 화면은 계통적 유형을 먼저, 그 안에서
    심각도 순으로 보여준다(`label_diagnosis.review_order`). 심각도로 다시 줄
    세우면 제품이 안 쓰는 순서를 평가한다 — 계통적이지 않은 유형의 높은
    심각도가 맨 위로 올라온다(docs/21 AN). 순위가 없거나 겹치면 지어내지 않는다.

    기준선은 점수(`1 − label_iou`) 그대로다. 동점은 집계 규약이 자른다.
    """
    if method == AIDA:
        mine = [c for c in candidates if c.source == SOURCE_AIDA]
        if not mine:
            return None
        if ranking_version == RANKING_V2 and scope == LABELLED:
            # **v2 기존 라벨 층의 평가 순서는 점수 `1 − label_iou`다** (사전 등록 D9). 제품의
            # `aida_rank`는 같은 점수를 이미지 이름·라벨 번호로 잘라 매긴 것이라, 그것을 쓰면
            # 동점 씨앗이 AIDA에는 작동하지 않고 `all_label_iou`에만 작동한다. 점수로 돌리면 같은
            # 후보가 두 방법에서 같은 `tie_key`를 받아 동점 순서가 방법 간에 일관된다. 화면의
            # 제품 순위는 그대로이고, 평가만 이 순서를 쓴다 — docs/qa-preregistration-proposal.
            if any(c.scores.get(IOU_BASELINE) is None for c in mine):
                return None
            return {c.canonical_candidate_id: c.scores[IOU_BASELINE] for c in mine}
        ranks = [c.aida_rank for c in mine]
        if any(r is None for r in ranks) or len(set(ranks)) != len(ranks):
            return None
        return {c.canonical_candidate_id: -float(c.aida_rank) for c in mine}
    mine = [c for c in candidates if method in c.scores]
    if not mine:
        return None
    return {c.canonical_candidate_id: c.scores[method] for c in mine}


def tie_key(tie_seed: int | None, candidate_id: str) -> str | None:
    """동점 키 (사전 등록 D9). `sha256("{tie_seed}:{후보 id}")`.

    **후보와 씨앗만으로 정해진다** — 입력 순서·프로세스·방법과 무관하다. 같은 후보는 어느
    방법에서든 같은 키를 받으므로 방법 간 동점 순서가 일관된다. 씨앗이 없으면 None이고
    옛 규칙(이미지 이름 → 후보 id)으로 자른다.
    """
    if tie_seed is None:
        return None
    return hashlib.sha256(f"{tie_seed}:{candidate_id}".encode("utf-8")).hexdigest()


def _sort_key(c: EvaluationCandidate, order: dict[str, float], tie_seed: int | None) -> tuple:
    key = tie_key(tie_seed, c.canonical_candidate_id)
    if key is not None:
        return (-order[c.canonical_candidate_id], key, c.image, c.canonical_candidate_id)
    return (-order[c.canonical_candidate_id], c.image, c.canonical_candidate_id)


def _top(candidates: list[EvaluationCandidate], order: dict[str, float],
         n: int, tie_seed: int | None = None) -> list[str]:
    """`evaluation.ranking.rank_candidates`와 같은 규칙으로 상위 n건.

    그 방법의 모집단이 n보다 작으면 **남는 예산은 안 쓴다** — 다른 방법의 후보로
    채우면 그 방법이 만들지 않은 후보가 그 방법의 성과로 세어진다.

    동점은 `tie_seed`가 있으면 `tie_key` 순, 없으면 이미지·후보 id 순이다. 내보내기의
    `tie_key`와 집계의 `rank_candidates`가 같은 값을 쓰므로 여기서 고른 상위 N과 집계가
    세는 상위 N이 같다.
    """
    mine = [c for c in candidates if c.canonical_candidate_id in order]
    ranked = sorted(mine, key=lambda c: _sort_key(c, order, tie_seed))
    return [c.canonical_candidate_id for c in ranked[:n]]


def _aggregation():
    """실험 쪽 집계 패키지(표준 라이브러리만). coverage는 **최종 분석과 같은 코드**로 돈다."""
    import sys
    root = str(EXPERIMENT_ROOT)
    if root not in sys.path:
        sys.path.append(root)
    from evaluation import coverage, importer      # noqa: WPS433
    return coverage, importer


def _export_fingerprint(export: dict) -> str:
    """coverage 입력의 지문 — 모집단(후보 id·묶음)과 순위(방법·점수·동점 키)만."""
    material = {
        "adjudications": sorted((r["canonical_candidate_id"], r["group_id"] or "")
                                for r in export["adjudications"]),
        "rankings": sorted((r["method"], r["canonical_candidate_id"], r["severity"], r.get("tie_key"))
                           for r in export["rankings"]),
    }
    return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def compute_bootstrap_coverage(snapshot: EvaluationSnapshot, iterations: int, seed: int,
                               base_pool: set[str]) -> dict:
    """기존 라벨 층의 1차 비교 방법들에 대해, 고정 재표본에서 상위 N에 드는 후보의 합집합.

    **최종 분석과 같은 길**을 탄다: `export_for_aggregation`(판정 없음) → `importer.load_export` →
    `coverage.resample_top_n_union`. 그래서 모집단·묶음·순위·동점 키가 분석과 정확히 같다. 판정한
    후보만 남겨 모집단을 줄이지 않는다 — 내보내기는 미판정 후보도 전부 담는다.
    """
    if snapshot.judge_budget is None:
        raise HTTPException(400, "판정 예산(N)이 있어야 재표본 합집합을 셀 수 있습니다.")
    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 1:
        raise HTTPException(400, "부트스트랩 반복 수는 1 이상의 정수입니다.")
    if seed is None:
        raise HTTPException(400, "부트스트랩 씨앗을 함께 정하세요 — 없으면 같은 재표본을 다시 만들 수 없습니다.")
    labelled = [c for c in snapshot.candidates if _in_scope(c, LABELLED)]
    version = snapshot_ranking_version(snapshot)
    methods = [m for m in (AIDA, ALL_LABEL_IOU, ALL_LABEL_OBJECTLAB)
               if method_order(labelled, m, version, LABELLED) is not None]
    if len(methods) < 2:
        raise HTTPException(409, "기존 라벨 층에 줄 세울 수 있는 방법이 둘 미만이라 합집합을 셀 수 없습니다.")
    empty = EvaluationAdjudications(evaluation_id=snapshot.evaluation_id,
                                    candidate_set_hash=snapshot.candidate_set_hash)
    try:
        export = export_for_aggregation(snapshot, empty, methods, LABELLED, GENERATION_INCLUDED)
    except ExportBlocked as exc:
        raise HTTPException(409, f"재표본 합집합을 낼 수 없습니다: {exc}") from exc
    coverage, importer = _aggregation()
    facts, ranks = importer.load_export(export, require_comparison=False)
    pool_keys = {a.key for a in facts if a.candidate_id in base_pool}
    result = coverage.resample_top_n_union(facts, ranks, methods, snapshot.judge_budget,
                                           iterations, seed, judged_pool=pool_keys)
    key_to_id = {a.key: a.candidate_id for a in facts}
    additional = sorted(key_to_id[k] for k in result["additional_candidate_keys"])
    return {
        "purpose": "부트스트랩 계산용. 비교 예산 N과 원래 상위 N·점 추정치는 바뀌지 않는다",
        "iterations": iterations, "seed": seed, "budget": snapshot.judge_budget,
        "methods": methods, "scope": LABELLED, "mode": GENERATION_INCLUDED,
        "input_fingerprint": _export_fingerprint(export),
        "base_pool_size": len(base_pool),
        "additional_count": len(additional),
        "additional_candidate_ids": additional,
        "per_method": result["methods"],
        "guarantee": ("고정 재표본의 판정 누락만 없앤다. 신뢰구간의 포함률·통계적 타당성은 "
                      "검증하지 않는다"),
    }


def coverage_ids(snapshot: EvaluationSnapshot) -> set[str]:
    if not snapshot.bootstrap_coverage:
        return set()
    return set(snapshot.bootstrap_coverage.get("additional_candidate_ids", []))


def judge_ids(snapshot: EvaluationSnapshot) -> set[str] | None:
    """판정할 후보. 판정 예산이 없으면 `None`(전부).

    **층마다 그 층에 정의된 방법의 상위 N건을 모아 합집합을 낸다.**

    | 층 | 방법 |
    |---|---|
    | 기존 라벨 | AIDA, 기준선, 그리고 모집단이 있으면 `all_label_iou` |
    | 누락 | AIDA, 그리고 모집단이 있으면 `unmatched_confidence` |

    두 방법이 같은 후보를 고르면 **한 번만** 판정한다. 그래야 N 이하의 어느
    검수량에서도 두 방법 모두 판정이 빠진 후보 없이 셀 수 있다.

    **무작위 표본은 예산과 별도로 전부 판정한다** — 표본에서 빠진 것이 생기면 그
    층의 비율 추정이 깨진다.
    """
    n = snapshot.judge_budget
    if n is None:
        return None
    picked: set[str] = set()
    for scope in (LABELLED, MISSING):
        layer = [c for c in snapshot.candidates if _in_scope(c, scope)]
        for method in SCOPE_METHODS[scope]:
            order = method_order(layer, method, snapshot_ranking_version(snapshot), scope)
            if order is None:
                if method == AIDA and any(c.source == SOURCE_AIDA for c in layer):
                    raise HTTPException(
                        409, "AIDA 제품 순위가 없거나 겹치는 진단입니다. 판정할 상위 "
                             "후보를 고를 수 없습니다 — 진단을 다시 돌리세요.")
                # 점수가 없는 방법(옛 진단의 기준선, 모집단 없는 진단). 내보낼 때 막힌다.
                continue
            picked.update(_top(layer, order, n, snapshot.tie_seed))
    picked.update(c.canonical_candidate_id for c in snapshot.candidates if c.random_sample)
    # 고정 재표본 합집합의 추가 후보 (안 (a)). 판정 대상에는 들지만 어느 방법의 원래 상위 N도
    # 바꾸지 않고 무작위 표본 K에 합쳐지지도 않는다.
    picked.update(coverage_ids(snapshot))
    return picked


def _truncation(snapshot: EvaluationSnapshot) -> str | None:
    """두 방법을 견줄 수 없게 잘린 묶음이면 그 이유. 아니면 `None`."""
    total = snapshot.total_in_queue
    if total is None:
        return ("진단 결과에 전체 후보 수(`total_in_queue`)가 없어 목록이 "
                "잘렸는지 알 수 없습니다. 두 방법을 견주지 않습니다.")
    frozen = sum(1 for c in snapshot.candidates if c.source == SOURCE_AIDA)
    # 높이 필터(D2)로 뺀 AIDA 후보는 잘린 것이 아니라 범위 밖이다 — 기록된 수만큼 되돌려 센다.
    if snapshot.label_height_filter:
        frozen += int(snapshot.label_height_filter.get("excluded_aida_candidates", 0))
    if frozen < total:
        return (f"AIDA 순위로 잘린 후보 목록입니다({frozen}/"
                f"{total}건). 기준선이 잘린 쪽 후보를 끌어올릴 수 없어 AIDA에 "
                "유리하게 휩니다 — `all_candidates`가 있는 진단으로 다시 얼리세요.")
    return None


def export_for_aggregation(snapshot: EvaluationSnapshot,
                           saved: EvaluationAdjudications,
                           methods: list[str],
                           scope: str = LABELLED,
                           mode: str = WITHIN_AIDA) -> dict:
    """집계 모듈이 그대로 받는 JSON.

    **층과 비교 모드를 먼저 고른다.** 기존 라벨 후보와 누락 후보는 비교 조건이 달라 한
    숫자로 합치지 않고(docs/evaluation-protocol.md), 같은 층이라도 **무엇을 모집단으로
    보느냐**에 따라 다른 질문이 된다(docs/next-work-2026-09-15.md W3).

    | scope | 무엇 | 비교 |
    |---|---|---|
    | `labelled_candidates` | `label_index`가 있는 후보 | 방법 간 비교 가능 |
    | `missing_candidates` | 누락 후보 | **보조 기술 통계만** — 성공·실패를 판정하지 않는다 |
    | `all_descriptive` | 전부 | **없다** — 현황 확인용 |

    | mode | 모집단 | 답하는 질문 |
    |---|---|---|
    | `within_aida_candidates` | AIDA 규칙이 만든 후보만 | 후보 안의 재정렬 (prelim1과 같은 질문) |
    | `candidate_generation_included` | 규칙 밖 라벨·예측까지 | 후보 생성까지 포함한 효과 (Q-A·Q-C) |

    **거른 것을 조용히 넘기지 않는다.** 몇 건을 왜 뺐는지 결과에 적는다 — 안 적으면
    나중에 그 숫자가 무엇을 뺀 값인지 아무도 모른다.

    **모집단이 방법마다 다르면 그 사실을 적는다.** `within_aida_candidates`에서는 예전처럼
    후보 집합이 다르면 거부하고, `candidate_generation_included`에서는 방법별 모집단 크기를
    `method_population`으로 내놓는다 — 그게 이 모드에서 재려는 것이기 때문이다.
    """
    if scope not in SCOPES:
        raise ExportBlocked(
            f"모르는 평가 층입니다: {scope!r}. 아는 것은 {', '.join(SCOPES)}입니다.")
    if mode not in COMPARISON_MODES:
        raise ExportBlocked(
            f"모르는 비교 모드입니다: {mode!r}. 아는 것은 {', '.join(COMPARISON_MODES)}입니다.")

    unknown = [m for m in methods if m not in SCOPE_METHODS[scope]]
    if unknown:
        raise ExportBlocked(
            f"'{scope}' 층에 정의되지 않은 방법입니다: {', '.join(unknown)}. "
            f"이 층의 방법은 {', '.join(SCOPE_METHODS[scope])}입니다.")

    wider = [m for m in methods if m in POPULATION_METHODS]
    if mode == WITHIN_AIDA and wider:
        raise ExportBlocked(
            f"{', '.join(wider)}는 AIDA 규칙 밖 모집단까지 줄 세웁니다. 후보 생성까지 "
            f"포함한 비교는 `{GENERATION_INCLUDED}` 모드로 요청하세요 — AIDA 후보 안의 "
            "재정렬과는 다른 질문입니다.")

    in_scope = [c for c in snapshot.candidates if _in_scope(c, scope)]
    included = (in_scope if mode == GENERATION_INCLUDED
                else [c for c in in_scope if c.source == SOURCE_AIDA])
    included_ids = {c.canonical_candidate_id for c in included}
    excluded = [c for c in snapshot.candidates
                if c.canonical_candidate_id not in included_ids]

    # 방법 간 비교로 읽어도 되는 층인가. **누락 층은 기준선이 생겨도 보조 통계다** —
    # 1차 지표로 올리려면 가설·점수·동점·Δ를 따로 사전 등록해야 한다.
    comparison_allowed = scope == LABELLED

    if not comparison_allowed and any(m not in SCOPE_METHODS[scope] for m in methods):
        # 비교군이 없는 층에 임의의 기준선을 붙이면, 그 자체로 "견줄 수 있다"는
        # 뜻이 되어 버린다.
        raise ExportBlocked(
            f"'{scope}' 층에는 사전 정의된 비교군이 없습니다. "
            f"AIDA 순위와 판정만 내보냅니다 — 요청한 방법: {', '.join(methods)}.")

    if (snapshot_ranking_version(snapshot) == RANKING_V2
            and AIDA in methods and IOU_BASELINE in methods):
        # v2의 기존 라벨 순서는 `1 − label_iou`라 기준선과 같은 신호다. 견주면 차이가 0에
        # 가깝게 나와 "AIDA가 기준선과 대등하다"로 읽힌다 (docs/adr-ranking-separation.md).
        raise ExportBlocked(
            f"이 묶음의 AIDA 순서({RANKING_V2})는 '{IOU_BASELINE}'과 같은 신호(1 − label_iou)입니다. "
            "같은 순서끼리 견주지 않습니다 — v2를 기준선과 견주려면 후보 생성까지 포함한 "
            "다른 평가가 필요합니다(docs/next-evaluation-proposal.md).")

    if any(m != AIDA for m in methods):
        truncated = _truncation(snapshot)
        if truncated:
            raise ExportBlocked(truncated)

    orders: dict[str, dict[str, float]] = {}
    # 모집단이 비어 "측정 불가"로 보고하는 방법 (사전 등록 4절, 사용자 결정 (a) 2026-09-29).
    # **누락 층(기술 통계)에서만** 허용한다 — 비교 층에서 모집단이 비면 그대로 막는다.
    not_measurable: list[str] = []
    for method in methods:
        order = method_order(included, method, snapshot_ranking_version(snapshot), scope)
        if order is None and scope == MISSING and method != AIDA:
            not_measurable.append(method)
            orders[method] = {}
            continue
        if order is None:
            raise ExportBlocked(
                f"'{method}'로 줄 세울 후보가 없습니다. AIDA는 후보마다 진단의 제품 "
                f"순위(`rank`)가 하나씩 있어야 하고, `{ALL_LABEL_IOU}`·"
                f"`{UNMATCHED_CONFIDENCE}`는 진단이 규칙 밖 모집단(`all_labels`·"
                "`unmatched_predictions`)을 적어 두었어야 합니다.")
        orders[method] = order

    if mode == WITHIN_AIDA:
        # 옛 규칙 그대로. 이 모드의 뜻이 "같은 후보 안의 재정렬"이라, 후보 집합이
        # 방법마다 다르면 정렬 효과가 아니라 작업 전체 효과가 된다.
        for method in methods:
            without = [c for c in included
                       if c.canonical_candidate_id not in orders[method]]
            if not without:
                continue
            no_label = [c for c in without if c.label_index is None]
            if no_label:
                raise ExportBlocked(
                    f"'{method}'가 누락 후보에 줄 점수가 정해지지 않았습니다 "
                    f"({len(no_label)}건). 임의 공식을 만들지 않습니다 — "
                    f"'{LABELLED}' 층으로 내보내거나 누락을 별도 층으로 보세요"
                    "(docs/evaluation-adjudication-design.md).")
            raise ExportBlocked(
                f"'{method}'의 점수가 없는 후보가 {len(without)}건 있습니다. "
                "후보 집합이 다르면 정렬 효과가 아니라 작업 전체 효과입니다.")

    by_id = {a.canonical_candidate_id: a for a in saved.adjudications}
    adjudications = []
    rankings = []
    for c in included:
        a = by_id.get(c.canonical_candidate_id)
        adjudications.append({
            "canonical_candidate_id": c.canonical_candidate_id,
            "image": c.image, "label_index": c.label_index,
            "suspicion": c.suspicion,
            "verdict": a.verdict if a else None,
            "unique_error_id": a.unique_error_id if a else None,
            "group_id": c.group_id,
            # 층별(상자 높이 등) 기술통계용. 판정이 끝난 뒤의 내보내기라 가림과 무관하다.
            "box": c.box,
            "complete": bool(a and a.verdict is not None),
            # 무엇의 성과로 셀 수 있는지가 여기서 갈린다. 무작위 표본은 방법 간
            # 비교가 아니라 "규칙이 놓친 비율"을 재는 별도 층이다.
            "source": c.source,
            "random_sample": c.random_sample,
            # 고정 재표본 합집합으로 더해진 후보인가. K 표본과 다르며 합치지 않는다.
            "coverage_extra": c.canonical_candidate_id in coverage_ids(snapshot),
        })
        for method in methods:
            order = orders[method]
            if c.canonical_candidate_id not in order:
                continue        # 그 방법의 모집단 밖 — 순서에 없다
            # `severity`는 집계가 줄 세우는 값이다. AIDA는 −순위라 음수다 —
            # 원래 점수는 `score`에 따로 둔다.
            row = {"method": method,
                   "canonical_candidate_id": c.canonical_candidate_id,
                   "severity": order[c.canonical_candidate_id],
                   "score": c.scores.get(method, order[c.canonical_candidate_id])}
            key = tie_key(snapshot.tie_seed, c.canonical_candidate_id)
            if key is not None:
                row["tie_key"] = key       # 집계가 그대로 쓴다 — 후보 선정과 같은 동점 순서
            rankings.append(row)

    # IoU 0 라벨 보고 (D9). 평가 범위 안의 기존 라벨 중 `label_iou`가 0인 것과, 그것이
    # `all_label_iou` 상위 N에 몇 건 드는지. 판정을 바꾸지 않는 기술 통계다.
    iou_zero = None
    if scope == LABELLED and ALL_LABEL_IOU in orders:
        zero_ids = {c.canonical_candidate_id for c in included
                    if c.scores.get(ALL_LABEL_IOU) is not None
                    and abs(c.scores[ALL_LABEL_IOU] - 1.0) < 1e-9}
        top = (_top(included, orders[ALL_LABEL_IOU], snapshot.judge_budget, snapshot.tie_seed)
               if snapshot.judge_budget else [])
        iou_zero = {"in_scope_labels": len(zero_ids),
                    "in_top_n_all_label_iou": sum(1 for i in top if i in zero_ids),
                    "n": snapshot.judge_budget,
                    "definition": "1 − label_iou == 1.0 (겹치는 예측이 없는 기존 라벨)"}

    reasons: dict[str, int] = {}
    for c in excluded:
        reason = _exclusion_reason(c, scope, mode)
        reasons[reason] = reasons.get(reason, 0) + 1

    limitation = _LIMITATION[scope]
    if mode == GENERATION_INCLUDED:
        limitation = (
            "후보 생성까지 포함한 비교입니다 — AIDA 규칙이 만들지 않은 라벨·예측도 "
            "모집단에 있습니다. 방법마다 모집단이 다르므로 `method_population`을 함께 "
            "읽으세요. " + limitation)

    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "evaluation_id": snapshot.evaluation_id,
        "dataset_id": snapshot.dataset_id,
        "snapshot_hash": snapshot.candidate_set_hash,
        # 어느 판정자의 원본으로 낸 내보내기인가. 1차 분석은 primary다.
        "adjudicator": saved.adjudicator,
        "auxiliary_sample": ({k: v for k, v in snapshot.auxiliary_sample.items() if k != "candidate_ids"}
                             if snapshot.auxiliary_sample else None),
        "methods": methods,
        # AIDA의 순서 근거. v1은 제품 순위(`aida_rank`), v2 기존 라벨 층은 점수 `1 − label_iou`
        # (동점 키 공유). 나머지 방법은 점수다.
        "order_basis": {m: (("product_rank" if not (snapshot_ranking_version(snapshot) == RANKING_V2
                                                    and scope == LABELLED)
                             else AIDA_V2_LABELLED_BASIS) if m == AIDA else "score")
                        for m in methods},
        # 동점 규칙 (D9). 씨앗이 있으면 각 순위 줄에 `tie_key`가 붙고 집계는 그것으로 자른다.
        "tie_seed": snapshot.tie_seed,
        "tie_break_rule": ("점수 → sha256(tie_seed:후보 id) → 이미지 → 후보 id"
                           if snapshot.tie_seed is not None else "점수 → 이미지 → 후보 id"),
        "iou_zero_labels": iou_zero,
        # 어느 순위 버전의 AIDA 순서인가. 집계가 버전이 다른 내보내기를 섞지 않게 한다.
        # 옛 묶음은 v1이고, 그 사실을 `ranking_version_recorded`로 따로 적는다.
        "ranking_version": snapshot_ranking_version(snapshot),
        "ranking_version_recorded": snapshot.ranking_version is not None,
        "candidate_pool": snapshot.candidate_pool,
        "total_in_diagnosis": snapshot.total_in_queue,
        "judge_budget": snapshot.judge_budget,
        "requested_scope": scope,
        # 어느 모집단을 잰 내보내기인가. 모드가 다르면 같은 방법 이름이라도 다른 질문이다.
        "comparison_mode": mode,
        "method_population": {m: len(orders[m]) for m in methods},
        # 누락 층에서 점수 붙은 후보가 하나도 없어 줄 세우지 못한 방법. 값을 지어내지 않고
        # 결과 문서에 "측정 불가"로 적는다 — cleanlab 기본 문턱을 낮추지 않는다.
        "not_measurable_methods": not_measurable,
        "random_sample": {
            "size": snapshot.random_sample_size,
            "seed": snapshot.random_sample_seed,
            "in_scope": sum(1 for c in included if c.random_sample),
            "definition": "AIDA 규칙 밖 기존 라벨의 단순 무작위 표본. 재표본 추가 후보와 합치지 않는다",
        },
        # 비교 예산과 연구용 총 판정량을 가른다. N은 방법별 상위 N이고, 총 판정량은
        # 상위 N 합집합 ∪ K ∪ 고정 재표본 추가 후보다.
        "judging": {
            "comparison_budget_n": snapshot.judge_budget,
            "total_judging_list": (len(judge_ids(snapshot)) if snapshot.judge_budget is not None else None),
            "coverage_extra_in_scope": sum(1 for c in included
                                           if c.canonical_candidate_id in coverage_ids(snapshot)),
        },
        "bootstrap_coverage": ({k: v for k, v in snapshot.bootstrap_coverage.items()
                                if k != "additional_candidate_ids"}
                               if snapshot.bootstrap_coverage else None),
        # 기존 라벨 층의 높이 필터 기록 (D2). 없으면 필터 없는 묶음이다.
        "label_height_filter": snapshot.label_height_filter,
        "total_candidates": len(snapshot.candidates),
        "included_candidates": len(included),
        "excluded_candidates": len(excluded),
        "exclusion_reasons": reasons,
        "comparison_allowed": comparison_allowed,
        "comparison_limitation": limitation,
        "descriptive_only": not comparison_allowed,
        "adjudications": adjudications,
        "rankings": rankings,
    }

# ── API ───────────────────────────────────────────────────────────────────────

class StartEvaluation(BaseModel):
    """평가를 시작한다. 지금 후보 목록을 얼린다."""
    evaluation_id: str
    shuffle_seed: int = 0
    # 판정할 상위 N건. 주면 두 방법 상위 N건의 합집합만 판정한다. 없으면 전부.
    judge_budget: int | None = None
    # 얼릴 AIDA 순서의 순위 버전. 그 버전의 진단 파일을 얼린다 (docs/adr-ranking-separation.md).
    ranking_version: str = RANKING_V1
    # 규칙 밖 기존 라벨에서 뽑을 무작위 표본 K와 그 씨앗 (docs/next-work-2026-09-15.md W3).
    # 후보 생성이 놓친 오류 비율을 재는 별도 층이다 — 방법 간 비교에 섞지 않는다.
    random_sample_size: int | None = None
    random_sample_seed: int | None = None
    # 기존 라벨 층의 높이 필터 (사전 등록 D2). 원본 픽셀 기준 이 값 미만의 기존 라벨 후보를
    # 평가 범위에서 뺀다. 누락 층에는 걸지 않는다. 없으면 필터 없음(옛 동작).
    min_label_height_px: float | None = None
    # 보조 판정 표본 (사전 등록 D8). 판정 대상의 이 비율을 씨앗으로 뽑아 두 번째 판정자에게 준다.
    auxiliary_sample_fraction: float | None = None
    auxiliary_sample_seed: int | None = None
    # 동점 씨앗 (사전 등록 D9). 없으면 옛 규칙(이미지·후보 id 순).
    tie_seed: int | None = None
    # 고정 재표본 합집합 (안 (a)). 최종 분석의 부트스트랩과 같은 반복 수·씨앗이어야 한다.
    coverage_iterations: int | None = None
    coverage_seed: int | None = None
    # 판정 화면의 묶음 나누기 (사전 등록 D5·D6). `{"version": "layer_bundles_v1", "labelled_bundles": k}`.
    # 없으면 묶음 없이 한 목록(옛 동작). 판정 대상·후보·점수·씨앗은 바꾸지 않는다.
    display_plan: dict | None = None


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
    if body.judge_budget is not None and body.judge_budget < 1:
        raise HTTPException(400, "판정 예산은 1 이상입니다.")
    path = eval_dir(dataset_id, body.evaluation_id) / SNAPSHOT_FILE
    if path.exists():
        raise HTTPException(409, "이미 있는 평가입니다. 묶음은 덮어쓰지 않습니다.")

    from .upload import _load_ruler_sidecar
    diagnosis = load_label_diagnosis(dataset_id, body.ranking_version)
    snapshot = build_snapshot(dataset_id, body.evaluation_id, diagnosis,
                              ruler=_load_ruler_sidecar(dataset_id, body.ranking_version),
                              shuffle_seed=body.shuffle_seed,
                              judge_budget=body.judge_budget,
                              ranking_version=body.ranking_version,
                              random_sample_size=body.random_sample_size,
                              random_sample_seed=body.random_sample_seed,
                              groups=load_groups(dataset_id),
                              min_label_height_px=body.min_label_height_px,
                              auxiliary_sample_fraction=body.auxiliary_sample_fraction,
                              auxiliary_sample_seed=body.auxiliary_sample_seed,
                              tie_seed=body.tie_seed,
                              coverage_iterations=body.coverage_iterations,
                              coverage_seed=body.coverage_seed,
                              display_plan=body.display_plan)
    save_snapshot(dataset_id, snapshot)
    return snapshot


@router.get("/{dataset_id}/evaluations/{evaluation_id}/queue",
            response_model=BlindQueue, response_model_exclude_unset=True)
def get_blind_queue(dataset_id: str, evaluation_id: str,
                    adjudicator: str = PRIMARY_ADJUDICATOR) -> BlindQueue:
    """가림 판정 목록. 점수·순위·진단 문구가 빠져 있다. `adjudicator`가 primary가 아니면
    보조 표본만, 그 판정자의 판정만 붙여 보낸다."""
    require_adjudicator(adjudicator)
    snapshot = load_snapshot(dataset_id, evaluation_id)
    saved = load_adjudications(dataset_id, evaluation_id,
                               snapshot.candidate_set_hash, adjudicator)
    return blind_queue(snapshot, saved, adjudicator)


@router.put("/{dataset_id}/evaluations/{evaluation_id}/adjudications",
            response_model=EvaluationAdjudications)
def put_adjudications(dataset_id: str, evaluation_id: str,
                      body: SaveAdjudications,
                      adjudicator: str = PRIMARY_ADJUDICATOR) -> EvaluationAdjudications:
    require_adjudicator(adjudicator)
    snapshot = load_snapshot(dataset_id, evaluation_id)
    if body.candidate_set_hash != snapshot.candidate_set_hash:
        raise HTTPException(
            409, "후보 목록이 그 사이에 바뀌었습니다. 판정을 저장하지 않습니다.")
    return save_adjudications(dataset_id, evaluation_id, snapshot,
                              body.adjudications, adjudicator)


@router.get("/{dataset_id}/evaluations/{evaluation_id}/agreement")
def get_agreement(dataset_id: str, evaluation_id: str,
                  secondary: str, primary: str = PRIMARY_ADJUDICATOR) -> dict:
    """보조 표본에서 두 판정자의 일치도 (D8). 양쪽 보류 수·일치율·κ와 그 분모를 낸다.

    **1차 분석을 바꾸지 않는다.** 이 수치는 공개용이고, 불일치 건의 `hold` 처리는 별도의
    사전 계획된 민감도 분석이다.
    """
    require_adjudicator(primary)
    require_adjudicator(secondary)
    if primary == secondary:
        raise HTTPException(400, "같은 판정자끼리 일치도를 낼 수 없습니다.")
    snapshot = load_snapshot(dataset_id, evaluation_id)
    sample = auxiliary_ids(snapshot)
    if sample is None:
        raise HTTPException(409, "이 묶음에는 보조 판정 표본이 없습니다.")
    a = load_adjudications(dataset_id, evaluation_id, snapshot.candidate_set_hash, primary)
    b = load_adjudications(dataset_id, evaluation_id, snapshot.candidate_set_hash, secondary)
    report = agreement_report(
        sorted(sample),
        {r.canonical_candidate_id: r.verdict for r in a.adjudications},
        {r.canonical_candidate_id: r.verdict for r in b.adjudications})
    return {"evaluation_id": evaluation_id, "primary": primary, "secondary": secondary,
            "damaged": {"primary": a.damaged, "secondary": b.damaged},
            "sample": {k: v for k, v in snapshot.auxiliary_sample.items() if k != "candidate_ids"},
            **report}


@router.get("/{dataset_id}/evaluations/{evaluation_id}/export")
def get_export(dataset_id: str, evaluation_id: str,
               methods: str = "aida", scope: str = LABELLED,
               mode: str = WITHIN_AIDA,
               adjudicator: str = PRIMARY_ADJUDICATOR) -> dict:
    """집계 모듈에 그대로 넣는 JSON.

    `methods`는 쉼표로 나눈다. `scope`는 평가 층이며 기본은 주 비교인
    `labelled_candidates`다. `mode`는 모집단이고 기본은 AIDA 후보 안의 재정렬
    (`within_aida_candidates`)이다 — 후보 생성까지 포함하려면
    `candidate_generation_included`로 요청한다.

    기준선을 넣었는데 점수가 없거나, 비교군이 없는 층에 기준선을 붙이거나, 모드에
    맞지 않는 방법을 요청하면 **거부한다.**
    """
    require_adjudicator(adjudicator)
    snapshot = load_snapshot(dataset_id, evaluation_id)
    saved = load_adjudications(dataset_id, evaluation_id,
                               snapshot.candidate_set_hash, adjudicator)
    try:
        return export_for_aggregation(
            snapshot, saved,
            [m.strip() for m in methods.split(",") if m.strip()], scope, mode)
    except ExportBlocked as exc:
        raise HTTPException(409, str(exc)) from exc


class ActivityEvents(BaseModel):
    """화면이 보내는 작업 기록 묶음."""
    candidate_set_hash: str
    events: list[dict] = []


# 아는 이벤트 이름. **모르는 이름을 받지 않는다** — 오타 하나가 조용히
# 파일에 들어가면 나중에 그 구간이 무엇이었는지 알 수 없다.
KNOWN_EVENTS = frozenset({
    "session_started", "session_ended",
    "queue_load_started", "queue_load_succeeded", "queue_load_failed",
    "candidate_opened", "verdict_set", "verdict_cleared",
    "missing_object_created", "missing_object_linked",
    "moved_previous", "moved_next",
    "save_started", "save_succeeded", "save_failed", "save_retried",
    "visibility_changed", "focus_changed",
})
# 후보를 가리켜야 하는 이벤트.
CANDIDATE_EVENTS = frozenset({
    "candidate_opened", "verdict_set", "verdict_cleared",
    "missing_object_created", "missing_object_linked",
})
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_META_BYTES = 2000
MAX_REQUEST_BYTES = 512 * 1024


def _reject(index: int, why: str):
    """**한 건이 잘못되면 요청 전체를 거부한다.**

    일부만 저장하면 기록에 구멍이 남는데, 화면은 성공으로 알고 다시 안 보낸다 —
    그 구멍은 순번으로만 드러나고 그때는 이미 늦다.
    """
    return HTTPException(400, f"{index}번째 이벤트가 규약을 어겼습니다: {why}")


def validate_events(events: list[dict], snapshot: EvaluationSnapshot) -> None:
    """이벤트가 규약을 지키는가 (docs/pilot-evaluation-plan.md)."""
    known_candidates = {c.canonical_candidate_id for c in snapshot.candidates}
    seen_ids: set[str] = set()

    for i, e in enumerate(events):
        if not isinstance(e, dict):
            raise _reject(i, "사전이 아닙니다.")

        name = e.get("event")
        if name not in KNOWN_EVENTS:
            raise _reject(i, f"모르는 이벤트 이름입니다: {name!r}")

        event_id = e.get("event_id")
        if not isinstance(event_id, str) or not ID_PATTERN.fullmatch(event_id):
            raise _reject(i, f"event_id 형식이 아닙니다: {event_id!r}")
        if event_id in seen_ids:
            raise _reject(i, f"한 요청 안에 같은 event_id가 두 번: {event_id}")
        seen_ids.add(event_id)

        session_id = e.get("session_id")
        if not isinstance(session_id, str) or not ID_PATTERN.fullmatch(session_id):
            raise _reject(i, f"session_id 형식이 아닙니다: {session_id!r}")

        sequence = e.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
            raise _reject(i, f"sequence는 0 이상의 정수입니다: {sequence!r}")

        elapsed = e.get("elapsed_ms")
        if (not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool)
                or not math.isfinite(elapsed) or elapsed < 0):
            raise _reject(i, f"elapsed_ms는 0 이상의 유한한 수입니다: {elapsed!r}")

        at = e.get("at")
        if not isinstance(at, str):
            raise _reject(i, "at이 없습니다.")
        try:
            datetime.fromisoformat(at.replace("Z", "+00:00"))
        except ValueError:
            raise _reject(i, f"at을 읽을 수 없습니다: {at!r}") from None

        meta = e.get("meta", {})
        if not isinstance(meta, dict):
            raise _reject(i, "meta가 사전이 아닙니다.")
        if len(json.dumps(meta, ensure_ascii=False).encode("utf-8")) > MAX_META_BYTES:
            raise _reject(i, f"meta가 {MAX_META_BYTES}바이트를 넘습니다.")

        cid = e.get("canonical_candidate_id")
        if name in CANDIDATE_EVENTS:
            # **얼린 목록에 없는 후보의 시간은 어디에도 못 붙인다.**
            if cid not in known_candidates:
                raise _reject(i, f"이 묶음에 없는 후보입니다: {cid!r}")
        elif cid is not None and cid not in known_candidates:
            raise _reject(i, f"이 묶음에 없는 후보입니다: {cid!r}")

        if name == "visibility_changed" and not isinstance(meta.get("visible"), bool):
            raise _reject(i, "visibility_changed에는 visible(참·거짓)이 필요합니다.")
        if name == "focus_changed" and not isinstance(meta.get("focused"), bool):
            raise _reject(i, "focus_changed에는 focused(참·거짓)이 필요합니다.")
        if name == "verdict_set" and meta.get("verdict") not in VALID_VERDICTS:
            raise _reject(i, f"알 수 없는 판정입니다: {meta.get('verdict')!r}")


def _stored_event_ids(path: Path) -> set[str]:
    """이미 저장된 `event_id`들. 파일이 없으면 빈 집합.

    깨진 줄은 여기서 넘긴다 — 중복을 가려내려는 것이지 파일을 검증하는
    자리가 아니고, 읽기가 실패해서 **중복이 다시 들어가는 쪽이 더 나쁘다.**
    깨진 줄은 요약 모듈이 읽을 때 드러난다.
    """
    if not path.exists():
        return set()
    ids: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ids.add(json.loads(line).get("event_id"))
            except ValueError:
                continue
    except OSError:
        return set()
    return ids - {None}


@router.post("/{dataset_id}/evaluations/{evaluation_id}/activity")
def append_activity(dataset_id: str, evaluation_id: str,
                    body: ActivityEvents) -> dict:
    """작업 기록을 **이어붙인다.**

    덮어쓰지 않는다 — 기록은 지난 일이라 나중 것이 앞의 것을 무효로 만들지
    않는다. 이어붙이기만 하므로 중간이 깨져도 앞부분이 남는다.

    **판정 파일과 섞지 않는다.** 판정은 지금의 사실이고 기록은 지나간 사실이라,
    한 파일에 두면 판정을 고칠 때마다 기록까지 다시 써야 한다.

    **이미 받은 `event_id`는 다시 넣지 않는다.** 응답이 유실되면 화면이 같은
    묶음을 다시 보내는데, 그때 두 벌이 남으면 판정 횟수가 부풀고 순번이 겹쳐
    그 세션이 손상으로 잡힌다. 몇 건을 걸렀는지 응답에 적는다.

    묶음이 다르면 받지 않는다 — 다른 후보 목록에서 잰 시간이다.
    """
    snapshot = load_snapshot(dataset_id, evaluation_id)
    if body.candidate_set_hash != snapshot.candidate_set_hash:
        raise HTTPException(
            409, "후보 목록이 그 사이에 바뀌었습니다. 다른 목록에서 잰 시간이라 "
                 "기록하지 않습니다.")
    if len(body.events) > MAX_EVENTS_PER_REQUEST:
        raise HTTPException(
            413, f"한 번에 {MAX_EVENTS_PER_REQUEST}건까지 받습니다 "
                 f"(받은 것 {len(body.events)}건).")
    size = len(json.dumps(body.events, ensure_ascii=False).encode("utf-8"))
    if size > MAX_REQUEST_BYTES:
        raise HTTPException(
            413, f"요청이 {MAX_REQUEST_BYTES}바이트를 넘습니다 ({size}).")

    # **먼저 전부 검사한다.** 쓰다가 멈추면 기록에 구멍이 남는다.
    validate_events(body.events, snapshot)

    path = eval_dir(dataset_id, evaluation_id) / ACTIVITY_FILE
    already = _stored_event_ids(path)
    lines = []
    deduplicated = 0
    for raw in body.events:
        if raw["event_id"] in already:
            deduplicated += 1
            continue
        already.add(raw["event_id"])
        # 서버가 아는 것은 서버가 채운다. 화면이 보낸 값을 그대로 믿지 않는다.
        lines.append(json.dumps({
            **raw,
            "event_schema_version": EVENT_SCHEMA_VERSION,
            "evaluation_id": evaluation_id,
            "candidate_set_hash": snapshot.candidate_set_hash,
        }, ensure_ascii=False))

    if lines:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write("".join(line + chr(10) for line in lines))
        except OSError as exc:
            raise HTTPException(500, f"기록을 남기지 못했습니다: {exc}") from exc

    # **받은 것 전부를 확인해 준다.** 걸러낸 것도 이미 저장돼 있으므로 화면은
    # 로컬 큐에서 지워도 된다 — 안 그러면 영영 다시 보낸다.
    return {"appended": len(lines), "deduplicated": deduplicated,
            "acknowledged": [e["event_id"] for e in body.events]}
