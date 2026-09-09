"""평가 판정의 생산 경로 (docs/evaluation-adjudication-design.md).

집계 모듈은 `Adjudication`과 `Ranking`을 **받기만 한다.** 그것을 누가 만드는지가
없었다. 여기서 검사하는 것은 그 생산 경로다 — 묶음 고정, 후보의 영구 이름,
`unique_error_id` 규칙, 저장 안전성, 집계로의 내보내기.

**"자연 오류에서 성능을 검증했다"가 아니다.** 판정은 아직 개발자가 한다.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import evaluation, upload

DATASET = "0123456789ab"


def _queue(*items) -> dict:
    """진단 결과 파일의 최소 모양. 평가가 얼리는 것은 `review_queue`뿐이다."""
    return {
        "dataset_id": DATASET,
        "generated_at": "2026-09-09T00:00:00+00:00",
        "summary": {},
        "caveat": "",
        "review_queue": [
            {"rank": i + 1, "image": im, "label_index": li, "suspicion": s,
             "severity": sev, "detail": "", "box": [0.1, 0.1, 0.2, 0.2]}
            for i, (im, li, s, sev) in enumerate(items)
        ],
    }


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


def write_diagnosis(uploads, data: dict) -> None:
    (uploads / DATASET / "label_diagnosis.json").write_text(
        json.dumps(data), encoding="utf-8")


def start(client, evaluation_id="e1") -> dict:
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": evaluation_id})
    assert r.status_code == 200, r.text
    return r.json()


def put(client, snap, rows, evaluation_id="e1"):
    return client.put(
        f"/api/datasets/{DATASET}/evaluations/{evaluation_id}/adjudications",
        json={"candidate_set_hash": snap["candidate_set_hash"],
              "adjudications": rows})


# ── 후보의 영구 이름 ──────────────────────────────────────────────────────────

def test_같은_라벨을_두_유형이_지목하면_후보가_둘이다(client, uploads):
    """`width`와 `scale`이 같은 라벨을 가리켜도 **판정 대상은 둘**이다.

    합쳐 버리면 어느 유형이 맞았는지 못 센다. 대신 둘 다 `hit`이면 같은
    `unique_error_id`로 모여 고유 오류는 하나다 — 그건 집계가 한다.
    """
    write_diagnosis(uploads, _queue(("a.jpg", 3, "width", 0.9),
                                    ("a.jpg", 3, "scale", 0.7)))
    snap = start(client)
    ids = [c["canonical_candidate_id"] for c in snap["candidates"]]
    assert len(set(ids)) == 2


def test_다른_이미지의_같은_라벨이_한_후보로_겹치지_않는다(client, uploads):
    """`label_index`는 **이미지 안에서만** 번호다.

    이름에 이미지를 안 넣으면 `a.jpg`의 0번과 `b.jpg`의 0번이 같은 이름이 되어,
    한쪽에 내린 판정이 다른 쪽에 붙는다.
    """
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9),
                                    ("b.jpg", 0, "width", 0.8)))
    snap = start(client)
    ids = [c["canonical_candidate_id"] for c in snap["candidates"]]
    assert len(set(ids)) == 2, f"이름이 겹쳤다: {ids}"


def test_누락_후보의_이름에_좌표가_안_들어간다(client, uploads):
    """자가 바뀌면 예측 좌표가 흔들린다. 좌표는 근거이지 이름이 아니다."""
    write_diagnosis(uploads, _queue(("a.jpg", None, "missing", 0.9)))
    snap = start(client)
    name = snap["candidates"][0]["canonical_candidate_id"]
    assert "0.1" not in name and "0.2" not in name


# ── 묶음 고정 ────────────────────────────────────────────────────────────────

def test_재진단해도_묶음이_안_바뀐다(client, uploads):
    """진단 결과 파일을 덮어써도 평가는 얼린 목록을 계속 쓴다."""
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    snap = start(client)

    write_diagnosis(uploads, _queue(("z.jpg", 7, "missing", 0.1)))
    queue = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").json()

    assert queue["candidate_set_hash"] == snap["candidate_set_hash"]
    assert [c["image"] for c in queue["candidates"]] == ["a.jpg"]


def test_같은_평가를_다시_시작하면_거부한다(client, uploads):
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    start(client)
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": "e1"})
    assert r.status_code == 409


# ── 가림 ─────────────────────────────────────────────────────────────────────

def test_판정_화면에_점수와_유형이_안_간다(client, uploads):
    """보고 판단하면 결과가 휜다 — 그게 가림 판정의 이유다."""
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    start(client)
    body = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").text
    assert "severity" not in body and "0.9" not in body
    assert "suspicion" not in body and "width" not in body


def test_같은_씨앗이면_판정_순서가_같다(client, uploads):
    """순서를 다시 만들 수 있어야 한다 — 그래서 씨앗을 묶음에 적는다.

    순위대로 주면 그 순서가 곧 힌트라 섞는데, 섞은 결과를 재현하지 못하면
    "어떤 순서로 판정했는가"를 나중에 말할 수 없다.
    """
    write_diagnosis(uploads, _queue(*[("a.jpg", i, "width", 1 - i / 10)
                                      for i in range(8)]))
    client.post(f"/api/datasets/{DATASET}/evaluations",
                json={"evaluation_id": "s1", "shuffle_seed": 7})
    first = client.get(f"/api/datasets/{DATASET}/evaluations/s1/queue").json()
    again = client.get(f"/api/datasets/{DATASET}/evaluations/s1/queue").json()
    assert [c["canonical_candidate_id"] for c in first["candidates"]] ==            [c["canonical_candidate_id"] for c in again["candidates"]]


def test_판정_순서가_진단_순위와_다르다(client, uploads):
    """순위대로 주면 그것이 곧 힌트다."""
    write_diagnosis(uploads, _queue(*[("a.jpg", i, "width", 1 - i / 20)
                                      for i in range(12)]))
    snap = start(client, "s2")
    queue = client.get(f"/api/datasets/{DATASET}/evaluations/s2/queue").json()
    assert [c["canonical_candidate_id"] for c in queue["candidates"]] !=            [c["canonical_candidate_id"] for c in snap["candidates"]]


def test_데이터셋을_지우면_평가_파일도_지워진다(client, uploads):
    """고객 데이터가 무기한 남으면 안 된다 — 평가 파일도 같은 규칙이다."""
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    snap = start(client)
    put(client, snap, [{"canonical_candidate_id":
                        snap["candidates"][0]["canonical_candidate_id"],
                        "verdict": "hit"}])
    assert (uploads / DATASET / "evaluations").is_dir()

    client.delete(f"/api/datasets/{DATASET}")
    assert not (uploads / DATASET).exists()


# ── unique_error_id ──────────────────────────────────────────────────────────

def test_기존_라벨의_오류_id는_서버가_정한다(client, uploads):
    """`suspicion`이 달라도 같은 라벨이면 같은 오류다."""
    write_diagnosis(uploads, _queue(("a.jpg", 3, "width", 0.9),
                                    ("a.jpg", 3, "scale", 0.7)))
    snap = start(client)
    rows = [{"canonical_candidate_id": c["canonical_candidate_id"],
             "verdict": "hit"} for c in snap["candidates"]]
    saved = put(client, snap, rows).json()
    assert {r["unique_error_id"] for r in saved["adjudications"]} == {"a.jpg/L3"}


def test_한_이미지의_서로_다른_누락_객체_둘은_따로_센다(client, uploads):
    write_diagnosis(uploads, _queue(("a.jpg", None, "missing", 0.9),
                                    ("a.jpg", None, "missing", 0.8)))
    snap = start(client)
    ids = [c["canonical_candidate_id"] for c in snap["candidates"]]
    rows = [{"canonical_candidate_id": ids[0], "verdict": "hit",
             "unique_error_id": "M1"},
            {"canonical_candidate_id": ids[1], "verdict": "hit",
             "unique_error_id": "M2"}]
    saved = put(client, snap, rows).json()
    assert {r["unique_error_id"] for r in saved["adjudications"]} == {
        "a.jpg/M1", "a.jpg/M2"}


def test_같은_누락_객체를_가리키는_후보_둘은_한_오류다(client, uploads):
    """겹쳐 잡은 후보 둘을 서로 다른 오류로 세면 고유 오류 수가 부풀려진다."""
    write_diagnosis(uploads, _queue(("a.jpg", None, "missing", 0.9),
                                    ("a.jpg", None, "missing", 0.8)))
    snap = start(client)
    ids = [c["canonical_candidate_id"] for c in snap["candidates"]]
    rows = [{"canonical_candidate_id": i, "verdict": "hit",
             "unique_error_id": "M1"} for i in ids]
    saved = put(client, snap, rows).json()
    assert {r["unique_error_id"] for r in saved["adjudications"]} == {"a.jpg/M1"}


def test_누락_hit인데_객체를_안_정하면_저장을_거부한다(client, uploads):
    """조용히 후보 id로 대신하지 않는다."""
    write_diagnosis(uploads, _queue(("a.jpg", None, "missing", 0.9)))
    snap = start(client)
    r = put(client, snap, [{"canonical_candidate_id":
                            snap["candidates"][0]["canonical_candidate_id"],
                            "verdict": "hit"}])
    assert r.status_code == 400
    assert not (uploads / DATASET / "evaluations" / "e1"
                / "adjudications.json").exists()


def test_miss와_hold에는_오류_id를_안_붙인다(client, uploads):
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9),
                                    ("a.jpg", 1, "width", 0.8)))
    snap = start(client)
    ids = [c["canonical_candidate_id"] for c in snap["candidates"]]
    saved = put(client, snap,
                [{"canonical_candidate_id": ids[0], "verdict": "miss"},
                 {"canonical_candidate_id": ids[1], "verdict": "hold"}]).json()
    assert all(r["unique_error_id"] is None for r in saved["adjudications"])


def test_hit_miss_hold가_모두_저장된다(client, uploads):
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9),
                                    ("a.jpg", 1, "width", 0.8),
                                    ("a.jpg", 2, "width", 0.7)))
    snap = start(client)
    ids = [c["canonical_candidate_id"] for c in snap["candidates"]]
    put(client, snap, [{"canonical_candidate_id": i, "verdict": v}
                       for i, v in zip(ids, ["hit", "miss", "hold"])])
    queue = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").json()
    got = {c["canonical_candidate_id"]: c["verdict"] for c in queue["candidates"]}
    assert [got[i] for i in ids] == ["hit", "miss", "hold"]


# ── 저장 안전성 ──────────────────────────────────────────────────────────────

def test_판정을_취소하고_다시_저장할_수_있다(client, uploads):
    """`None`은 "아직 안 봤다"이고 `hold`와 다르다."""
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    snap = start(client)
    cid = snap["candidates"][0]["canonical_candidate_id"]
    put(client, snap, [{"canonical_candidate_id": cid, "verdict": "hit"}])
    put(client, snap, [{"canonical_candidate_id": cid, "verdict": None}])
    queue = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").json()
    assert queue["candidates"][0]["verdict"] is None
    assert queue["candidates"][0]["unique_error_id"] is None


def test_저장에_실패해도_기존_판정이_남는다(client, uploads, monkeypatch):
    """**실패를 진짜 저장 지점에서 만든다.**

    `_write_atomic`을 통째로 가짜로 바꾸면 OSError를 500으로 바꾸는 층까지 같이
    사라져, 검사가 실제로 도는 코드를 안 지나간다.
    """
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    snap = start(client)
    cid = snap["candidates"][0]["canonical_candidate_id"]
    put(client, snap, [{"canonical_candidate_id": cid, "verdict": "hit"}])

    def boom(self, target):
        raise OSError("디스크 없음")

    # `undo()`가 아니라 context를 쓴다 — monkeypatch는 함수마다 하나라, undo()는
    # uploads 픽스처가 건 UPLOADS_DIR까지 같이 되돌린다.
    with monkeypatch.context() as m:
        m.setattr(Path, "replace", boom)
        r = put(client, snap,
                [{"canonical_candidate_id": cid, "verdict": "miss"}])
        assert r.status_code == 500

    eval_files = uploads / DATASET / "evaluations" / "e1"
    # 임시 파일을 남기지 않는다.
    assert not list(eval_files.glob("*.tmp"))

    queue = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").json()
    assert queue["candidates"][0]["verdict"] == "hit"

    # 재시도는 성공한다.
    assert put(client, snap,
               [{"canonical_candidate_id": cid, "verdict": "miss"}]).status_code == 200
    queue = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").json()
    assert queue["candidates"][0]["verdict"] == "miss"


def test_다른_묶음에_붙은_판정은_안_읽는다(client, uploads):
    """되살리면 무엇을 가리키는지 알 수 없다."""
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    snap = start(client)
    cid = snap["candidates"][0]["canonical_candidate_id"]
    put(client, snap, [{"canonical_candidate_id": cid, "verdict": "hit"}])

    path = uploads / DATASET / "evaluations" / "e1" / "adjudications.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["candidate_set_hash"] = "다른묶음"
    path.write_text(json.dumps(saved), encoding="utf-8")

    assert client.get(
        f"/api/datasets/{DATASET}/evaluations/e1/queue").status_code == 409


def test_바뀐_묶음_해시로는_저장하지_않는다(client, uploads):
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    snap = start(client)
    cid = snap["candidates"][0]["canonical_candidate_id"]
    r = client.put(
        f"/api/datasets/{DATASET}/evaluations/e1/adjudications",
        json={"candidate_set_hash": "옛것",
              "adjudications": [{"canonical_candidate_id": cid,
                                 "verdict": "hit"}]})
    assert r.status_code == 409


def test_깨진_판정_파일을_빈_판정으로_위장하지_않는다(client, uploads):
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    snap = start(client)
    cid = snap["candidates"][0]["canonical_candidate_id"]
    put(client, snap, [{"canonical_candidate_id": cid, "verdict": "hit"}])

    (uploads / DATASET / "evaluations" / "e1" / "adjudications.json").write_text(
        "{깨짐", encoding="utf-8")
    queue = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").json()
    assert queue["damaged"] is True


def test_묶음에_없는_후보는_거부한다(client, uploads):
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    snap = start(client)
    r = put(client, snap, [{"canonical_candidate_id": "없는것",
                            "verdict": "hit"}])
    assert r.status_code == 400


def test_같은_후보가_두_번_오면_거부한다(client, uploads):
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    snap = start(client)
    cid = snap["candidates"][0]["canonical_candidate_id"]
    r = put(client, snap, [{"canonical_candidate_id": cid, "verdict": "hit"},
                           {"canonical_candidate_id": cid, "verdict": "miss"}])
    assert r.status_code == 400


# ── 내보내기 ─────────────────────────────────────────────────────────────────

def test_점수가_없는_방법을_넣으면_내보내기를_막는다(client, uploads):
    """누락 후보의 단순 IoU 기준선 점수는 **아직 정해지지 않았다.**

    임의 공식을 만들면 그건 IoU 기준선이 아닌 다른 것을 재게 된다.
    """
    write_diagnosis(uploads, _queue(("a.jpg", None, "missing", 0.9)))
    snap = start(client)
    r = client.get(f"/api/datasets/{DATASET}/evaluations/e1/export"
                   "?methods=aida,iou_baseline")
    assert r.status_code == 409
    assert "정해지지 않" in r.json()["detail"]


def test_후보_집합이_다르면_내보내기를_막는다(client, uploads):
    """정렬 효과는 같은 후보 안에서만 잰다."""
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    snap = start(client)
    path = uploads / DATASET / "evaluations" / "e1" / "snapshot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["candidates"][0]["scores"] = {"aida": 0.9}
    data["candidates"].append({**data["candidates"][0],
                               "canonical_candidate_id": "b.jpg/L0#width",
                               "image": "b.jpg",
                               "scores": {"aida": 0.5, "iou_baseline": 0.4}})
    path.write_text(json.dumps(data), encoding="utf-8")

    r = client.get(f"/api/datasets/{DATASET}/evaluations/e1/export"
                   "?methods=aida,iou_baseline")
    assert r.status_code == 409


def test_내보낸_JSON을_집계_모듈이_그대로_받는다(client, uploads):
    """어댑터를 거쳐 손계산과 맞는지 본다.

    후보 셋 중 둘이 같은 라벨(`a.jpg/L3`)이고 하나는 다른 라벨이다.
    **판정 hit는 셋인데 고유 오류는 둘이다.**
    """
    write_diagnosis(uploads, _queue(("a.jpg", 3, "width", 0.9),
                                    ("a.jpg", 3, "scale", 0.8),
                                    ("a.jpg", 5, "width", 0.7)))
    snap = start(client)
    ids = [c["canonical_candidate_id"] for c in snap["candidates"]]
    put(client, snap, [{"canonical_candidate_id": i, "verdict": "hit"}
                       for i in ids])

    export = client.get(
        f"/api/datasets/{DATASET}/evaluations/e1/export?methods=aida").json()

    from evaluation.importer import load_export
    from evaluation.summary import summarise

    adjudications, rankings = load_export(export)
    result = summarise(adjudications, rankings, "aida", budget=3)
    assert result.in_budget == 3
    assert result.hit_candidates == 3
    # **판정 hit는 셋인데 고유 오류는 둘이다.**
    assert result.unique_error_yield == 2
