"""판정자 분리와 보조 표본 (사전 등록 D8).

사람(primary)의 원본과 보조 판정자의 원본을 따로 저장하고, 1차 분석에 쓸 원본을 명시적으로
고른다. 보조 표본은 판정 대상 확정 뒤·판정 전에 고정 씨앗으로 뽑는다.
"""
import json
import math

import pytest
from fastapi.testclient import TestClient

from app.agreement import agreement_report, cohen_kappa
from app.main import app
from app.routers import evaluation as E
from app.routers import upload

DATASET = "abcdefabcdef"


def diagnosis(n=12) -> dict:
    rows = [{"rank": i + 1, "image": f"im{i % 4}.png", "label_index": i, "suspicion": "width",
             "severity": 1 - i / 100, "detail": "", "box": [0.0, 0.0, 50.0, 50.0 + i],
             "label_iou": 0.5} for i in range(n)]
    return {"dataset": DATASET, "generated_at": "2026-09-27T00:00:00+00:00", "summary": {},
            "caveat": "", "review_queue": rows, "all_candidates": rows, "total_in_queue": n}


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    monkeypatch.setattr(E, "UPLOADS_DIR", root)
    monkeypatch.setattr(upload, "UPLOADS_DIR", root)
    (root / DATASET).mkdir(parents=True)
    (root / DATASET / "label_diagnosis.json").write_text(json.dumps(diagnosis()), encoding="utf-8")
    return root


@pytest.fixture
def client(uploads):
    return TestClient(app)


def start(client, evaluation_id="e1", **body):
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": evaluation_id, "judge_budget": 10,
                          "auxiliary_sample_fraction": 0.3, "auxiliary_sample_seed": 20260930, **body})
    assert r.status_code == 200, r.text
    return r.json()


def put(client, snap, rows, adjudicator=None, evaluation_id="e1"):
    url = f"/api/datasets/{DATASET}/evaluations/{evaluation_id}/adjudications"
    if adjudicator:
        url += f"?adjudicator={adjudicator}"
    return client.put(url, json={"candidate_set_hash": snap["candidate_set_hash"], "adjudications": rows})


def queue(client, adjudicator=None, evaluation_id="e1"):
    url = f"/api/datasets/{DATASET}/evaluations/{evaluation_id}/queue"
    if adjudicator:
        url += f"?adjudicator={adjudicator}"
    return client.get(url)


# ── 보조 표본 추출 ─────────────────────────────────────────────────────────────

def test_보조_표본은_판정_대상에서_올림으로_뽑고_기록한다(client):
    snap = start(client)
    aux = snap["auxiliary_sample"]
    allowed = {c["canonical_candidate_id"] for c in queue(client).json()["candidates"]}
    # 판정 대상 = AIDA 상위 10 ∪ 기준선 상위 10 (순서가 달라 12건)
    assert aux["pool_size"] == len(allowed) == 12
    assert aux["size"] == math.ceil(0.3 * 12) == 4
    assert aux["rounding"] == "ceil" and aux["seed"] == 20260930
    assert set(aux["candidate_ids"]) <= allowed
    assert aux["candidate_ids"] == sorted(aux["candidate_ids"])


def test_같은_씨앗이면_같은_표본_다른_씨앗이면_다른_표본(client):
    a = start(client, "e1")["auxiliary_sample"]["candidate_ids"]
    b = start(client, "e2")["auxiliary_sample"]["candidate_ids"]
    c = start(client, "e3", auxiliary_sample_seed=1)["auxiliary_sample"]["candidate_ids"]
    assert a == b
    assert a != c


def test_표본_규칙은_지문에_들어간다(client):
    a = start(client, "e1")["candidate_set_hash"]
    b = start(client, "e2", auxiliary_sample_seed=1)["candidate_set_hash"]
    assert a != b


def test_씨앗_없는_표본은_거부한다(client):
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": "e9", "auxiliary_sample_fraction": 0.3})
    assert r.status_code == 400


# ── 판정자 분리 ────────────────────────────────────────────────────────────────

def test_보조_판정자는_표본만_보고_점수를_받지_않는다(client):
    snap = start(client)
    q = queue(client, "ai").json()
    ids = [c["canonical_candidate_id"] for c in q["candidates"]]
    assert sorted(ids) == snap["auxiliary_sample"]["candidate_ids"]
    for c in q["candidates"]:
        assert set(c) <= {"canonical_candidate_id", "image", "label_index", "box", "class_name",
                          "verdict", "unique_error_id"}
        assert c["verdict"] is None


def test_보조_판정자의_판정은_사람_판정에_섞이지_않는다(client, uploads):
    snap = start(client)
    aux = snap["auxiliary_sample"]["candidate_ids"]
    assert put(client, snap, [{"canonical_candidate_id": aux[0], "verdict": "hit"}]).status_code == 200
    assert put(client, snap, [{"canonical_candidate_id": aux[0], "verdict": "miss"}], "ai").status_code == 200
    # 파일이 다르다
    d = uploads / DATASET / "evaluations" / "e1"
    assert (d / "adjudications.json").exists() and (d / "adjudications.ai.json").exists()
    human = json.loads((d / "adjudications.json").read_text(encoding="utf-8"))
    assert human["adjudicator"] == "primary" and human["adjudications"][0]["verdict"] == "hit"
    # 사람 화면에는 사람 판정만, 보조 화면에는 보조 판정만
    hv = {c["canonical_candidate_id"]: c["verdict"] for c in queue(client).json()["candidates"]}
    av = {c["canonical_candidate_id"]: c["verdict"] for c in queue(client, "ai").json()["candidates"]}
    assert hv[aux[0]] == "hit" and av[aux[0]] == "miss"


