"""판정 화면의 묶음 나누기 (사전 등록 D5·D6, 2026-10-07 개정 5).

묶음 표시 계획은 **화면의 순서와 경계만** 정한다. 판정 대상·후보·점수·씨앗·보조 표본은 그대로이고,
각 층 안의 상대 순서는 씨앗으로 섞인 가림 순서 그대로다. 계획이 없는 옛 묶음(practice1·qa1)은 지문도
응답 모양도 예전 그대로여야 한다.
"""
import json
import random

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import EvaluationAdjudications
from app.routers import evaluation as E
from app.routers import upload

DATASET = "0123456789ab"
PLAN = {"version": "layer_bundles_v1", "labelled_bundles": 3}
OLD_FIELDS = {"canonical_candidate_id", "image", "label_index", "box", "class_name",
              "verdict", "unique_error_id"}


def world(n_images=12, labels_per_image=3, preds_per_image=2) -> dict:
    """AIDA 후보 몇 개 + 모든 라벨 + 미매칭 예측. 점수는 씨앗으로 고정한 난수."""
    rnd = random.Random(5)
    aida, labels, preds = [], [], []
    rank = 1
    for i in range(n_images):
        image = f"img{i:02d}.jpg"
        for j in range(labels_per_image):
            box = [10.0 + j * 50, 10.0, 50.0 + j * 50, 80.0]
            iou = round(rnd.random(), 3)
            labels.append({"image": image, "label_index": j, "box": box, "label_iou": iou,
                           "objectlab_score": round(rnd.random(), 3), "class_name": "Car"})
            if j == 0 and i % 2 == 0:
                aida.append({"rank": rank, "image": image, "label_index": j, "suspicion": "width",
                             "severity": round(1 - iou, 3), "detail": "", "box": box,
                             "label_iou": iou, "class_name": "Car"})
                rank += 1
        for k in range(preds_per_image):
            box = [300.0 + k * 40, 20.0, 330.0 + k * 40, 90.0]
            preds.append({"image": image, "label_index": None, "box": box,
                          "confidence": round(rnd.random(), 3), "covered_ratio": 0.0,
                          "class_name": "Car"})
            if k == 0 and i % 3 == 0:
                aida.append({"rank": rank, "image": image, "label_index": None,
                             "suspicion": "missing", "severity": 0.5, "detail": "", "box": box,
                             "class_name": "Car"})
                rank += 1
    return {"dataset": DATASET, "generated_at": "2026-10-07T00:00:00+00:00", "summary": {},
            "caveat": "", "review_queue": aida, "all_candidates": aida,
            "total_in_queue": len(aida), "all_labels": labels, "unmatched_predictions": preds}


SETTINGS = dict(judge_budget=6, shuffle_seed=11, random_sample_size=4, random_sample_seed=12,
                tie_seed=13, auxiliary_sample_fraction=0.3, auxiliary_sample_seed=14)


def build(display_plan=None, evaluation_id="e1", **over):
    return E.build_snapshot(DATASET, evaluation_id, world(), **{**SETTINGS, **over},
                            display_plan=display_plan)


def empty(snapshot):
    return EvaluationAdjudications(evaluation_id=snapshot.evaluation_id,
                                   candidate_set_hash=snapshot.candidate_set_hash)


def queue_ids(q):
    return [c.canonical_candidate_id for c in q.candidates]


# ── 계획 자체 ────────────────────────────────────────────────────────────────

def test_같은_입력이면_같은_계획과_지문이다():
    a, b = build(PLAN), build(PLAN)
    assert a.display_plan == b.display_plan
    assert a.candidate_set_hash == b.candidate_set_hash


def test_판정_대상은_정확히_한_묶음에만_든다():
    snap = build(PLAN)
    planned = [cid for bundle in snap.display_plan["bundles"] for cid in bundle["candidate_ids"]]
    assert len(planned) == len(set(planned))
    assert set(planned) == E.judge_ids(snap)


def test_층_안의_상대_순서는_계획_없는_가림_순서_그대로다():
    with_plan, without = build(PLAN), build(None)
    old = E.blind_queue(without, empty(without))
    labelled_old = [c.canonical_candidate_id for c in old.candidates if c.label_index is not None]
    missing_old = [c.canonical_candidate_id for c in old.candidates if c.label_index is None]
    bundles = with_plan.display_plan["bundles"]
    labelled_new = [cid for b in bundles if b["layer"] == "labelled_candidates"
                    for cid in b["candidate_ids"]]
    missing_new = [cid for b in bundles if b["layer"] == "missing_candidates"
                   for cid in b["candidate_ids"]]
    assert labelled_new == labelled_old and missing_new == missing_old
    # 화면 목록은 기존 라벨 묶음들 → 누락 묶음 순이다.
    new = E.blind_queue(with_plan, empty(with_plan))
    assert queue_ids(new) == labelled_new + missing_new


