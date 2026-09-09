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
             # 상자는 줄마다 다르게 준다. 후보 이름이 (이미지, 라벨, 유형,
             # 상자)의 요약이라 같은 상자를 주면 서로 다른 누락 객체가 같은
             # 후보가 된다 — 현실에서는 있을 수 없는 입력이다.
             "severity": sev, "detail": "",
             "box": [10.0 + i, 10.0 + i, 60.0 + i, 60.0 + i],
             **({} if len(row) < 5 else {"label_iou": row[4]})}
            for i, row in enumerate(items)
            for im, li, s, sev in [row[:4]]
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

def test_비교군이_없는_층에_기준선을_붙이면_막는다(client, uploads):
    """누락 후보의 단순 IoU 기준선 점수는 **아직 정해지지 않았다.**

    기준선을 붙일 수 있게 두면, 그 자체로 "견줄 수 있다"는 뜻이 되어 버린다.
    """
    write_diagnosis(uploads, _queue(("a.jpg", None, "missing", 0.9)))
    start(client)
    r = client.get(f"/api/datasets/{DATASET}/evaluations/e1/export"
                   "?methods=aida,iou_baseline&scope=missing_candidates")
    assert r.status_code == 409
    assert "비교군이 없습니다" in r.json()["detail"]


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

    adjudications, rankings = load_export(export, require_comparison=True)
    result = summarise(adjudications, rankings, "aida", budget=3)
    assert result.in_budget == 3
    assert result.hit_candidates == 3
    # **판정 hit는 셋인데 고유 오류는 둘이다.**
    assert result.unique_error_yield == 2


# ── 단순 불일치 기준선 ────────────────────────────────────────────────────────

def test_기준선_점수는_안_맞을수록_높다(client, uploads):
    """`1 - IoU`. 이 한 줄이 기준선의 전부다."""
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9, 0.8),
                                    ("a.jpg", 1, "scale", 0.2, 0.3)))
    snap = start(client)
    got = {c["canonical_candidate_id"]: c["scores"] for c in snap["candidates"]}
    scores = sorted(s["iou_baseline"] for s in got.values())
    assert scores == [0.2, 0.7]


def test_기준선은_유형을_모른다(client, uploads):
    """같은 라벨을 두 유형이 지목해도 기준선 점수는 같다.

    유형별로 다르게 굴면 그건 이미 단순한 규칙이 아니고, 우리 방법과 비교하는
    뜻이 사라진다.
    """
    write_diagnosis(uploads, _queue(("a.jpg", 3, "width", 0.9, 0.4),
                                    ("a.jpg", 3, "scale", 0.2, 0.4)))
    snap = start(client)
    assert {c["scores"]["iou_baseline"] for c in snap["candidates"]} == {0.6}


def test_기준선_점수가_없는_옛_진단은_내보내기를_막는다(client, uploads):
    """옛 결과 파일에는 `label_iou`가 없다. 조용히 0점을 주지 않는다."""
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9)))
    start(client)
    r = client.get(f"/api/datasets/{DATASET}/evaluations/e1/export"
                   "?methods=aida,iou_baseline")
    assert r.status_code == 409


def test_누락_후보를_뺀_것을_결과에_적는다(client, uploads):
    """**거른 것을 조용히 넘기지 않는다.**

    안 적으면 나중에 그 숫자가 무엇을 뺀 값인지 아무도 모른다.
    """
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9, 0.4),
                                    ("a.jpg", None, "missing", 0.8)))
    start(client)
    got = client.get(f"/api/datasets/{DATASET}/evaluations/e1/export"
                     "?methods=aida,iou_baseline").json()

    assert got["requested_scope"] == "labelled_candidates"
    assert got["total_candidates"] == 2
    assert got["included_candidates"] == 1
    assert got["excluded_candidates"] == 1
    assert sum(got["exclusion_reasons"].values()) == 1
    assert got["comparison_allowed"] is True
    assert "조건부 재정렬 효과" in got["comparison_limitation"]


