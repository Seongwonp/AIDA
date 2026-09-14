"""재검수 순위 버전이 API·평가 묶음·내보내기·이력에서 섞이지 않는가
(docs/adr-ranking-separation.md).

**v1은 지금까지의 제품 순위 그대로, v2는 시험 버전이다.** 둘이 같은 이름으로 보이거나 한
집계에 섞이면 "어느 순서를 잰 숫자인가"를 잃는다. 버전 기록이 없는 옛 파일은 v1로 읽는다.

기대값의 버전 이름은 문자열로 직접 적는다 — 구현 상수로 적으면 v1·v2가 뒤바뀌어도 통과한다.
"""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import evaluation as E
from app.routers import upload
from tests import fake_experiment as fake

DATASET = "0123456789ab"
V1 = "aida_v1_systematic_boost"
V2 = "aida_v2_candidate_iou"
V1_FILE = "label_diagnosis.json"
V2_FILE = "label_diagnosis.aida_v2_candidate_iou.json"


def rows():
    return [
        {"rank": 1, "image": "a.png", "label_index": 0, "suspicion": "width",
         "severity": 0.9, "detail": "", "box": [10.0, 10.0, 60.0, 60.0],
         "label_iou": 0.4, "layer": "labelled_candidates", "layer_rank": 1},
        {"rank": 2, "image": "b.png", "label_index": None, "suspicion": "missing",
         "severity": 0.7, "detail": "", "box": [5.0, 5.0, 30.0, 30.0],
         "layer": "missing_candidates", "layer_rank": 1},
    ]


def diagnosis(ranking: str | None) -> dict:
    data = fake.diagnosis_payload(DATASET)
    data["review_queue"] = rows()
    data["all_candidates"] = rows()
    data["total_in_queue"] = 2
    if ranking is not None:
        data["ranking"] = {
            "ranking_version": ranking,
            "ranking_scope": "mixed_queue" if ranking == V1 else "per_layer",
            "ranking_signal": {"labelled_candidates": "s", "missing_candidates": "s"},
            "dataset_boost_affects_order": ranking == V1,
            "tie_break_rule": "t",
        }
    return data


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    monkeypatch.setattr(E, "UPLOADS_DIR", root)
    monkeypatch.setattr(upload, "UPLOADS_DIR", root)
    (root / DATASET / "images").mkdir(parents=True)
    return root


@pytest.fixture
def client(uploads):
    return TestClient(app)


def write(uploads, name, data):
    (uploads / DATASET / name).write_text(json.dumps(data), encoding="utf-8")


# ── 진단 결과 읽기 ───────────────────────────────────────────────────────────

def test_버전_기록이_없는_옛_진단은_v1로_읽고_옛_결과라고_표시한다(client, uploads):
    write(uploads, V1_FILE, diagnosis(None))
    body = client.get(f"/api/datasets/{DATASET}/label-diagnosis").json()
    assert body["ranking"]["ranking_version"] == V1
    assert body["ranking"]["legacy"] is True
    assert body["ranking"]["dataset_boost_affects_order"] is True


def test_v2_결과는_따로_읽히고_v1으로_보이지_않는다(client, uploads):
    write(uploads, V1_FILE, diagnosis(None))
    write(uploads, V2_FILE, diagnosis(V2))
    two = client.get(f"/api/datasets/{DATASET}/label-diagnosis?ranking={V2}").json()
    one = client.get(f"/api/datasets/{DATASET}/label-diagnosis").json()
    assert (two["ranking"]["ranking_version"], two["ranking"]["legacy"]) == (V2, False)
    assert two["ranking"]["dataset_boost_affects_order"] is False
    assert one["ranking"]["ranking_version"] == V1


def test_v2_줄의_층_정보가_응답에_실린다(client, uploads):
    write(uploads, V2_FILE, diagnosis(V2))
    body = client.get(f"/api/datasets/{DATASET}/label-diagnosis?ranking={V2}").json()
    assert [(r["layer"], r["layer_rank"]) for r in body["review_queue"]] == [
        ("labelled_candidates", 1), ("missing_candidates", 1)]


def test_파일_이름과_안에_적힌_버전이_다르면_읽지_않는다(client, uploads):
    write(uploads, V2_FILE, diagnosis(V1))
    r = client.get(f"/api/datasets/{DATASET}/label-diagnosis?ranking={V2}")
    assert r.status_code == 409


def test_모르는_버전은_400이다(client, uploads):
    write(uploads, V1_FILE, diagnosis(None))
    assert client.get(f"/api/datasets/{DATASET}/label-diagnosis?ranking=aida_v3").status_code == 400


