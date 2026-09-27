"""동점 씨앗 (사전 등록 D9).

점수가 같은 후보의 순서를 고정 씨앗으로 자르고, 후보 선정·화면 대상·내보내기·집계가 같은
순서를 쓰는지 본다. IoU 0 라벨은 포함하고 그 수를 보고한다.
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

DATASET = "abcdefabcdef"


def diagnosis() -> dict:
    # AIDA 후보 2건 + 규칙 밖 라벨 6건, 그중 5건이 IoU 0(동점 1.0) — 파일 이름은 z…a 역순
    aida = [{"rank": 1, "image": "m.png", "label_index": 0, "suspicion": "width", "severity": 0.9,
             "detail": "", "box": [0.0, 0.0, 50.0, 50.0], "label_iou": 0.5},
            {"rank": 2, "image": "n.png", "label_index": 0, "suspicion": "width", "severity": 0.8,
             "detail": "", "box": [0.0, 0.0, 50.0, 50.0], "label_iou": 0.6}]
    labels = [{"image": im, "label_index": 0, "box": [0.0, 0.0, 50.0, 50.0], "label_iou": 0.0,
               "class_name": "Car"} for im in ("z.png", "y.png", "x.png", "w.png", "v.png")]
    labels.append({"image": "a.png", "label_index": 0, "box": [0.0, 0.0, 50.0, 50.0],
                   "label_iou": 0.3, "class_name": "Car"})
    labels += [{"image": r["image"], "label_index": 0, "box": r["box"], "label_iou": r["label_iou"],
                "class_name": "Car"} for r in aida]
    return {"dataset": DATASET, "generated_at": "2026-09-27T00:00:00+00:00", "summary": {},
            "caveat": "", "review_queue": aida, "all_candidates": aida, "total_in_queue": 2,
            "all_labels": labels, "unmatched_predictions": []}


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
                    json={"evaluation_id": evaluation_id, "judge_budget": 3, **body})
    assert r.status_code == 200, r.text
    return r.json()


def export(client, evaluation_id="e1"):
    r = client.get(f"/api/datasets/{DATASET}/evaluations/{evaluation_id}/export"
                   "?methods=aida,all_label_iou&mode=candidate_generation_included")
    assert r.status_code == 200, r.text
    return r.json()


def top_iou(client, evaluation_id):
    body = export(client, evaluation_id)
    facts, ranks = load_export(body)
    by_key = {a.key: a for a in facts}
    mine = [r for r in ranks if r.method == "all_label_iou"]
    return [by_key[r.candidate_key].image_id for r in top_n(mine, by_key, 3)], body


def test_씨앗이_없으면_동점은_이미지_이름순이다(client):
    images, body = top_iou(client, start(client, "e0")["evaluation_id"])
    assert images == ["v.png", "w.png", "x.png"]
    assert body["tie_seed"] is None and "tie_key" not in body["rankings"][0]


def test_씨앗이_있으면_동점_순서가_씨앗으로_정해지고_재현된다(client):
    a, body_a = top_iou(client, start(client, "e1", tie_seed=20260929)["evaluation_id"])
    b, _ = top_iou(client, start(client, "e2", tie_seed=20260929)["evaluation_id"])
    c, _ = top_iou(client, start(client, "e3", tie_seed=1)["evaluation_id"])
    assert a == b
    assert a != ["v.png", "w.png", "x.png"] or c != a     # 적어도 한 씨앗은 이름순과 다르다
    assert set(a) <= {"z.png", "y.png", "x.png", "w.png", "v.png"}
    assert body_a["tie_seed"] == 20260929 and all("tie_key" in r for r in body_a["rankings"])


def test_후보_선정과_집계가_같은_상위_N을_본다(client):
    snap = start(client, "e1", tie_seed=20260929)
    images, body = top_iou(client, "e1")
    # 판정 대상(화면)에 all_label_iou 상위 3이 전부 들어 있다
    q = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").json()
    shown = {c["image"] for c in q["candidates"]}
    assert set(images) <= shown
    # 판정 대상 = AIDA 상위 2 ∪ all_label_iou 상위 3 (겹침 없음)
    assert len(q["candidates"]) == 5


def test_같은_후보는_방법이_달라도_같은_동점_키다():
    assert E.tie_key(7, "Labc") == E.tie_key(7, "Labc")
    assert E.tie_key(7, "Labc") != E.tie_key(8, "Labc")
    assert E.tie_key(None, "Labc") is None


def test_씨앗은_지문에_들어간다(client):
    a = start(client, "e1")["candidate_set_hash"]
    b = start(client, "e2", tie_seed=20260929)["candidate_set_hash"]
    assert a != b


def test_iou_0_라벨_수를_보고한다(client):
    start(client, "e1", tie_seed=20260929)
    body = export(client, "e1")
    z = body["iou_zero_labels"]
    assert z["in_scope_labels"] == 5 and z["in_top_n_all_label_iou"] == 3 and z["n"] == 3


def test_입력_순서가_달라도_같은_순서다(client, uploads):
    d = diagnosis()
    d["all_labels"] = list(reversed(d["all_labels"]))
    (uploads / DATASET / "label_diagnosis.json").write_text(json.dumps(d), encoding="utf-8")
    a, _ = top_iou(client, start(client, "e1", tie_seed=20260929)["evaluation_id"])
    (uploads / DATASET / "label_diagnosis.json").write_text(json.dumps(diagnosis()), encoding="utf-8")
    b, _ = top_iou(client, start(client, "e2", tie_seed=20260929)["evaluation_id"])
    assert a == b


def test_동점_키_식은_집계_모듈과_같다():
    import hashlib
    from evaluation.coverage import tie_key as agg_tie_key
    assert E.tie_key(20260929, "Lx") == agg_tie_key(20260929, "Lx") == hashlib.sha256(b"20260929:Lx").hexdigest()
