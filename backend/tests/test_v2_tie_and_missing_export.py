"""Codex 정적 검토(68d0d18) 반영.

1. v2 기존 라벨 층에서 AIDA의 평가 순서는 `1 − label_iou`이고 `tie_key`가 실제로 작동한다 —
   선정·내보내기·집계가 같은 순서를 본다. v1과 누락 층은 제품 순위 그대로다.
2. 누락 층은 등록된 세 방법을 기술 통계용으로 내보낼 수 있고 집계까지 이어진다.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import evaluation as E
from app.routers import upload

sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "experiment"))
from evaluation.importer import load_export  # noqa: E402
from evaluation.ranking import top_n  # noqa: E402
from evaluation.summary import summarise  # noqa: E402

DATASET = "0123456789ab"
V1 = "aida_v1_systematic_boost"
V2 = "aida_v2_candidate_iou"
IMAGES = ["a.png", "b.png", "c.png", "d.png", "e.png", "f.png"]


def diagnosis(version: str) -> dict:
    # AIDA 기존 라벨 후보 6건, label_iou 전부 0.5(동점). 제품 순위는 이미지 이름순.
    aida = [{"rank": i + 1, "image": im, "label_index": 0, "suspicion": "width", "severity": 0.9,
             "detail": "", "box": [0.0, 0.0, 50.0, 50.0], "label_iou": 0.5}
            for i, im in enumerate(IMAGES)]
    # 누락 층 AIDA 후보 1건 — 첫 미매칭 예측과 같은 상자라 모집단과 이어진다
    aida.append({"rank": 7, "image": "a.png", "label_index": None, "suspicion": "missing",
                 "severity": 0.8, "detail": "", "box": [100.0, 100.0, 120.0, 120.0]})
    labels = [{"image": im, "label_index": 0, "box": [0.0, 0.0, 50.0, 50.0], "label_iou": 0.5,
               "class_name": "Car"} for im in IMAGES]
    preds = [{"image": im, "label_index": None, "box": [100.0, 100.0, 120.0, 120.0 + i],
              "confidence": 0.9 - i / 100, "covered_ratio": 0.0, "class_name": "Car",
              "objectlab_overlooked": 0.1 * i} for i, im in enumerate(IMAGES[:3])]
    data = {"dataset": DATASET, "generated_at": "2026-09-27T00:00:00+00:00", "summary": {},
            "caveat": "", "review_queue": aida, "all_candidates": aida, "total_in_queue": 7,
            "all_labels": labels, "unmatched_predictions": preds,
            "ranking": {"ranking_version": version,
                        "ranking_scope": "mixed_queue" if version == V1 else "per_layer",
                        "ranking_signal": {"labelled_candidates": "s", "missing_candidates": "s"},
                        "dataset_boost_affects_order": version == V1, "tie_break_rule": "t"}}
    return data


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    monkeypatch.setattr(E, "UPLOADS_DIR", root)
    monkeypatch.setattr(upload, "UPLOADS_DIR", root)
    (root / DATASET).mkdir(parents=True)
    (root / DATASET / "label_diagnosis.json").write_text(json.dumps(diagnosis(V1)), encoding="utf-8")
    (root / DATASET / f"label_diagnosis.{V2}.json").write_text(json.dumps(diagnosis(V2)), encoding="utf-8")
    return root


@pytest.fixture
def client(uploads):
    return TestClient(app)


def start(client, evaluation_id, version, tie_seed=None, budget=3):
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": evaluation_id, "judge_budget": budget,
                          "ranking_version": version, "tie_seed": tie_seed})
    assert r.status_code == 200, r.text
    return r.json()


def export(client, evaluation_id, methods, scope="labelled_candidates"):
    r = client.get(f"/api/datasets/{DATASET}/evaluations/{evaluation_id}/export"
                   f"?methods={methods}&scope={scope}&mode=candidate_generation_included")
    assert r.status_code == 200, r.text
    return r.json()


def aggregated_top(body, method, n=3):
    facts, ranks = load_export(body, require_comparison=False)
    by_key = {a.key: a for a in facts}
    mine = [r for r in ranks if r.method == method]
    return [by_key[r.candidate_key].image_id for r in top_n(mine, by_key, n)]


def hash_order():
    """이름순과 다른 동점 순서를 내는 씨앗을 찾는다 — 검사가 씨앗 하나에 기대지 않게."""
    for seed in range(1, 200):
        keys = sorted(IMAGES, key=lambda im: E.tie_key(seed, E.canonical_id(im, 0, "width", [0.0, 0.0, 50.0, 50.0])))
        if keys[:3] != IMAGES[:3]:
            return seed, keys
    raise AssertionError("씨앗 200개 중 이름순과 다른 것이 없다")


def test_v2_기존_라벨_층에서_AIDA_동점은_씨앗으로_잘리고_두_방법이_같은_순서다(client):
    seed, expected = hash_order()
    snap = start(client, "e1", V2, tie_seed=seed)
    body = export(client, "e1", "aida,all_label_iou")
    assert body["order_basis"]["aida"] == "score_1_minus_label_iou"
    assert aggregated_top(body, "aida") == expected[:3] != IMAGES[:3]
    assert aggregated_top(body, "all_label_iou") == expected[:3]
    # 선정(판정 대상)도 같은 3건 — 두 방법이 같은 후보라 합집합이 3건이다
    q = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").json()
    labelled = [c["image"] for c in q["candidates"] if c["label_index"] is not None]
    assert sorted(labelled) == sorted(expected[:3])
    # 같은 후보는 두 방법에서 같은 tie_key
    keys = {}
    for r in body["rankings"]:
        keys.setdefault(r["canonical_candidate_id"], set()).add(r["tie_key"])
    assert all(len(v) == 1 for v in keys.values())


def test_v1은_제품_순위_그대로다(client):
    seed, _ = hash_order()
    start(client, "e1", V1, tie_seed=seed)
    body = export(client, "e1", "aida,all_label_iou")
    assert body["order_basis"]["aida"] == "product_rank"
    assert aggregated_top(body, "aida") == IMAGES[:3]


def test_v2_누락_층은_제품_순위_그대로다(client):
    seed, _ = hash_order()
    start(client, "e1", V2, tie_seed=seed)
    snap = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").json()
    body = export(client, "e1", "aida", scope="missing_candidates")
    assert body["order_basis"]["aida"] == "product_rank"


def test_누락_층은_세_방법을_기술_통계로_내보내고_집계까지_간다(client):
    start(client, "e1", V2, tie_seed=1)
    body = export(client, "e1", "aida,unmatched_confidence,unmatched_objectlab",
                  scope="missing_candidates")
    assert body["descriptive_only"] is True and body["comparison_allowed"] is False
    assert body["method_population"] == {"aida": 0, "unmatched_confidence": 3, "unmatched_objectlab": 3} \
        or body["method_population"]["unmatched_objectlab"] == 3
    facts, ranks = load_export(body, require_comparison=False)
    for m in ("unmatched_confidence", "unmatched_objectlab"):
        summ = summarise(facts, ranks, m, budget=3)
        assert summ.in_budget == 3
    with pytest.raises(Exception):
        load_export(body, require_comparison=True)


def test_누락_층에_정의되지_않은_방법은_여전히_거부한다(client):
    start(client, "e1", V2, tie_seed=1)
    r = client.get(f"/api/datasets/{DATASET}/evaluations/e1/export"
                   "?methods=aida,all_label_iou&scope=missing_candidates&mode=candidate_generation_included")
    assert r.status_code == 409