def test_기존_라벨은_고르게_나누고_누락은_뒤에_한_묶음이다():
    snap = build(PLAN)
    plan = snap.display_plan
    n_lab = plan["layer_sizes"]["labelled_candidates"]
    n_mis = plan["layer_sizes"]["missing_candidates"]
    base, extra = divmod(n_lab, 3)
    assert plan["bundle_sizes"] == [base + (i < extra) for i in range(3)] + [n_mis]
    assert [b["layer"] for b in plan["bundles"]] == ["labelled_candidates"] * 3 + ["missing_candidates"]


def test_qa1_모양_384건_넷과_90건_하나():
    """예산 없는 묶음(판정 대상 = 전부)으로 실제 qa1b와 같은 층 크기를 만든다."""
    labels = [{"image": f"i{i:03d}.jpg", "label_index": 0, "box": [0.0, 0.0, 40.0, 40.0 + i % 7],
               "label_iou": (i % 97) / 100, "class_name": "Car"} for i in range(384)]
    preds = [{"image": f"p{i:03d}.jpg", "label_index": None, "box": [5.0, 5.0, 30.0, 30.0],
              "confidence": (i % 89) / 100, "covered_ratio": 0.0, "class_name": "Car"}
             for i in range(90)]
    diag = {"dataset": DATASET, "generated_at": "x", "summary": {}, "caveat": "",
            "review_queue": [], "all_candidates": [], "total_in_queue": 0,
            "all_labels": labels, "unmatched_predictions": preds}
    snap = E.build_snapshot(DATASET, "q", diag, shuffle_seed=20260927,
                            display_plan={"version": "layer_bundles_v1", "labelled_bundles": 4})
    assert snap.display_plan["bundle_sizes"] == [96, 96, 96, 96, 90]
    q = E.blind_queue(snap, empty(snap))
    assert [(b.layer, b.layer_bundle, b.layer_bundles, b.size) for b in q.bundles] == [
        ("labelled_candidates", 1, 4, 96), ("labelled_candidates", 2, 4, 96),
        ("labelled_candidates", 3, 4, 96), ("labelled_candidates", 4, 4, 96),
        ("missing_candidates", 1, 1, 90)]
    assert [c.bundle for c in q.candidates] == [0] * 96 + [1] * 96 + [2] * 96 + [3] * 96 + [4] * 90


def test_묶음은_층과_위치로만_정해지고_표본_여부와_무관하다():
    """계획을 섞인 순서·층만으로 다시 만들어 같은지 본다 — 출처·무작위 표본·보조 표본을 안 본다."""
    snap = build(PLAN)
    order = E._shuffled_ids(snap, E.judge_ids(snap))
    layer = {c.canonical_candidate_id: c.label_index is not None for c in snap.candidates}
    lab = [cid for cid in order if layer[cid]]
    mis = [cid for cid in order if not layer[cid]]
    base, extra = divmod(len(lab), 3)
    sizes = [base + (i < extra) for i in range(3)]
    expected, at = [], 0
    for s in sizes:
        expected.append(lab[at:at + s])
        at += s
    expected.append(mis)
    assert [b["candidate_ids"] for b in snap.display_plan["bundles"]] == expected
    # 무작위 표본을 다른 씨앗으로 뽑아도 같은 판정 대상이면 같은 자리에 같은 묶음이 붙는다
    # (표본 표시는 계획 재료가 아니다).
    material = json.dumps(E.display_plan_fingerprint(snap.display_plan))
    assert "random_sample" not in material and "source" not in material and "score" not in material


# ── 지문 ─────────────────────────────────────────────────────────────────────

def test_계획은_지문을_바꾸고_내용_지문은_같다():
    without, with_plan = build(None), build(PLAN)
    assert with_plan.candidate_set_hash != without.candidate_set_hash
    assert E.content_hash(with_plan) == without.candidate_set_hash
    assert E.content_hash(without) == without.candidate_set_hash
    other = build({"version": "layer_bundles_v1", "labelled_bundles": 2})
    assert other.candidate_set_hash != with_plan.candidate_set_hash
    assert E.content_hash(other) == without.candidate_set_hash


def test_계획이_없으면_지문_재료가_예전과_같다():
    """옛 묶음의 지문이 그대로여야 판정이 떨어지지 않는다 — 재료에 계획 키가 생기지 않는다."""
    snap = build(None)
    payload = E.snapshot_payload(snap)
    assert "display_plan" not in payload
    assert E.candidate_set_hash(payload) == snap.candidate_set_hash