def test_보조_판정자는_표본_밖을_판정할_수_없다(client):
    snap = start(client)
    aux = set(snap["auxiliary_sample"]["candidate_ids"])
    outside = next(c["canonical_candidate_id"] for c in queue(client).json()["candidates"]
                   if c["canonical_candidate_id"] not in aux)
    r = put(client, snap, [{"canonical_candidate_id": outside, "verdict": "hit"}], "ai")
    assert r.status_code == 400


def test_표본이_없는_묶음에는_보조_판정이_없다(client):
    r = client.post(f"/api/datasets/{DATASET}/evaluations", json={"evaluation_id": "e5"})
    assert r.status_code == 200 and r.json()["auxiliary_sample"] is None
    assert queue(client, "ai", "e5").status_code == 409


def test_옛_판정_파일은_primary로_읽힌다(client, uploads):
    snap = start(client)
    aux = snap["auxiliary_sample"]["candidate_ids"]
    put(client, snap, [{"canonical_candidate_id": aux[0], "verdict": "hit"}])
    path = uploads / DATASET / "evaluations" / "e1" / "adjudications.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["adjudicator"]                      # 이 기능 전의 파일 모양
    path.write_text(json.dumps(data), encoding="utf-8")
    q = queue(client).json()
    assert {c["canonical_candidate_id"]: c["verdict"] for c in q["candidates"]}[aux[0]] == "hit"


def test_내보내기는_판정자를_명시적으로_고르고_기록한다(client):
    snap = start(client)
    aux = snap["auxiliary_sample"]["candidate_ids"]
    put(client, snap, [{"canonical_candidate_id": aux[0], "verdict": "hit"}])
    put(client, snap, [{"canonical_candidate_id": aux[0], "verdict": "miss"}], "ai")
    base = f"/api/datasets/{DATASET}/evaluations/e1/export?methods=aida"
    p = client.get(base).json()
    a = client.get(base + "&adjudicator=ai").json()
    assert p["adjudicator"] == "primary" and a["adjudicator"] == "ai"
    pv = {r["canonical_candidate_id"]: r["verdict"] for r in p["adjudications"]}
    av = {r["canonical_candidate_id"]: r["verdict"] for r in a["adjudications"]}
    assert pv[aux[0]] == "hit" and av[aux[0]] == "miss"
    assert p["auxiliary_sample"]["size"] == 4 and "candidate_ids" not in p["auxiliary_sample"]


def test_판정자_id_형식을_검사한다(client):
    start(client)
    assert queue(client, "AI").status_code == 400
    assert queue(client, "a/b").status_code == 400


# ── 일치도 ────────────────────────────────────────────────────────────────────

def test_kappa_손계산():
    # 3분류: [hit,hit] [miss,miss] [hold,hit] [hit,miss] → po .5, pe .375 → κ 0.2
    assert cohen_kappa([("hit", "hit"), ("miss", "miss"), ("hold", "hit"), ("hit", "miss")]) == pytest.approx(0.2)
    # 2분류(보류 제외): [hit,hit] [miss,miss] [hit,miss] → po 2/3, pe 4/9 → κ 0.4
    assert cohen_kappa([("hit", "hit"), ("miss", "miss"), ("hit", "miss")]) == pytest.approx(0.4)
    assert cohen_kappa([]) is None
    assert cohen_kappa([("hit", "hit"), ("hit", "hit")]) is None   # 기대 일치 1


def test_일치도_보고서는_분모를_가른다():
    ids = ["a", "b", "c", "d", "e"]
    rep = agreement_report(ids, {"a": "hit", "b": "miss", "c": "hold", "d": "hit", "e": "hit"},
                           {"a": "hit", "b": "miss", "c": "hit", "d": "miss"})
    assert rep["sample_size"] == 5
    assert rep["primary_judged"] == 5 and rep["secondary_judged"] == 4
    assert rep["primary_holds"] == 1 and rep["secondary_holds"] == 0
    assert rep["both_judged"] == 4 and rep["both_decided"] == 3
    assert rep["agreement_3way"]["rate"] == pytest.approx(0.5)
    assert rep["agreement_3way"]["kappa"] == pytest.approx(0.2)
    assert rep["agreement_decided"]["kappa"] == pytest.approx(0.4)


def test_일치도_api는_표본에서만_센다(client):
    snap = start(client)
    aux = snap["auxiliary_sample"]["candidate_ids"]
    # 표본 4건 중 3건만 판정 — 4번째는 양쪽 다 미판정
    put(client, snap, [{"canonical_candidate_id": i, "verdict": v} for i, v in zip(aux, ["hit", "miss", "hold"])])
    put(client, snap, [{"canonical_candidate_id": i, "verdict": v} for i, v in zip(aux, ["hit", "hit", "hit"])], "ai")
    r = client.get(f"/api/datasets/{DATASET}/evaluations/e1/agreement?secondary=ai")
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["sample_size"] == 4 and rep["both_judged"] == 3 and rep["both_decided"] == 2
    assert rep["primary_holds"] == 1 and rep["secondary_holds"] == 0
    assert rep["agreement_decided"]["agree"] == 1
    assert client.get(f"/api/datasets/{DATASET}/evaluations/e1/agreement?secondary=primary").status_code == 400
