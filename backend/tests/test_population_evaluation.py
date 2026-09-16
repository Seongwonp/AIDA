"""후보 생성까지 포함한 평가 — 모집단이 방법마다 다르다 (docs/next-work-2026-09-15.md W3).

prelim1은 **AIDA가 고른 후보 안에서만** 두 순서를 견줬다. Q-A는 그 밖을 묻는다 —
규칙이 놓친 라벨에 오류가 얼마나 있나. Q-C는 누락 필터가 버린 예측을 묻는다.

**손계산 세계.**

| 후보 | 층 | AIDA | `label_iou` | 1 − IoU | 확신도 |
|---|---|---|---|---|---|
| a.png L0 (width) | 기존 라벨 | 순위 1 | 0.40 | 0.60 | — |
| a.png L1 | 기존 라벨 | **아님** | 0.10 | 0.90 | — |
| b.png L0 (scale) | 기존 라벨 | 순위 2 | 0.20 | 0.80 | — |
| b.png L1 | 기존 라벨 | **아님** | 0.95 | 0.05 | — |
| a.png [50,50,60,60] | 누락 | 순위 3 | — | — | 0.90 |
| a.png [70,70,80,80] | 누락 | **아님**(확신도 낮음) | — | — | 0.30 |
| b.png [10,10,20,20] | 누락 | **아님** | — | — | 0.65 |

방법별 순서 — `aida`: L0(a) → L0(b). `iou_baseline`(AIDA 후보 안): L0(b) 0.80 → L0(a) 0.60.
`all_label_iou`(모든 라벨): L1(a) 0.90 → L0(b) 0.80 → L0(a) 0.60 → L1(b) 0.05.
`unmatched_confidence`(필터 전 전부): a[50] 0.90 → b[10] 0.65 → a[70] 0.30.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import evaluation as E
from app.routers import upload

DATASET = "0123456789ab"


def candidate(rank, image, label_index, suspicion, severity, label_iou=None, box=None):
    row = {"rank": rank, "image": image, "label_index": label_index,
           "suspicion": suspicion, "severity": severity, "detail": "",
           "box": box or [10.0, 10.0, 60.0, 60.0], "class_name": "Car"}
    if label_iou is not None:
        row["label_iou"] = label_iou
    return row


AIDA_CANDIDATES = [
    candidate(1, "a.png", 0, "width", 0.9, 0.40),
    candidate(2, "b.png", 0, "scale", 0.5, 0.20),
    candidate(3, "a.png", None, "missing", 0.7, box=[50.0, 50.0, 60.0, 60.0]),
]
ALL_LABELS = [
    {"image": "a.png", "label_index": 0, "box": [10.0, 10.0, 60.0, 60.0],
     "label_iou": 0.40, "class_name": "Car"},
    {"image": "a.png", "label_index": 1, "box": [20.0, 20.0, 70.0, 70.0],
     "label_iou": 0.10, "class_name": "Car"},
    {"image": "b.png", "label_index": 0, "box": [10.0, 10.0, 60.0, 60.0],
     "label_iou": 0.20, "class_name": "Car"},
    {"image": "b.png", "label_index": 1, "box": [30.0, 30.0, 80.0, 80.0],
     "label_iou": 0.95, "class_name": "Car"},
]
UNMATCHED = [
    {"image": "a.png", "label_index": None, "box": [50.0, 50.0, 60.0, 60.0],
     "confidence": 0.90, "covered_ratio": 0.0, "class_name": "Car"},
    {"image": "a.png", "label_index": None, "box": [70.0, 70.0, 80.0, 80.0],
     "confidence": 0.30, "covered_ratio": 0.0, "class_name": "Car"},
    {"image": "b.png", "label_index": None, "box": [10.0, 10.0, 20.0, 20.0],
     "confidence": 0.65, "covered_ratio": 0.9, "class_name": "Car"},
]


def diagnosis(with_population=True) -> dict:
    data = {"dataset": DATASET, "generated_at": "2026-09-16T00:00:00+00:00",
            "summary": {}, "caveat": "", "review_queue": AIDA_CANDIDATES,
            "all_candidates": AIDA_CANDIDATES, "total_in_queue": len(AIDA_CANDIDATES)}
    if with_population:
        data["all_labels"] = ALL_LABELS
        data["unmatched_predictions"] = UNMATCHED
    return data


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    monkeypatch.setattr(E, "UPLOADS_DIR", root)
    monkeypatch.setattr(upload, "UPLOADS_DIR", root)
    (root / DATASET).mkdir(parents=True)
    return root


@pytest.fixture
def client(uploads):
    return TestClient(app)


def write(uploads, data):
    (uploads / DATASET / "label_diagnosis.json").write_text(json.dumps(data), encoding="utf-8")


def start(client, **body):
    r = client.post(f"/api/datasets/{DATASET}/evaluations", json={"evaluation_id": "e1", **body})
    assert r.status_code == 200, r.text
    return r.json()


def by_key(snap):
    out = {}
    for c in snap["candidates"]:
        if c["label_index"] is not None:
            out[f"{c['image']}#{c['label_index']}"] = c
        else:
            out[f"{c['image']}#{c['box'][0]}"] = c
    return out


# ── 묶음에 무엇이 얼려지나 ────────────────────────────────────────────────────

def test_규칙에_안_걸린_라벨과_버려진_예측도_얼린다(client, uploads):
    write(uploads, diagnosis())
    snap = start(client)
    labelled = [c for c in snap["candidates"] if c["label_index"] is not None]
    missing = [c for c in snap["candidates"] if c["label_index"] is None]
    assert len(labelled) == 4 and len(missing) == 3
    assert sorted(c["source"] for c in labelled) == [
        "aida_candidate", "aida_candidate", "label", "label"]
    assert sorted(c["source"] for c in missing) == [
        "aida_candidate", "unmatched_prediction", "unmatched_prediction"]


def test_AIDA가_고른_라벨은_두_번_얼리지_않는다(client, uploads):
    """같은 라벨이 후보 목록과 모집단 양쪽에 있다. 둘로 얼리면 판정자가 같은 상자를
    두 번 보고, 한 오류가 두 번 세어질 자리를 만든다."""
    write(uploads, diagnosis())
    snap = start(client)
    keys = [(c["image"], c["label_index"]) for c in snap["candidates"]
            if c["label_index"] is not None]
    assert len(keys) == len(set(keys))
    flagged = by_key(snap)["a.png#0"]
    assert flagged["source"] == "aida_candidate"
    assert flagged["suspicion"] == "width" and flagged["aida_rank"] == 1
    # 같은 후보가 두 방법의 점수를 모두 갖는다
    assert flagged["scores"]["iou_baseline"] == 0.6
    assert flagged["scores"]["all_label_iou"] == 0.6


def test_AIDA_누락_후보는_상자로_모집단과_이어진다(client, uploads):
    write(uploads, diagnosis())
    snap = start(client)
    aida_missing = [c for c in snap["candidates"]
                    if c["label_index"] is None and c["source"] == "aida_candidate"]
    assert len(aida_missing) == 1
    assert aida_missing[0]["box"] == [50.0, 50.0, 60.0, 60.0]
    assert aida_missing[0]["confidence"] == 0.9
    assert aida_missing[0]["scores"]["unmatched_confidence"] == 0.9


def test_AIDA_후보의_이름은_모집단이_생겨도_그대로다(uploads):
    """이름이 바뀌면 옛 판정이 무엇을 가리키는지 잃는다."""
    before = E.build_snapshot(DATASET, "e0", diagnosis(with_population=False))
    after = E.build_snapshot(DATASET, "e1", diagnosis())
    old = {c.canonical_candidate_id for c in before.candidates}
    new = {c.canonical_candidate_id for c in after.candidates}
    assert old < new
    assert before.candidate_set_hash != after.candidate_set_hash


def test_모집단이_없는_옛_진단은_예전_그대로다(client, uploads):
    write(uploads, diagnosis(with_population=False))
    snap = start(client)
    assert len(snap["candidates"]) == 3
    assert {c["source"] for c in snap["candidates"]} == {"aida_candidate"}


# ── 판정 대상 ─────────────────────────────────────────────────────────────────

def test_예산_안의_판정_대상은_방법마다_자기_모집단에서_뽑는다(client, uploads):
    """N=1. 기존 라벨 층: aida→a.L0, iou_baseline→b.L0, all_label_iou→a.L1.
    누락 층: aida와 unmatched_confidence가 **같은 후보**(a[50])를 고른다 → 한 번만."""
    write(uploads, diagnosis())
    start(client, judge_budget=1)
    queue = client.get(f"/api/datasets/{DATASET}/evaluations/e1/queue").json()
    keys = sorted(f"{c['image']}#{c['label_index']}" for c in queue["candidates"])
    assert keys == ["a.png#0", "a.png#1", "a.png#None", "b.png#0"]


def test_방법의_모집단이_예산보다_작으면_남는_예산을_안_쓴다(client, uploads):
    """AIDA 후보는 기존 라벨 층에 2건뿐이다. N=3이어도 AIDA가 3건을 채우려고
    규칙 밖 라벨을 끌어오지 않는다 — 그러면 AIDA가 안 만든 후보가 AIDA의 성과가 된다.

    손계산(N=3) — 기존 라벨 층: aida {a.L0, b.L0}, iou_baseline {b.L0, a.L0},
    all_label_iou 상위 3 {a.L1, b.L0, a.L0} → 합집합 3건(**b.L1 0.05는 안 든다**).
    누락 층: aida {a[50]}, unmatched_confidence 상위 3 = 3건 전부 → 3건. 합쳐서 6건."""
    write(uploads, diagnosis())
    start(client, judge_budget=3)
    snap = E.load_snapshot(DATASET, "e1")
    labelled = [c for c in snap.candidates if c.label_index is not None]
    assert len(E.method_order(labelled, "aida")) == 2
    assert len(E.judge_ids(snap)) == 6


def test_무작위_표본은_규칙_밖_라벨에서_뽑고_표시를_남긴다(client, uploads):
    write(uploads, diagnosis())
    snap = start(client, judge_budget=1, random_sample_size=1, random_sample_seed=7)
    sampled = [c for c in snap["candidates"] if c["random_sample"]]
    assert len(sampled) == 1
    assert sampled[0]["source"] == "label"          # AIDA가 고른 후보는 표본이 아니다
    assert snap["random_sample_size"] == 1 and snap["random_sample_seed"] == 7
    assert sampled[0]["canonical_candidate_id"] in E.judge_ids(E.load_snapshot(DATASET, "e1"))


def test_무작위_표본은_씨앗으로_다시_만들_수_있다(uploads):
    def sample(seed):
        snap = E.build_snapshot(DATASET, "e1", diagnosis(), judge_budget=1,
                                random_sample_size=1, random_sample_seed=seed)
        return {c.canonical_candidate_id for c in snap.candidates if c.random_sample}
    assert sample(7) == sample(7)
    assert sample(7) != sample(8)


def test_표본이_모집단보다_크면_거부한다(client, uploads):
    write(uploads, diagnosis())
    r = client.post(f"/api/datasets/{DATASET}/evaluations",
                    json={"evaluation_id": "e2", "random_sample_size": 99,
                          "random_sample_seed": 1})
    assert r.status_code == 400


def test_상자가_같은_미매칭_예측이_둘이면_얼리지_않는다(client, uploads):
    """판정 화면은 이미지와 상자만 보여준다. 상자가 같으면 판정자가 둘을 구분할 수 없고,
    후보 이름에도 클래스가 없다(옛 지문과 호환되어야 한다). 조용히 하나를 덮어쓰면
    그 후보의 확신도와 기준선 점수가 다른 예측의 것이 된다."""
    data = diagnosis()
    data["unmatched_predictions"] = UNMATCHED + [
        {"image": "a.png", "label_index": None, "box": [50.0, 50.0, 60.0, 60.0],
         "confidence": 0.40, "covered_ratio": 0.0, "class_name": "Pedestrian"}]
    write(uploads, data)
    r = client.post(f"/api/datasets/{DATASET}/evaluations", json={"evaluation_id": "e1"})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "a.png" in detail and "상자" in detail


def test_무작위_표본은_방법의_순서나_예산을_바꾸지_않는다(uploads):
    """표본은 규칙 밖 라벨에서 뽑고, 그 라벨은 `all_label_iou`의 모집단이기도 하다.
    **표본에서 빼면 그 방법의 순서가 표본 추출에 따라 흔들린다.** 규칙은 "표본이 방법의
    예산을 쓰지 않는다"이지 "표본을 순위에서 뺀다"가 아니다."""
    plain = E.build_snapshot(DATASET, "e1", diagnosis(), judge_budget=1)
    sampled = E.build_snapshot(DATASET, "e2", diagnosis(), judge_budget=1,
                               random_sample_size=2, random_sample_seed=7)

    def tops(snap):
        labelled = [c for c in snap.candidates if c.label_index is not None]
        return {m: E._top(labelled, E.method_order(labelled, m), 1)
                for m in ("aida", "iou_baseline", "all_label_iou")}

    assert tops(plain) == tops(sampled)          # 순서도 예산 안 후보도 그대로
    # 규칙 밖 라벨 둘을 표본으로 뽑았다. a.L1은 이미 `all_label_iou` 상위 1이라 판정
    # 대상이었고, b.L1(1 − IoU 0.05)만 새로 더해진다 — 예산이 아니라 표본으로 들어온다.
    marked = {c.canonical_candidate_id for c in sampled.candidates if c.random_sample}
    assert len(marked) == 2
    assert marked <= E.judge_ids(sampled)
    assert E.judge_ids(sampled) - E.judge_ids(plain) == {
        E.canonical_id("b.png", 1, "", [30.0, 30.0, 80.0, 80.0])}


