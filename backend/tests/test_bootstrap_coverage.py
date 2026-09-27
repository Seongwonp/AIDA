"""고정 재표본 합집합 (안 (a)) — 후보 선정 → 화면 → 저장 → 내보내기 → 집계 연결.

비교 예산 N과 점 추정치는 그대로이고, 추가 후보는 판정 목록·저장·내보내기에 들며 K와 섞이지
않는다. 확장 목록만 판정한 구간 = 전량 판정 구간.
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
from evaluation.bootstrap import paired_cluster_bootstrap  # noqa: E402
from evaluation.importer import load_export  # noqa: E402

DATASET = "abcdefabcdef"
V2 = "aida_v2_candidate_iou"
N, ITER, SEED = 4, 80, 42


def diagnosis():
    import random
    rng = random.Random(5)
    aida, labels, groups = [], [], {}
    rank = 1
    for g in range(8):
        for i in range(3):
            im = f"g{g}i{i}.png"; groups[im] = f"log{g}"
            iou = round(rng.random(), 3)
            row = {"image": im, "label_index": 0, "box": [0.0, 0.0, 50.0, 50.0], "label_iou": iou,
                   "class_name": "Car"}
            labels.append(row)
            if rng.random() < 0.7:
                aida.append({"rank": rank, "image": im, "label_index": 0, "suspicion": "width",
                             "severity": 1 - iou, "detail": "", "box": row["box"], "label_iou": iou})
                rank += 1
    aida.sort(key=lambda r: -r["severity"])
    for i, r in enumerate(aida):
        r["rank"] = i + 1
    data = {"dataset": DATASET, "generated_at": "2026-09-27T00:00:00+00:00", "summary": {}, "caveat": "",
            "review_queue": aida, "all_candidates": aida, "total_in_queue": len(aida),
            "all_labels": labels, "unmatched_predictions": [],
            "ranking": {"ranking_version": V2, "ranking_scope": "per_layer",
                        "ranking_signal": {"labelled_candidates": "s", "missing_candidates": "s"},
                        "dataset_boost_affects_order": False, "tie_break_rule": "t"}}
    return data, groups


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    monkeypatch.setattr(E, "UPLOADS_DIR", root)
    monkeypatch.setattr(upload, "UPLOADS_DIR", root)
    (root / DATASET).mkdir(parents=True)
    data, groups = diagnosis()
    (root / DATASET / f"label_diagnosis.{V2}.json").write_text(json.dumps(data), encoding="utf-8")
    (root / DATASET / "groups.json").write_text(json.dumps(groups), encoding="utf-8")
    return root


@pytest.fixture
def client(uploads):
    return TestClient(app)


BODY = {"judge_budget": N, "ranking_version": V2, "tie_seed": 20260929,
        "random_sample_size": 2, "random_sample_seed": 7,
        "auxiliary_sample_fraction": 0.3, "auxiliary_sample_seed": 20260930}


def start(client, evaluation_id="e1", **extra):
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": evaluation_id, **BODY, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def export(client, evaluation_id="e1"):
    r = client.get(f"/api/datasets/{DATASET}/evaluations/{evaluation_id}/export"
                   "?methods=aida,all_label_iou&mode=candidate_generation_included")
    assert r.status_code == 200, r.text
    return r.json()


def queue_ids(client, evaluation_id="e1"):
    return {c["canonical_candidate_id"]
            for c in client.get(f"/api/datasets/{DATASET}/evaluations/{evaluation_id}/queue").json()["candidates"]}


def test_추가_후보는_판정_목록에_들고_N과_원래_상위_N은_그대로다(client):
    plain = start(client, "e0")
    cov = start(client, "e1", coverage_iterations=ITER, coverage_seed=SEED)
    bc = cov["bootstrap_coverage"]
    assert bc["budget"] == N and bc["iterations"] == ITER and bc["seed"] == SEED
    assert bc["additional_count"] > 0, "합성 조건에서 추가 후보가 없으면 검사가 뜻이 없다"
    assert bc["methods"] == ["aida", "all_label_iou"]
    base, full = queue_ids(client, "e0"), queue_ids(client, "e1")
    assert set(bc["additional_candidate_ids"]) <= full and full - base == set(bc["additional_candidate_ids"])
    assert bc["base_pool_size"] == len(base)
    # 원래 상위 N·점 추정치의 재료(순위)는 같다
    ea, eb = export(client, "e0"), export(client, "e1")
    assert sorted((r["method"], r["canonical_candidate_id"], r["severity"]) for r in ea["rankings"]) == \
        sorted((r["method"], r["canonical_candidate_id"], r["severity"]) for r in eb["rankings"])
    assert eb["judging"]["comparison_budget_n"] == N
    assert eb["judging"]["total_judging_list"] == len(full)
    assert eb["random_sample"]["in_scope"] == 2
    # 추가 후보는 K와 섞이지 않는다
    rows = {r["canonical_candidate_id"]: r for r in eb["adjudications"]}
    for cid in bc["additional_candidate_ids"]:
        assert rows[cid]["coverage_extra"] is True and rows[cid]["random_sample"] is False
    assert plain["candidate_set_hash"] != cov["candidate_set_hash"]


def test_보조_표본은_확장된_최종_목록에서_뽑힌다(client):
    cov = start(client, "e1", coverage_iterations=ITER, coverage_seed=SEED)
    aux = cov["auxiliary_sample"]
    assert aux["pool_size"] == len(queue_ids(client, "e1"))
    assert "추가 후보" in aux["pool"] and "represents" in aux


def test_추가_후보의_판정은_저장되고_확장_목록_판정이_전량_판정과_같은_구간을_낸다(client):
    cov = start(client, "e1", coverage_iterations=ITER, coverage_seed=SEED)
    ids = queue_ids(client, "e1")
    # 판정: 후보 id의 해시로 결정적 hit/miss
    def verdict(cid):
        return "hit" if int(cid[-1], 16) % 3 == 0 else "miss"
    rows = [{"canonical_candidate_id": i, "verdict": verdict(i)} for i in sorted(ids)]
    r = client.put(f"/api/datasets/{DATASET}/evaluations/e1/adjudications",
                   json={"candidate_set_hash": cov["candidate_set_hash"], "adjudications": rows})
    assert r.status_code == 200, r.text
    body = export(client, "e1")
    facts, ranks = load_export(body, require_comparison=False)
    res = paired_cluster_bootstrap(facts, ranks, "all_label_iou", "aida", N, ITER, SEED,
                                   require_same_candidates=False, require_judged_top_n=True)
    # 전량 판정
    all_rows = [{"canonical_candidate_id": c["canonical_candidate_id"], "verdict": verdict(c["canonical_candidate_id"])}
                for c in cov["candidates"] if c["label_index"] is not None]
    # 전부 판정하려면 예산 밖 판정을 받는 묶음이 필요하다 — 예산 없는 묶음으로 같은 후보를 얼린다
    r2 = client.post(f"/api/datasets/{DATASET}/evaluations",
                     json={"evaluation_id": "e2", "ranking_version": V2, "tie_seed": 20260929})
    assert r2.status_code == 200
    r = client.put(f"/api/datasets/{DATASET}/evaluations/e2/adjudications",
                   json={"candidate_set_hash": r2.json()["candidate_set_hash"], "adjudications": all_rows})
    assert r.status_code == 200, r.text
    facts2, ranks2 = load_export(export(client, "e2"), require_comparison=False)
    res2 = paired_cluster_bootstrap(facts2, ranks2, "all_label_iou", "aida", N, ITER, SEED,
                                    require_same_candidates=False)
    assert (res["observed_difference"], res["ci_low"], res["ci_high"]) == \
        (res2["observed_difference"], res2["ci_low"], res2["ci_high"])


def test_원래_상위_N만_판정하면_집계가_거부한다(client):
    plain = start(client, "e0")
    ids = queue_ids(client, "e0")
    rows = [{"canonical_candidate_id": i, "verdict": "miss"} for i in sorted(ids)]
    client.put(f"/api/datasets/{DATASET}/evaluations/e0/adjudications",
               json={"candidate_set_hash": plain["candidate_set_hash"], "adjudications": rows})
    facts, ranks = load_export(export(client, "e0"), require_comparison=False)
    with pytest.raises(Exception, match="미판정"):
        paired_cluster_bootstrap(facts, ranks, "all_label_iou", "aida", N, ITER, SEED,
                                 require_same_candidates=False, require_judged_top_n=True)


def test_반복_수나_씨앗이_없으면_거부한다(client):
    for body in ({"coverage_iterations": ITER}, {"coverage_seed": SEED}, {"coverage_iterations": 0, "coverage_seed": 1}):
        r = client.post(f"/api/datasets/{DATASET}/evaluations", json={"evaluation_id": "e9", **BODY, **body})
        assert r.status_code == 400, body


def test_입력_지문은_집계_모듈과_같은_식이다(client):
    from evaluation.coverage import export_fingerprint
    start(client, "e1", coverage_iterations=ITER, coverage_seed=SEED)
    body = export(client, "e1")
    assert export_fingerprint(body) == body["bootstrap_coverage"]["input_fingerprint"] == E._export_fingerprint(body)
