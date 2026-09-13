"""두 방법 비교가 **무엇을 모집단으로, 어떤 순서로** 재는가.

주 비교는 "AIDA가 만든 동일 후보 집합 안에서의 조건부 재정렬 효과"다
(docs/evaluation-adjudication-design.md). 그 비교가 성립하려면 셋이 맞아야 한다.

1. **AIDA 순서는 제품이 보여준 순서다.** 진단의 `rank`(계통적 유형 먼저, 그
   안에서 심각도)이지 심각도 한 값이 아니다. 심각도로 다시 줄 세우면 제품이
   안 쓰는 순서를 평가하게 된다(docs/21 AN).
2. **후보 집합은 잘리기 전 전부다.** `review_queue`는 AIDA 순위 상위 N건이라,
   그것만 얼리면 기준선이 AIDA 하위 후보를 끌어올릴 기회가 없다.
3. **판정은 두 방법 상위 N건의 합집합만** 한다. 겹치는 후보는 한 번만 본다.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import evaluation, upload

DATASET = "0123456789ab"


def row(rank, image, label_index, suspicion, severity, label_iou=None):
    out = {"rank": rank, "image": image, "label_index": label_index,
           "suspicion": suspicion, "severity": severity, "detail": "",
           "box": [10.0 + rank, 10.0, 60.0 + rank, 60.0]}
    if label_iou is not None:
        out["label_iou"] = label_iou
    return out


def diagnosis(queue, all_candidates=None, total=None) -> dict:
    data = {"dataset_id": DATASET, "generated_at": "2026-09-13T00:00:00+00:00",
            "summary": {}, "caveat": "", "review_queue": queue,
            "total_in_queue": total if total is not None else len(queue)}
    if all_candidates is not None:
        data["all_candidates"] = all_candidates
    return data


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    monkeypatch.setattr(evaluation, "UPLOADS_DIR", root)
    monkeypatch.setattr(upload, "UPLOADS_DIR", root)
    (root / DATASET).mkdir(parents=True)
    return root


@pytest.fixture
def client(uploads):
    return TestClient(app)


def write(uploads, data):
    import json
    (uploads / DATASET / "label_diagnosis.json").write_text(
        json.dumps(data), encoding="utf-8")


def start(client, **body):
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": "e1", **body})
    assert r.status_code == 200, r.text
    return r.json()


def put(client, snap, rows):
    return client.put(
        f"/api/datasets/{DATASET}/evaluations/e1/adjudications",
        json={"candidate_set_hash": snap["candidate_set_hash"],
              "adjudications": rows})


def export(client, methods):
    return client.get(f"/api/datasets/{DATASET}/evaluations/e1/export"
                      f"?methods={methods}")


def by_image(snap):
    return {c["image"]: c["canonical_candidate_id"] for c in snap["candidates"]}


# ── 1. AIDA 순서 ─────────────────────────────────────────────────────────────

def test_AIDA_순위는_심각도가_아니라_제품이_보여준_순서다(client, uploads):
    """계통적 유형(width)이 1위, 심각도가 더 높은 잡음 유형이 2위인 진단.

    제품 화면은 1위를 먼저 보여준다. 평가가 심각도로 다시 줄 세우면 예산 1건에서
    **제품이 안 보여준 후보**를 AIDA의 선택으로 센다.
    """
    queue = [row(1, "a.jpg", 0, "width", 0.82, 0.5),
             row(2, "b.jpg", 0, "class_mismatch", 0.99, 0.5)]
    write(uploads, diagnosis(queue))
    snap = start(client)
    ids = by_image(snap)
    assert put(client, snap, [
        {"canonical_candidate_id": ids["a.jpg"], "verdict": "hit"},
        {"canonical_candidate_id": ids["b.jpg"], "verdict": "miss"},
    ]).status_code == 200

    from evaluation.importer import load_export
    from evaluation.summary import summarise
    adjudications, rankings = load_export(export(client, "aida").json())
    got = summarise(adjudications, rankings, "aida", budget=1)
    assert got.unique_error_yield == 1


def test_제품_순위가_없거나_겹치면_AIDA_순서를_지어내지_않는다(client, uploads):
    queue = [row(1, "a.jpg", 0, "width", 0.9, 0.5),
             row(1, "b.jpg", 0, "width", 0.8, 0.5)]
    write(uploads, diagnosis(queue))
    start(client)
    assert export(client, "aida").status_code == 409


# ── 2. 잘리기 전 전부 ────────────────────────────────────────────────────────

def test_잘리기_전_후보_전체를_얼린다(client, uploads):
    full = [row(1, "a.jpg", 0, "width", 0.9, 0.9),
            row(2, "b.jpg", 0, "width", 0.8, 0.8),
            row(3, "c.jpg", 0, "width", 0.7, 0.1)]
    write(uploads, diagnosis(full[:1], all_candidates=full, total=3))
    snap = start(client)
    assert len(snap["candidates"]) == 3
    assert snap["candidate_pool"] == "all_candidates"


def test_잘린_목록만_있는_옛_진단은_두_방법_비교를_막는다(client, uploads):
    """기준선 상위 후보가 잘린 쪽에 있을 수 있다. 그대로 견주면 AIDA에 유리하다."""
    queue = [row(1, "a.jpg", 0, "width", 0.9, 0.9)]
    write(uploads, diagnosis(queue, total=3))
    snap = start(client)
    assert snap["candidate_pool"] == "review_queue"
    r = export(client, "aida,iou_baseline")
    assert r.status_code == 409
    assert "잘린" in r.json()["detail"]


def test_잘리지_않은_옛_진단은_비교할_수_있다(client, uploads):
    """`review_queue`가 전부를 담았다면 잘린 것이 아니다."""
    queue = [row(1, "a.jpg", 0, "width", 0.9, 0.9),
             row(2, "b.jpg", 0, "width", 0.8, 0.1)]
    write(uploads, diagnosis(queue, total=2))
    start(client)
    assert export(client, "aida,iou_baseline").status_code == 200


# ── 3. 상위 N 합집합만 판정 ──────────────────────────────────────────────────

def _pool():
    """기존 라벨 넷 + 누락 하나.

    | 후보 | AIDA 순위 | 기준선 점수(1−IoU) |
    |---|---|---|
    | A | 1 | 0.9 |
    | B | 2 | 0.1 |
    | C | 3 | 0.8 |
    | D | 4 | 0.05 |
    | E(누락) | 5 | — |

    N=2 → AIDA {A, B}, 기준선 {A, C} → 합집합 {A, B, C}. 누락 층은 AIDA만
    있으므로 {E}.
    """
    return [row(1, "A.jpg", 0, "width", 0.9, 0.1),
            row(2, "B.jpg", 0, "width", 0.8, 0.9),
            row(3, "C.jpg", 0, "width", 0.7, 0.2),
            row(4, "D.jpg", 0, "width", 0.6, 0.95),
            row(5, "E.jpg", None, "missing", 0.5)]


def test_판정_예산을_주면_두_방법_상위_N의_합집합만_판정한다(client, uploads):
    write(uploads, diagnosis(_pool()[:1], all_candidates=_pool(), total=5))
    snap = start(client, judge_budget=2)
    assert snap["judge_budget"] == 2

    queue = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").json()
    images = sorted(c["image"] for c in queue["candidates"])
    # A는 두 방법이 모두 골랐지만 **한 번만** 나온다.
    assert images == ["A.jpg", "B.jpg", "C.jpg", "E.jpg"]


def test_판정_대상_밖의_후보에는_판정을_저장하지_않는다(client, uploads):
    write(uploads, diagnosis(_pool()[:1], all_candidates=_pool(), total=5))
    snap = start(client, judge_budget=2)
    ids = by_image(snap)
    r = put(client, snap, [{"canonical_candidate_id": ids["D.jpg"],
                            "verdict": "miss"}])
    assert r.status_code == 400


def test_예산_안에서는_두_방법_모두_판정이_빠지지_않는다(client, uploads):
    write(uploads, diagnosis(_pool()[:1], all_candidates=_pool(), total=5))
    snap = start(client, judge_budget=2)
    ids = by_image(snap)
    verdicts = {"A.jpg": "hit", "B.jpg": "miss", "C.jpg": "hit"}
    assert put(client, snap, [{"canonical_candidate_id": ids[k], "verdict": v}
                              for k, v in verdicts.items()]).status_code == 200

    got = export(client, "aida,iou_baseline").json()
    assert got["judge_budget"] == 2

    from evaluation.importer import load_export
    from evaluation.summary import summarise
    adjudications, rankings = load_export(got, require_comparison=True)
    aida = summarise(adjudications, rankings, "aida", budget=2)
    base = summarise(adjudications, rankings, "iou_baseline", budget=2)
    assert (aida.in_budget, aida.judged, aida.unique_error_yield) == (2, 2, 1)
    assert (base.in_budget, base.judged, base.unique_error_yield) == (2, 2, 2)


def test_판정_예산이_0_이하면_거부한다(client, uploads):
    write(uploads, diagnosis(_pool()[:1], all_candidates=_pool(), total=5))
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": "e1", "judge_budget": 0})
    assert r.status_code == 400
