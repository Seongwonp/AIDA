"""집계에서 시각 구간 빼기 (evaluation.activity.exclude_windows) — UI 점검 기록이 판정 기록에 섞인 경우.

practice1에서 생겼다. 판정이 끝난 뒤 판정 화면을 점검하느라 같은 평가의 작업 기록에 이동 기록이 더해졌다.
원시 기록은 고치지 않고, 집계할 때 명시한 구간만 뺀다. 판정 이벤트는 남아야 한다.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.activity import exclude_windows, summarise_activity  # noqa: E402
from evaluation.schema import ValidationError  # noqa: E402
import practice1_activity_refilter as R  # noqa: E402

WINDOW = [{"start": "2026-10-06T15:39:22.165Z", "end": "2026-10-06T16:06:48Z", "reason": "UI 점검"}]


def ev(sid, seq, event, at, ms, cid=None, meta=None):
    return {"event_schema_version": 1, "evaluation_id": "p", "candidate_set_hash": "h",
            "event_id": f"{sid}-{seq}", "session_id": sid, "sequence": seq, "event": event,
            "canonical_candidate_id": cid, "at": at, "elapsed_ms": ms, "meta": meta or {}}


def judging_session():
    """판정 세션 — 15:28:00Z부터 후보 둘, 각각 판정·저장, 15:35:55Z에 끝."""
    s = "judge"
    return [ev(s, 0, "session_started", "2026-10-06T15:28:00.000Z", 0),
            ev(s, 1, "candidate_opened", "2026-10-06T15:28:01.000Z", 1000, "A"),
            ev(s, 2, "verdict_set", "2026-10-06T15:28:04.000Z", 4000, "A", {"verdict": "miss"}),
            ev(s, 3, "save_started", "2026-10-06T15:28:04.001Z", 4001),
            ev(s, 4, "save_succeeded", "2026-10-06T15:28:04.050Z", 4050),
            ev(s, 5, "moved_next", "2026-10-06T15:28:05.000Z", 5000),
            ev(s, 6, "candidate_opened", "2026-10-06T15:28:05.001Z", 5001, "B"),
            ev(s, 7, "verdict_set", "2026-10-06T15:28:07.000Z", 7000, "B", {"verdict": "hit"}),
            ev(s, 8, "save_started", "2026-10-06T15:28:07.001Z", 7001),
            ev(s, 9, "save_succeeded", "2026-10-06T15:28:07.050Z", 7050),
            ev(s, 10, "session_ended", "2026-10-06T15:35:55.129Z", 475129)]


def inspection_session():
    """점검 세션 — 이동만, 판정·저장 없음. 구간 시작 시각에 정확히 시작한다."""
    s = "inspect"
    return [ev(s, 0, "session_started", "2026-10-06T15:39:22.165Z", 0),
            ev(s, 1, "candidate_opened", "2026-10-06T15:39:23.000Z", 835, "A"),
            ev(s, 2, "moved_next", "2026-10-06T15:39:30.000Z", 7835),
            ev(s, 3, "candidate_opened", "2026-10-06T15:39:30.001Z", 7836, "B"),
            ev(s, 4, "moved_previous", "2026-10-06T15:40:30.000Z", 67835),
            ev(s, 5, "session_ended", "2026-10-06T16:06:47.422Z", 1645257)]


def test_점검_이벤트는_빠지고_판정_이벤트는_남는다():
    judge, inspect = judging_session(), inspection_session()
    kept, dropped = exclude_windows(judge + inspect, WINDOW)
    assert kept == judge
    assert dropped == inspect
    assert all(e["session_id"] == "inspect" for e in dropped)
    assert sum(e["event"] == "verdict_set" for e in kept) == 2


def test_빼고_집계하면_판정_세션만의_집계와_같다():
    judge = judging_session()
    kept, _ = exclude_windows(judge + inspection_session(), WINDOW)
    assert summarise_activity(kept).as_dict() == summarise_activity(judge).as_dict()
    # 빼지 않으면 세션·열린 후보 수가 달라진다 — 오염이 실제로 집계를 바꾼다.
    assert summarise_activity(judge + inspection_session()).sessions == 2


def test_구간은_반열린_구간이다():
    kept, dropped = exclude_windows(
        [ev("x", 0, "focus_changed", "2026-10-06T15:39:22.164Z", 0),
         ev("x", 1, "focus_changed", "2026-10-06T15:39:22.165Z", 1),
         ev("x", 2, "focus_changed", "2026-10-06T16:06:47.999Z", 2),
         ev("x", 3, "focus_changed", "2026-10-06T16:06:48.000Z", 3)], WINDOW)
    assert [e["sequence"] for e in kept] == [0, 3]
    assert [e["sequence"] for e in dropped] == [1, 2]


def test_시간대가_다르게_적혀도_같은_순간으로_비교한다():
    local = [{"start": "2026-10-07T00:39:22.165+09:00", "end": "2026-10-07T01:06:48+09:00",
              "reason": "UI 점검"}]
    events = judging_session() + inspection_session()
    assert exclude_windows(events, local) == exclude_windows(events, WINDOW)


@pytest.mark.parametrize("bad_at", ["2026-10-06T15:40:00", None, "", "어제"])
def test_시간대_없는_시각이나_없는_시각은_거부한다(bad_at):
    with pytest.raises(ValidationError):
        exclude_windows([ev("x", 0, "focus_changed", bad_at, 0)], WINDOW)


@pytest.mark.parametrize("window", [
    {"start": "2026-10-06T16:00:00Z", "end": "2026-10-06T15:00:00Z", "reason": "r"},
    {"start": "2026-10-06T15:00:00Z", "end": "2026-10-06T16:00:00Z", "reason": ""},
    {"start": "2026-10-06T15:00:00", "end": "2026-10-06T16:00:00Z", "reason": "r"},
])
def test_잘못된_구간은_거부한다(window):
    with pytest.raises(ValidationError):
        exclude_windows(judging_session(), [window])


def test_빈_구간_목록이면_아무것도_빼지_않는다():
    events = judging_session()
    assert exclude_windows(events, []) == (events, [])


def frontend_check_session():
    """두 번째 점검 — 판정 화면 개편 뒤 UI 확인(10:07 KST = 01:07Z). 이동만 있다."""
    s = "fecheck"
    evs = [ev(s, 0, "session_started", "2026-10-07T01:07:07.408Z", 0)]
    for i in range(22):
        evs.append(ev(s, 1 + 2 * i, "candidate_opened", f"2026-10-07T01:07:{10 + 2 * i:02d}.000Z",
                      3000 + 2000 * i, f"C{i}"))
        evs.append(ev(s, 2 + 2 * i, "moved_next" if i < 21 else "moved_previous",
                      f"2026-10-07T01:07:{11 + 2 * i:02d}.000Z", 4000 + 2000 * i))
    evs.append(ev(s, 45, "session_ended", "2026-10-07T01:07:59.131Z", 51723))
    return evs


def test_practice1_구간_상수는_기록에서_정한_값이다():
    w1, w2 = R.PRACTICE1_UI_INSPECTION_WINDOWS
    assert (w1["start"], w1["end"]) == ("2026-10-06T15:39:22.165Z", "2026-10-06T16:06:48Z")
    assert (w2["start"], w2["end"]) == ("2026-10-07T01:05:00Z", "2026-10-07T01:08:00Z")
    judge = judging_session()
    kept, dropped = exclude_windows(judge + inspection_session() + frontend_check_session(),
                                    R.PRACTICE1_UI_INSPECTION_WINDOWS)
    assert kept == judge
    assert {e["session_id"] for e in dropped} == {"inspect", "fecheck"}
    assert not any(e["event"] in ("verdict_set", "save_started") for e in dropped)


def test_두_번째_점검_구간도_빼면_집계가_판정_세션과_같다():
    judge = judging_session()
    mixed = judge + inspection_session() + frontend_check_session()
    kept, _ = exclude_windows(mixed, R.PRACTICE1_UI_INSPECTION_WINDOWS)
    assert summarise_activity(kept).as_dict() == summarise_activity(judge).as_dict()
    assert summarise_activity(mixed).opened_candidates > summarise_activity(judge).opened_candidates


def test_줄_범위_표기():
    assert R._ranges([1, 2, 3, 7, 8, 10]) == ["1-3", "7-8", "10-10"]
    assert R._ranges([]) == []


def test_재집계_도구는_기존_요약을_재현하는지_적고_덮어쓰지_않는다(tmp_path):
    events = judging_session() + inspection_session()
    act = tmp_path / "activity.jsonl"
    act.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    adj = tmp_path / "adjudications.json"
    adj.write_text(json.dumps({"updated_at": "x", "adjudications": [
        {"canonical_candidate_id": "A", "verdict": "miss"},
        {"canonical_candidate_id": "B", "verdict": "hit"}]}), encoding="utf-8")
    t = R.timing_block(judging_session())
    prev = tmp_path / "prev.json"
    prev.write_text(json.dumps({"timing": {k: t[k] for k in R.COMPARED_KEYS},
                                "save": {"save_failures": 0, "save_retries": 0}}), encoding="utf-8")
    out = tmp_path / "out.json"
    assert R.main(["--activity", str(act), "--adjudications", str(adj),
                   "--previous", str(prev), "--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["reproduces_previous"] is True
    assert result["excluded"]["events"] == 6 and result["adjudications"]["candidates_differing"] == []
    before = out.read_bytes()
    with pytest.raises(SystemExit):
        R.main(["--activity", str(act), "--adjudications", str(adj),
                "--previous", str(prev), "--out", str(out)])
    assert out.read_bytes() == before