def test_후보_점수_보조표본_재표본은_계획과_무관하다():
    a, b = build(None, coverage_iterations=50, coverage_seed=3), build(PLAN, coverage_iterations=50,
                                                                        coverage_seed=3)
    assert [c.model_dump() for c in a.candidates] == [c.model_dump() for c in b.candidates]
    assert a.auxiliary_sample == b.auxiliary_sample
    assert a.bootstrap_coverage == b.bootstrap_coverage
    assert E.judge_ids(a) == E.judge_ids(b)


# ── 요청 검사 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    {"version": "other", "labelled_bundles": 3},
    {"version": "layer_bundles_v1"},
    {"version": "layer_bundles_v1", "labelled_bundles": 0},
    {"version": "layer_bundles_v1", "labelled_bundles": True},
    {"version": "layer_bundles_v1", "labelled_bundles": 3, "missing_bundles": 2},
    {"version": "layer_bundles_v1", "labelled_bundles": 10_000},
])
def test_잘못된_계획은_거부한다(bad):
    with pytest.raises(E.HTTPException) as err:
        build(bad)
    assert err.value.status_code == 400


def test_저장된_계획이_판정_목록과_다르면_목록을_내지_않는다():
    snap = build(PLAN)
    broken = json.loads(json.dumps(snap.display_plan))
    broken["bundles"][0]["candidate_ids"].pop()
    tampered = snap.model_copy(update={"display_plan": broken})
    with pytest.raises(E.HTTPException) as err:
        E.blind_queue(tampered, empty(tampered))
    assert err.value.status_code == 500


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    monkeypatch.setattr(E, "UPLOADS_DIR", root)
    monkeypatch.setattr(upload, "UPLOADS_DIR", root)
    (root / DATASET).mkdir(parents=True)
    (root / DATASET / "label_diagnosis.json").write_text(json.dumps(world()), encoding="utf-8")
    return TestClient(app)


def start(client, evaluation_id, **body):
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": evaluation_id, **SETTINGS, **body})
    assert r.status_code == 200, r.text
    return r.json()


def test_계획이_없는_묶음의_목록_응답은_예전_모양이다(client):
    start(client, "old")
    q = client.get(f"/api/datasets/{DATASET}/evaluations/old/queue").json()
    assert "bundles" not in q
    assert q["candidates"] and all(set(item) == OLD_FIELDS for item in q["candidates"])


def test_계획이_있으면_목록에_묶음_자리와_묶음_표가_실린다(client):
    snap = start(client, "new", display_plan=PLAN)
    assert snap["display_plan"]["bundle_sizes"][-1] == snap["display_plan"]["layer_sizes"]["missing_candidates"]
    q = client.get(f"/api/datasets/{DATASET}/evaluations/new/queue").json()
    assert all(set(item) == OLD_FIELDS | {"bundle"} for item in q["candidates"])
    assert [b["layer"] for b in q["bundles"]] == ["labelled_candidates"] * 3 + ["missing_candidates"]
    bundle_seq = [item["bundle"] for item in q["candidates"]]
    assert bundle_seq == sorted(bundle_seq)
    # 누락 묶음의 후보는 전부 누락 층, 기존 라벨 묶음은 전부 기존 라벨 층.
    for item in q["candidates"]:
        assert (item["label_index"] is None) == (q["bundles"][item["bundle"]]["layer"] == "missing_candidates")


def test_계획이_있어도_판정_저장과_보조_판정자_목록은_그대로다(client):
    snap = start(client, "new", display_plan=PLAN)
    q = client.get(f"/api/datasets/{DATASET}/evaluations/new/queue").json()
    first = q["candidates"][0]["canonical_candidate_id"]
    r = client.put(f"/api/datasets/{DATASET}/evaluations/new/adjudications",
                   json={"candidate_set_hash": snap["candidate_set_hash"],
                         "adjudications": [{"canonical_candidate_id": first, "verdict": "miss"}]})
    assert r.status_code == 200, r.text
    again = client.get(f"/api/datasets/{DATASET}/evaluations/new/queue").json()
    assert again["candidates"][0]["verdict"] == "miss"
    assert [c["canonical_candidate_id"] for c in again["candidates"]] == \
        [c["canonical_candidate_id"] for c in q["candidates"]]
    # 보조 판정자는 보조 표본만, 묶음 없이 본다.
    aux = client.get(f"/api/datasets/{DATASET}/evaluations/new/queue?adjudicator=primary_retest").json()
    assert "bundles" not in aux
    assert {c["canonical_candidate_id"] for c in aux["candidates"]} == \
        set(snap["auxiliary_sample"]["candidate_ids"])
    assert all(set(item) == OLD_FIELDS for item in aux["candidates"])