def test_그_버전의_진단이_없으면_404다(client, uploads):
    write(uploads, V1_FILE, diagnosis(None))
    assert client.get(f"/api/datasets/{DATASET}/label-diagnosis?ranking={V2}").status_code == 404


# ── 이력 ─────────────────────────────────────────────────────────────────────

def test_이력은_어느_버전의_결과가_있는지_보여준다(client, uploads):
    write(uploads, V1_FILE, diagnosis(None))
    write(uploads, V2_FILE, diagnosis(V2))
    rows_ = client.get("/api/datasets/history").json()
    assert rows_[0]["ranking_versions"] == [V1, V2]
    assert rows_[0]["has_label_diagnosis"] is True


def test_v2만_있어도_이력에서_열_수_있다(client, uploads):
    write(uploads, V2_FILE, diagnosis(V2))
    row = client.get("/api/datasets/history").json()[0]
    assert (row["has_label_diagnosis"], row["ranking_versions"]) == (True, [V2])


# ── 평가 묶음 ─────────────────────────────────────────────────────────────────

def test_버전이_없는_옛_묶음의_지문은_예전_재료_그대로다(uploads):
    """지문 재료를 여기서 **손으로** 다시 만든다. `ranking_version` 키가 끼면 달라진다.

    prelim1 같은 옛 묶음은 이 재료로 지문이 만들어졌다 — 바뀌면 판정이 묶음에서 떨어진다.
    """
    snap = E.build_snapshot(DATASET, "e1", diagnosis(None), shuffle_seed=3)
    by_image = {c.image: c.canonical_candidate_id for c in snap.candidates}
    candidates = [
        {"canonical_candidate_id": by_image["a.png"], "image": "a.png", "label_index": 0,
         "suspicion": "width", "box": [10.0, 10.0, 60.0, 60.0], "class_name": None,
         "scores": {"aida": 0.9, "iou_baseline": 0.6}, "aida_rank": 1},
        {"canonical_candidate_id": by_image["b.png"], "image": "b.png", "label_index": None,
         "suspicion": "missing", "box": [5.0, 5.0, 30.0, 30.0], "class_name": None,
         "scores": {"aida": 0.7}, "aida_rank": 2},
    ]
    payload = {
        "schema_version": 1, "dataset_id": DATASET, "shuffle_seed": 3,
        "diagnosis_generated_at": "2026-09-05T00:00:00+00:00", "judge_budget": None,
        "candidate_pool": "all_candidates", "total_in_queue": 2, "ruler": None,
        "candidates": sorted(candidates, key=lambda c: c["canonical_candidate_id"]),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert snap.ranking_version is None
    assert snap.candidate_set_hash == hashlib.sha256(text.encode("utf-8")).hexdigest()


def start(client, evaluation_id="e1", **body):
    return client.post(f"/api/datasets/{DATASET}/evaluations",
                       json={"evaluation_id": evaluation_id, **body})


def test_새_묶음은_순위_버전을_얼리고_지문에_넣는다(client, uploads):
    write(uploads, V1_FILE, diagnosis(None))
    write(uploads, V2_FILE, diagnosis(V2))
    one = start(client, "e1", shuffle_seed=3)
    two = start(client, "e2", shuffle_seed=3, ranking_version=V2)
    assert one.status_code == 200 and two.status_code == 200, (one.text, two.text)
    assert one.json()["ranking_version"] == V1
    assert two.json()["ranking_version"] == V2
    legacy = E.build_snapshot(DATASET, "e0", diagnosis(None), shuffle_seed=3)
    # 같은 진단·같은 씨앗인데 버전을 얼렸으니 옛 재료의 지문과 다르다
    assert one.json()["candidate_set_hash"] != legacy.candidate_set_hash
    assert one.json()["candidate_set_hash"] != two.json()["candidate_set_hash"]


def test_묶음_버전과_진단_파일의_버전이_다르면_얼리지_않는다(client, uploads):
    write(uploads, V2_FILE, diagnosis(V1))
    assert start(client, ranking_version=V2).status_code == 409


def test_모르는_버전으로는_얼리지_않는다(client, uploads):
    write(uploads, V1_FILE, diagnosis(None))
    assert start(client, ranking_version="aida_v3").status_code == 400


def test_얼린_뒤_다른_버전으로_재진단해도_묶음은_v1_그대로다(client, uploads):
    write(uploads, V1_FILE, diagnosis(None))
    snap = start(client).json()
    write(uploads, V2_FILE, diagnosis(V2))
    again = E.load_snapshot(DATASET, "e1")
    assert (again.ranking_version, again.candidate_set_hash) == (V1, snap["candidate_set_hash"])


# ── 내보내기 ─────────────────────────────────────────────────────────────────

def export(client, evaluation_id="e1"):
    return client.get(f"/api/datasets/{DATASET}/evaluations/{evaluation_id}/export?methods=aida")


def test_버전이_없는_옛_묶음은_v1로_내보내고_기록이_없었다고_적는다(client, uploads):
    snap = E.build_snapshot(DATASET, "e1", diagnosis(None))
    E.save_snapshot(DATASET, snap)
    raw = json.loads((uploads / DATASET / "evaluations" / "e1" / "snapshot.json").read_text(encoding="utf-8"))
    assert raw.get("ranking_version") is None
    body = export(client).json()
    assert (body["ranking_version"], body["ranking_version_recorded"]) == (V1, False)


def test_v2_묶음의_내보내기는_v2라고_적는다(client, uploads):
    write(uploads, V2_FILE, diagnosis(V2))
    assert start(client, ranking_version=V2).status_code == 200
    body = export(client).json()
    assert (body["ranking_version"], body["ranking_version_recorded"]) == (V2, True)


def export_methods(client, methods, evaluation_id="e1"):
    return client.get(f"/api/datasets/{DATASET}/evaluations/{evaluation_id}/export?methods={methods}")


def test_v2_묶음은_같은_신호인_IoU_기준선과_견주지_않는다(client, uploads):
    """v2의 기존 라벨 순서는 `1 − label_iou`라 `iou_baseline`과 같다. 견주면 차이가 0에
    가깝게 나오고 "AIDA가 기준선과 대등하다"로 잘못 읽힌다 (docs/adr-ranking-separation.md)."""
    write(uploads, V2_FILE, diagnosis(V2))
    assert start(client, ranking_version=V2).status_code == 200
    r = export_methods(client, "aida,iou_baseline")
    assert r.status_code == 409
    assert "같은 신호" in r.json()["detail"]
    assert export_methods(client, "aida").status_code == 200


def test_v1_묶음은_여전히_IoU_기준선과_견줄_수_있다(client, uploads):
    write(uploads, V1_FILE, diagnosis(None))
    assert start(client).status_code == 200
    assert export_methods(client, "aida,iou_baseline").status_code == 200


def test_버전_없는_옛_묶음도_IoU_기준선과_견줄_수_있다(client, uploads):
    """prelim1 같은 옛 묶음은 v1이다 — 그 비교를 막으면 사전 등록한 집계를 다시 못 돌린다."""
    E.save_snapshot(DATASET, E.build_snapshot(DATASET, "e1", diagnosis(None)))
    assert export_methods(client, "aida,iou_baseline").status_code == 200


# ── 진단 실행 ─────────────────────────────────────────────────────────────────

@pytest.fixture
def wired(fake_experiment, monkeypatch):
    root, uploads = fake_experiment
    ds = uploads / DATASET
    (ds / "images").mkdir(parents=True)
    (ds / "labels").mkdir(parents=True)
    (ds / "images" / "a.png").write_bytes(b"\x89PNG")
    (ds / "labels" / "a.txt").write_text("0 0.5 0.5 0.2 0.2", encoding="utf-8")
    monkeypatch.setenv("FAKE_UPLOADS_DIR", str(uploads))
    monkeypatch.setenv("FAKE_DIAGNOSIS_JSON", json.dumps(diagnosis(None), ensure_ascii=False))
    return TestClient(app), uploads


def test_v2로_진단해도_v1_결과는_한_바이트도_안_바뀐다(wired):
    client, uploads = wired
    v1_path = uploads / DATASET / V1_FILE
    v1_path.write_text(json.dumps(diagnosis(None)), encoding="utf-8")
    before = v1_path.read_bytes()

    res = client.post(f"/api/datasets/{DATASET}/diagnose-labels?ranking={V2}")
    assert res.status_code == 200, res.text
    assert res.json()["ranking"]["ranking_version"] == V2
    assert v1_path.read_bytes() == before
    call = json.loads((uploads / DATASET / "stub_call.json").read_text(encoding="utf-8"))
    assert call["argv"] == ["--upload-id", DATASET, "--ranking", V2]


def test_진단은_모르는_버전을_받지_않는다(wired):
    client, _ = wired
    assert client.post(f"/api/datasets/{DATASET}/diagnose-labels?ranking=aida_v3").status_code == 400


# ── 두 코드의 이름이 같은가 ───────────────────────────────────────────────────

def test_백엔드와_진단_코드의_버전_이름과_파일_이름이_같다():
    L = pytest.importorskip("label_diagnosis", reason="experiment/ 코드를 못 읽는 환경")
    from app import ranking as R
    assert (R.RANKING_V1, R.RANKING_V2) == (L.RANKING_V1, L.RANKING_V2) == (V1, V2)
    for v in (V1, V2):
        assert R.diagnosis_filename(v) == L.diagnosis_filename(v)