def test_누락_층은_비교를_허용하지_않는다(client, uploads):
    """AIDA 순위와 판정은 내보내되 **성공 판정은 만들지 않는다.**"""
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9, 0.4),
                                    ("a.jpg", None, "missing", 0.8)))
    start(client)
    got = client.get(f"/api/datasets/{DATASET}/evaluations/e1/export"
                     "?scope=missing_candidates").json()

    assert got["included_candidates"] == 1
    assert got["comparison_allowed"] is False
    assert got["descriptive_only"] is True
    assert [a["label_index"] for a in got["adjudications"]] == [None]


def test_전체_층은_현황용이고_비교에_안_쓴다(client, uploads):
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9, 0.4),
                                    ("a.jpg", None, "missing", 0.8)))
    start(client)
    got = client.get(f"/api/datasets/{DATASET}/evaluations/e1/export"
                     "?scope=all_descriptive").json()

    assert got["included_candidates"] == 2
    assert got["excluded_candidates"] == 0
    assert got["comparison_allowed"] is False


def test_모르는_층은_거부한다(client, uploads):
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9, 0.4)))
    start(client)
    r = client.get(f"/api/datasets/{DATASET}/evaluations/e1/export"
                   "?scope=아무거나")
    assert r.status_code == 409


def test_기존_라벨만이면_두_방법을_함께_내보낸다(client, uploads):
    """설계 문서의 1안(기존 라벨 후보만으로 주 비교)이 실제로 도는지 본다.

    **어느 안을 고른 것이 아니다** — 고를 수 있게 된 것이다.
    """
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9, 0.9),
                                    ("a.jpg", 1, "width", 0.3, 0.1)))
    snap = start(client)
    ids = [c["canonical_candidate_id"] for c in snap["candidates"]]
    put(client, snap, [{"canonical_candidate_id": i, "verdict": v}
                       for i, v in zip(ids, ["miss", "hit"])])

    export = client.get(f"/api/datasets/{DATASET}/evaluations/e1/export"
                        "?methods=aida,iou_baseline").json()

    from evaluation.importer import load_export
    from evaluation.summary import summarise

    # **비교로 읽는다** — 층이 비교를 허용하는지 집계가 직접 확인한다.
    adjudications, rankings = load_export(export, require_comparison=True)
    # 예산 1건: AIDA는 severity가 높은 쪽(오류 아님)을, 기준선은 IoU가 낮은
    # 쪽(오류)을 먼저 본다. **같은 후보 집합에서 순서만 다르다.**
    aida = summarise(adjudications, rankings, "aida", budget=1)
    base = summarise(adjudications, rankings, "iou_baseline", budget=1)
    assert aida.unique_error_yield == 0
    assert base.unique_error_yield == 1


# ── 작업 기록 (docs/pilot-evaluation-plan.md) ────────────────────────────────


def _event(second, name, cid=None, session="s1", seq=0, event_id=None, **meta):
    return {"session_id": session, "event": name,
            "event_id": event_id or f"e{seq}",
            "sequence": seq,
            "canonical_candidate_id": cid,
            "at": "2026-09-09T00:00:00+00:00",
            "elapsed_ms": int(second * 1000), "meta": meta}


def _post(client, snap, events, evaluation_id="e1"):
    return client.post(
        f"/api/datasets/{DATASET}/evaluations/{evaluation_id}/activity",
        json={"candidate_set_hash": snap["candidate_set_hash"],
              "events": events})


def _lines(uploads, evaluation_id="e1"):
    path = (uploads / DATASET / "evaluations" / evaluation_id / "activity.jsonl")
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def pilot(client, uploads):
    """후보 하나짜리 평가. 기록 검사에 쓰는 최소 무대."""
    write_diagnosis(uploads, _queue(("a.jpg", 0, "width", 0.9, 0.4)))
    snap = start(client)
    return snap, snap["candidates"][0]["canonical_candidate_id"]


