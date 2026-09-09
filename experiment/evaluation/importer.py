"""판정 화면이 내보낸 JSON을 집계 입력으로 바꾼다.

집계 모듈은 `Adjudication`과 `Ranking`을 **받기만 한다.** 그것을 만드는 쪽은
백엔드의 평가 라우터다(`docs/evaluation-adjudication-design.md`). 이 파일이 그
둘 사이의 유일한 연결점이다.

**여기서 값을 지어내지 않는다.** 빠진 것은 빠졌다고 말하고 멈춘다 — 어댑터가
조용히 기본값을 채우면 집계가 검증한 규약이 무의미해진다.
"""
from .schema import (Adjudication, Ranking, ValidationError,
                     validate_adjudications, validate_rankings)

# 내보내기 형식의 판. 백엔드의 `EVALUATION_SCHEMA_VERSION`과 같은 값이다.
SUPPORTED_EXPORT_VERSION = 1


def _require(data: dict, field: str):
    if field not in data:
        raise ValidationError(f"내보내기에 {field}가 없다")
    return data[field]


def load_export(export: dict, dataset_id: str | None = None
                ) -> tuple[list[Adjudication], list[Ranking]]:
    """내보내기 JSON → (사실, 점수).

    `dataset_id`를 주면 그 이름으로 덮어쓴다. 여러 데이터셋을 한 번에 집계할 때
    업로드 id 대신 읽을 수 있는 이름을 쓰려는 것이다. **안 주면 내보내기에 적힌
    것을 그대로 쓴다** — 어댑터가 이름을 지어내면 묶음 경계가 어긋난다.

    `group_id`는 연속 장면 묶음이다. 없으면 이미지 하나가 곧 묶음이다.
    """
    version = _require(export, "schema_version")
    if version != SUPPORTED_EXPORT_VERSION:
        # 모양이 바뀐 파일을 옛 규칙으로 읽으면 조용히 다른 것을 센다.
        raise ValidationError(
            f"모르는 내보내기 판이다: {version} "
            f"(이 코드가 아는 것은 {SUPPORTED_EXPORT_VERSION})")

    name = dataset_id or _require(export, "dataset_id")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(f"dataset_id가 비어 있다: {name!r}")

    adjudications = []
    for row in _require(export, "adjudications"):
        adjudications.append(Adjudication(
            dataset_id=name,
            image_id=_require(row, "image"),
            candidate_id=_require(row, "canonical_candidate_id"),
            suspicion=row.get("suspicion", ""),
            verdict=row.get("verdict"),
            label_index=row.get("label_index"),
            unique_error_id=row.get("unique_error_id"),
            group_id=row.get("group_id"),
        ))

    # 순위는 후보 **키**에 붙는다. 내보내기는 후보 id만 적으므로 여기서 잇는다.
    key_of = {a.candidate_id: a.key for a in adjudications}
    rankings = []
    for row in _require(export, "rankings"):
        cid = _require(row, "canonical_candidate_id")
        if cid not in key_of:
            raise ValidationError(f"판정에 없는 후보에 점수가 붙었다: {cid}")
        rankings.append(Ranking(method=_require(row, "method"),
                                candidate_key=key_of[cid],
                                severity=float(_require(row, "severity"))))

    validate_adjudications(adjudications)
    validate_rankings(rankings, {a.key for a in adjudications})
    return adjudications, rankings


def load_exports(exports: list[dict], names: list[str] | None = None
                 ) -> tuple[list[Adjudication], list[Ranking]]:
    """여러 평가를 합친다. **데이터셋 이름이 겹치면 거부한다.**

    같은 이름으로 두 번 들어오면 서로 다른 데이터셋의 묶음이 한 묶음으로
    합쳐져 재표집 단위가 틀린다(docs/evaluation-protocol.md).
    """
    if names is not None and len(names) != len(exports):
        raise ValidationError(
            f"이름 수가 내보내기 수와 다르다: {len(names)} vs {len(exports)}")

    all_adjudications: list[Adjudication] = []
    all_rankings: list[Ranking] = []
    seen: set[str] = set()
    for i, export in enumerate(exports):
        name = names[i] if names else export.get("dataset_id")
        adjudications, rankings = load_export(export, name)
        actual = adjudications[0].dataset_id if adjudications else name
        if actual in seen:
            raise ValidationError(f"데이터셋 이름이 겹친다: {actual}")
        seen.add(actual)
        all_adjudications += adjudications
        all_rankings += rankings

    validate_adjudications(all_adjudications)
    validate_rankings(all_rankings, {a.key for a in all_adjudications})
    return all_adjudications, all_rankings