# ── 내보내기 ─────────────────────────────────────────────────────────────────

def export(client, methods, scope="labelled_candidates", mode=None):
    url = f"/api/datasets/{DATASET}/evaluations/e1/export?methods={methods}&scope={scope}"
    if mode:
        url += f"&mode={mode}"
    return client.get(url)


def test_기본_모드는_AIDA_후보_안의_재정렬_그대로다(client, uploads):
    """prelim1과 같은 질문이다. 모집단이 생겨도 그 비교는 AIDA 후보 안에서만 센다."""
    write(uploads, diagnosis())
    start(client)
    body = export(client, "aida,iou_baseline").json()
    assert body["comparison_mode"] == "within_aida_candidates"
    assert body["included_candidates"] == 2          # 규칙 밖 라벨은 빠진다
    assert body["comparison_allowed"] is True
    assert {r["method"] for r in body["rankings"]} == {"aida", "iou_baseline"}


def test_AIDA_후보_안_모드에서는_전체_라벨_방법을_막는다(client, uploads):
    write(uploads, diagnosis())
    start(client)
    r = export(client, "aida,all_label_iou")
    assert r.status_code == 409
    assert "candidate_generation_included" in r.json()["detail"]


def test_후보_생성_포함_모드는_방법마다_모집단을_적는다(client, uploads):
    write(uploads, diagnosis())
    start(client)
    body = export(client, "aida,all_label_iou", mode="candidate_generation_included").json()
    assert body["included_candidates"] == 4
    assert body["method_population"] == {"aida": 2, "all_label_iou": 4}
    assert body["comparison_allowed"] is True
    assert "후보 생성" in body["comparison_limitation"]