def test_작업_기록은_이어붙인다(client, uploads, pilot):
    """덮어쓰지 않는다 — 기록은 지난 일이라 나중 것이 앞의 것을 무효로 하지 않는다."""
    snap, cid = pilot
    _post(client, snap, [_event(0, "session_started", seq=0)])
    _post(client, snap, [_event(5, "verdict_set", cid, seq=1, verdict="hit")])

    assert [r["event"] for r in _lines(uploads)] == ["session_started",
                                                     "verdict_set"]


def test_기록에_서버가_아는_것은_서버가_채운다(client, uploads, pilot):
    """화면이 보낸 값을 그대로 믿지 않는다."""
    snap, _ = pilot
    bogus = {**_event(0, "session_started", seq=0),
             "evaluation_id": "다른평가", "candidate_set_hash": "다른묶음",
             "event_schema_version": 99}
    _post(client, snap, [bogus])

    row = _lines(uploads)[0]
    assert row["evaluation_id"] == "e1"
    assert row["candidate_set_hash"] == snap["candidate_set_hash"]
    assert row["event_schema_version"] == 1


def test_다른_묶음의_기록은_안_받는다(client, uploads, pilot):
    """다른 후보 목록에서 잰 시간이다."""
    r = client.post(f"/api/datasets/{DATASET}/evaluations/e1/activity",
                    json={"candidate_set_hash": "옛것",
                          "events": [_event(0, "session_started")]})
    assert r.status_code == 409


def test_기록이_판정_파일을_건드리지_않는다(client, uploads, pilot):
    """수명도 쓰임도 다르다. 한 파일에 두면 판정을 고칠 때마다 기록도 다시 쓴다."""
    snap, cid = pilot
    put(client, snap, [{"canonical_candidate_id": cid, "verdict": "hit"}])
    before = (uploads / DATASET / "evaluations" / "e1"
              / "adjudications.json").read_text(encoding="utf-8")

    _post(client, snap, [_event(0, "session_started")])

    after = (uploads / DATASET / "evaluations" / "e1"
             / "adjudications.json").read_text(encoding="utf-8")
    assert before == after


def test_기록이_한_번에_너무_많으면_거부한다(client, uploads, pilot):
    snap, _ = pilot
    r = _post(client, snap, [_event(i, "moved_next", seq=i) for i in range(501)])
    assert r.status_code == 413


# ── 중복 방지 ────────────────────────────────────────────────────────────────

def test_같은_event_id를_다시_받으면_안_넣는다(client, uploads, pilot):
    """응답이 유실되면 화면이 같은 묶음을 다시 보낸다.

    두 벌이 남으면 판정 횟수가 부풀고 순번이 겹쳐 그 세션이 손상으로 잡힌다.
    """
    snap, cid = pilot
    batch = [_event(0, "session_started", seq=0, event_id="a"),
             _event(3, "verdict_set", cid, seq=1, event_id="b", verdict="hit")]

    first = _post(client, snap, batch).json()
    second = _post(client, snap, batch).json()

    assert first["appended"] == 2 and first["deduplicated"] == 0
    assert second["appended"] == 0 and second["deduplicated"] == 2
    assert len(_lines(uploads)) == 2


def test_걸러낸_것도_확인해_준다(client, uploads, pilot):
    """안 그러면 화면이 로컬 큐에서 못 지우고 영영 다시 보낸다."""
    snap, _ = pilot
    batch = [_event(0, "session_started", seq=0, event_id="a")]
    _post(client, snap, batch)
    again = _post(client, snap, batch).json()
    assert again["acknowledged"] == ["a"]


def test_한_요청_안에_같은_event_id가_두_번이면_거부한다(client, uploads, pilot):
    snap, _ = pilot
    r = _post(client, snap, [_event(0, "session_started", seq=0, event_id="a"),
                             _event(1, "moved_next", seq=1, event_id="a")])
    assert r.status_code == 400


# ── 스키마 검증 ──────────────────────────────────────────────────────────────

def test_모르는_이벤트_이름을_거부한다(client, uploads, pilot):
    """오타 하나가 조용히 들어가면 그 구간이 무엇이었는지 알 수 없다."""
    snap, _ = pilot
    r = _post(client, snap, [_event(0, "sesion_started", seq=0)])
    assert r.status_code == 400
    assert "모르는 이벤트" in r.json()["detail"]


