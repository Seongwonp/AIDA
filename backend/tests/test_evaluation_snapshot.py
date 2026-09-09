"""평가 묶음의 무결성 — 지문과 후보 이름 (docs/evaluation-adjudication-design.md).

두 가지를 여기서 고정한다.

**지문(`candidate_set_hash`)은 판정에 영향을 주는 것 전부를 덮어야 한다.**
후보 id만 해시하면 같은 id에 박스나 점수가 바뀌어도 지문이 그대로다. 그러면
이미 내린 판정이 **다른 내용의 후보에 그대로 붙는다** — 판정이 무엇을
가리키는지 알 수 없어지는데도 아무도 막지 않는다.

**후보 이름은 목록 순서에 기대면 안 된다.** 순번으로 구분하면 진단이 순서를
바꾸는 것만으로 두 후보의 이름이 서로 뒤바뀐다. 순서 규칙은 실제로 두 번
바뀐 적이 있다(docs/21 AN·AO).
"""
import pytest
from fastapi import HTTPException

from app.routers import evaluation as E

DATASET = "0123456789ab"


def item(image="a.jpg", label_index=0, suspicion="width", severity=0.9,
         box=(10.0, 10.0, 60.0, 60.0), label_iou=0.4) -> dict:
    row = {"rank": 1, "image": image, "label_index": label_index,
           "suspicion": suspicion, "severity": severity, "detail": "",
           "box": list(box)}
    if label_iou is not None:
        row["label_iou"] = label_iou
    return row


def diagnosis(*items, generated_at="2026-09-09T00:00:00+00:00") -> dict:
    return {"dataset_id": DATASET, "generated_at": generated_at,
            "summary": {}, "caveat": "", "review_queue": list(items)}


def build(*items, seed=0, **kw):
    return E.build_snapshot(DATASET, "e1", diagnosis(*items, **kw),
                            shuffle_seed=seed)


# ── 지문이 무엇을 덮는가 ─────────────────────────────────────────────────────

def test_박스만_달라져도_지문이_달라진다():
    """같은 라벨의 같은 유형인데 상자가 다르면 **다른 것을 보라는 뜻**이다."""
    one = build(item(box=(10, 10, 60, 60)))
    two = build(item(box=(11, 10, 60, 60)))
    assert one.candidate_set_hash != two.candidate_set_hash


def test_점수만_달라져도_지문이_달라진다():
    """점수가 바뀌면 순위가 바뀐다. 예산 안에 드는 후보가 달라진다."""
    one = build(item(severity=0.9))
    two = build(item(severity=0.4))
    assert one.candidate_set_hash != two.candidate_set_hash


def test_기준선_점수만_달라져도_지문이_달라진다():
    one = build(item(label_iou=0.4))
    two = build(item(label_iou=0.9))
    assert one.candidate_set_hash != two.candidate_set_hash


def test_섞는_씨앗이_달라지면_지문이_달라진다():
    """판정 순서가 달라지면 같은 묶음이 아니다."""
    assert build(item(), seed=0).candidate_set_hash != \
           build(item(), seed=7).candidate_set_hash


def test_진단_시각이_달라지면_지문이_달라진다():
    """어느 진단을 얼린 것인가가 다르면 다른 묶음이다."""
    one = build(item(), generated_at="2026-09-09T00:00:00+00:00")
    two = build(item(), generated_at="2026-09-10T00:00:00+00:00")
    assert one.candidate_set_hash != two.candidate_set_hash


def test_만든_시각은_지문에_안_들어간다():
    """같은 진단을 두 번 얼리면 같은 지문이어야 한다.

    실행할 때마다 달라지는 값이 들어가면 지문이 "내용이 같은가"를 못 말한다.
    """
    assert build(item()).candidate_set_hash == build(item()).candidate_set_hash


def test_후보_순서만_바뀌어도_지문은_같다():
    """지문은 **집합**의 지문이다. 순서는 씨앗이 따로 정한다."""
    a, b = item(label_index=0), item(label_index=1, severity=0.5)
    assert build(a, b).candidate_set_hash == build(b, a).candidate_set_hash


def test_후보가_하나_늘면_지문이_달라진다():
    one = build(item(label_index=0))
    two = build(item(label_index=0), item(label_index=1, severity=0.5))
    assert one.candidate_set_hash != two.candidate_set_hash


# ── 후보 이름의 안정성 ───────────────────────────────────────────────────────

def test_목록_순서를_바꿔도_후보_이름이_그대로다():
    """순번으로 구분하면 순서만 바뀌어도 두 후보의 이름이 서로 뒤바뀐다.

    그러면 A에 내린 판정이 B에 붙는다 — 그것도 조용히.
    """
    one = item(image="a.jpg", label_index=None, suspicion="missing",
               box=(10, 10, 60, 60), label_iou=None)
    two = item(image="a.jpg", label_index=None, suspicion="missing",
               box=(90, 90, 140, 140), label_iou=None)

    forward = {c.canonical_candidate_id: tuple(c.box)
               for c in build(one, two).candidates}
    backward = {c.canonical_candidate_id: tuple(c.box)
                for c in build(two, one).candidates}
    assert forward == backward


def test_박스가_다른_누락_후보는_다른_이름이다():
    one = item(label_index=None, suspicion="missing", box=(10, 10, 60, 60),
               label_iou=None)
    two = item(label_index=None, suspicion="missing", box=(90, 90, 140, 140),
               label_iou=None)
    names = {c.canonical_candidate_id for c in build(one, two).candidates}
    assert len(names) == 2


def test_같은_라벨을_두_유형이_지목하면_이름이_다르다():
    """어느 유형이 맞았는지 세려면 판정 대상이 둘이어야 한다."""
    names = {c.canonical_candidate_id
             for c in build(item(suspicion="width"),
                            item(suspicion="scale", severity=0.7)).candidates}
    assert len(names) == 2


def test_완전히_같은_후보가_두_번_오면_조용히_덮지_않는다():
    """모든 항목이 같으면 판정자가 둘을 구분할 방법이 없다.

    하나로 접으면 **판정 하나가 소리 없이 사라지고**, 그냥 두면 같은 것을 두 번
    세게 된다. 어느 쪽도 맞지 않으므로 얼리기를 거부하고 진단 쪽을 보게 한다.
    """
    with pytest.raises(HTTPException) as caught:
        build(item(), item())
    assert caught.value.status_code == 409


# ── 이름에 무엇이 새는가 ─────────────────────────────────────────────────────

def test_이름이_유형과_순위를_드러내지_않는다():
    """이름은 가림 화면에 그대로 간다."""
    snapshot = build(item(suspicion="class_mismatch", severity=0.93))
    name = snapshot.candidates[0].canonical_candidate_id
    assert "class_mismatch" not in name
    assert "0.93" not in name and "rank" not in name