def test_모집단이_없는_진단으로는_후보_생성_비교를_못_한다(client, uploads):
    write(uploads, diagnosis(with_population=False))
    start(client)
    r = export(client, "aida,all_label_iou", mode="candidate_generation_included")
    assert r.status_code == 409


def test_누락_층_기준선은_보조_기술_통계로만_나간다(client, uploads):
    """Q-C는 1차가 아니다. 비교군이 생겨도 성공·실패 판정에 쓰지 않는다."""
    write(uploads, diagnosis())
    start(client)
    body = export(client, "aida,unmatched_confidence", scope="missing_candidates",
                  mode="candidate_generation_included").json()
    assert body["included_candidates"] == 3
    assert body["method_population"] == {"aida": 1, "unmatched_confidence": 3}
    assert body["comparison_allowed"] is False and body["descriptive_only"] is True


def test_층에_없는_방법은_거부한다(client, uploads):
    write(uploads, diagnosis())
    start(client)
    assert export(client, "all_label_iou", scope="missing_candidates",
                  mode="candidate_generation_included").status_code == 409


def test_내보내기_줄에_출처와_무작위_표본_표시가_실린다(client, uploads):
    write(uploads, diagnosis())
    start(client, judge_budget=1, random_sample_size=1, random_sample_seed=7)
    body = export(client, "aida,all_label_iou", mode="candidate_generation_included").json()
    rows = body["adjudications"]
    assert {r["source"] for r in rows} == {"aida_candidate", "label"}
    assert sum(bool(r["random_sample"]) for r in rows) == 1