def test_묶음에_없는_후보를_거부한다(client, uploads, pilot):
    """얼린 목록에 없는 후보의 시간은 어디에도 못 붙인다."""
    snap, _ = pilot
    r = _post(client, snap, [_event(0, "candidate_opened", "없는후보", seq=0)])
    assert r.status_code == 400


def test_후보_이벤트에_후보가_없으면_거부한다(client, uploads, pilot):
    snap, _ = pilot
    r = _post(client, snap, [_event(0, "verdict_set", None, seq=0,
                                    verdict="hit")])
    assert r.status_code == 400


def test_저장_이벤트는_후보가_없어도_된다(client, uploads, pilot):
    snap, _ = pilot
    assert _post(client, snap,
                 [_event(0, "save_started", seq=0)]).status_code == 200


@pytest.mark.parametrize("event,meta", [
    ("visibility_changed", {}),
    ("visibility_changed", {"visible": "yes"}),
    ("focus_changed", {}),
    ("verdict_set", {"verdict": "아무거나"}),
])
def test_이벤트별_필수_metadata를_확인한다(client, uploads, pilot, event, meta):
    snap, cid = pilot
    row = _event(0, event, cid if event == "verdict_set" else None, seq=0)
    row["meta"] = meta
    assert _post(client, snap, [row]).status_code == 400


@pytest.mark.parametrize("field,value", [
    ("elapsed_ms", -1),
    ("elapsed_ms", "빠름"),
    ("sequence", -1),
    ("sequence", 1.5),
    ("session_id", "안 되는 아이디"),
    ("event_id", ""),
    ("at", "언젠가"),
])
def test_형식이_틀린_값을_거부한다(client, uploads, pilot, field, value):
    snap, _ = pilot
    row = _event(0, "session_started", seq=0)
    row[field] = value
    assert _post(client, snap, [row]).status_code == 400


def test_meta가_너무_크면_거부한다(client, uploads, pilot):
    snap, _ = pilot
    row = _event(0, "session_started", seq=0)
    row["meta"] = {"긴것": "가" * 3000}
    assert _post(client, snap, [row]).status_code == 400


def test_한_건이_틀리면_요청_전체를_거부한다(client, uploads, pilot):
    """일부만 저장하면 기록에 구멍이 남는데 화면은 성공으로 알고 다시 안 보낸다."""
    snap, _ = pilot
    r = _post(client, snap, [_event(0, "session_started", seq=0, event_id="a"),
                             _event(1, "없는이벤트", seq=1, event_id="b")])
    assert r.status_code == 400
    assert _lines(uploads) == []


def test_기록을_집계_모듈이_그대로_읽는다(client, uploads, pilot):
    """저장한 것과 계산하는 것이 같은 모양인지 본다."""
    snap, cid = pilot
    _post(client, snap, [
        _event(0, "session_started", seq=0, event_id="a"),
        _event(0, "candidate_opened", cid, seq=1, event_id="b"),
        _event(8, "verdict_set", cid, seq=2, event_id="c", verdict="hit"),
        _event(8, "session_ended", seq=3, event_id="d"),
    ])

    from evaluation.activity import read_events, summarise_activity
    path = uploads / DATASET / "evaluations" / "e1" / "activity.jsonl"
    got = summarise_activity(read_events(path.read_text(encoding="utf-8")))
    assert got.judged_candidates == 1
    assert got.active_seconds == 8.0
    assert got.complete_sessions == 1


def test_서버와_집계의_이벤트_이름이_같다():
    """한쪽만 늘리면 받아 놓고 못 읽거나, 못 받는데 읽을 줄 아는 상태가 된다."""
    from evaluation.activity import KNOWN_EVENTS as AGGREGATE_EVENTS
    from app.routers.evaluation import KNOWN_EVENTS as SERVER_EVENTS
    assert SERVER_EVENTS == AGGREGATE_EVENTS