# ── 집계까지 ─────────────────────────────────────────────────────────────────

def test_모집단이_다른_두_방법을_집계가_그대로_센다(client, uploads):
    """N=1 손계산. `all_label_iou` 1위는 a.L1(오류), `aida` 1위는 a.L0(오류 아님).
    → 고유 오류 1 대 0."""
    write(uploads, diagnosis())
    snap = start(client)
    ids = by_key(snap)
    verdicts = [
        {"canonical_candidate_id": ids["a.png#0"]["canonical_candidate_id"], "verdict": "miss"},
        {"canonical_candidate_id": ids["a.png#1"]["canonical_candidate_id"], "verdict": "hit"},
        {"canonical_candidate_id": ids["b.png#0"]["canonical_candidate_id"], "verdict": "miss"},
        {"canonical_candidate_id": ids["b.png#1"]["canonical_candidate_id"], "verdict": "miss"},
    ]
    r = client.put(f"/api/datasets/{DATASET}/evaluations/e1/adjudications",
                   json={"candidate_set_hash": snap["candidate_set_hash"],
                         "adjudications": verdicts})
    assert r.status_code == 200, r.text

    from evaluation.importer import load_export
    from evaluation.summary import summarise
    body = export(client, "aida,all_label_iou", mode="candidate_generation_included").json()
    adjudications, rankings = load_export(body, require_comparison=True)
    assert summarise(adjudications, rankings, "all_label_iou", budget=1).unique_error_yield == 1
    assert summarise(adjudications, rankings, "aida", budget=1).unique_error_yield == 0
