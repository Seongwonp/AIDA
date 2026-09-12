"""판정 작업 시간 계산 (evaluation/activity.py).

**손계산 timeline과 정확히 맞는지**를 본다. 시간은 눈으로 검산하기 쉬운 값이
아니라, 규칙이 코드와 어긋나도 그럴듯한 숫자가 나온다 — 그러면 그 숫자로 N을
정하게 된다.
"""
import pytest

from evaluation.activity import (IDLE_THRESHOLD_SECONDS,
                                 bootstrap_mean_upper,
                                 budget_from_pilot, delta_scenarios,
                                 plan_seconds_per_candidate,
                                 provenance_warnings,
                                 block_budget,
                                 bootstrap_mean_upper_by_interval,
                                 interval_reports, judged_in_order,
                                 sustained_plan,
                                 read_events, summarise_activity)
from evaluation.schema import ValidationError

HASH = "h1"


_counter = {"n": 0}


def ev(second, event, cid=None, session="s1", seq=None, event_id=None, **meta):
    """`second`는 세션 시작으로부터의 초. 손계산이 쉬우라고 초 단위로 쓴다.

    `seq`를 안 주면 부르는 순서대로 매긴다 — 검사마다 순번을 손으로 세지 않게.
    """
    _counter["n"] += 1
    return {
        "event_schema_version": 1,
        "evaluation_id": "e1",
        "candidate_set_hash": HASH,
        "session_id": session,
        "event_id": event_id or f"ev{_counter['n']}",
        "sequence": _counter["n"] - 1 if seq is None else seq,
        "event": event,
        "canonical_candidate_id": cid,
        "at": "2026-09-09T00:00:00+00:00",
        "elapsed_ms": int(second * 1000),
        "meta": meta,
    }


def session(*events, name="s1"):
    """한 세션의 이벤트에 0부터 순번을 다시 매긴다."""
    out = []
    for i, e in enumerate(events):
        out.append({**e, "session_id": name, "sequence": i})
    return out


# ── 손계산 timeline ──────────────────────────────────────────────────────────

def test_손계산_timeline과_정확히_맞는다():
    """세 후보를 판정하는 흐름. 손으로 센 값과 대조한다.

        0s   session_started
        0s   candidate_opened A          A 시작
        10s  verdict_set A=hit           A에 10초
        10s  moved_next                  (같은 순간)
        10s  candidate_opened B          B 시작
        14s  verdict_set B=hold          B에 4초
        14s  moved_next
        14s  candidate_opened C          C 시작
        20s  verdict_set C=miss          C에 6초
        20s  session_ended

    활동 10 + 4 + 6 = 20초. 전체도 20초(자리를 안 비웠다).
    판정 완료 3건, 보류 1건.
    """
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(10, "verdict_set", "A", verdict="hit"),
        ev(10, "moved_next"),
        ev(10, "candidate_opened", "B"),
        ev(14, "verdict_set", "B", verdict="hold"),
        ev(14, "moved_next"),
        ev(14, "candidate_opened", "C"),
        ev(20, "verdict_set", "C", verdict="miss"),
        ev(20, "session_ended"),
    ]
    got = summarise_activity(events)

    assert got.wall_seconds == 20.0
    assert got.active_seconds == 20.0
    assert got.idle_seconds == 0.0
    assert got.judged_candidates == 3
    assert got.holds == 1
    assert got.hold_rate == pytest.approx(1 / 3)

    times = {c.canonical_candidate_id: c.active_seconds
             for c in got.per_candidate}
    assert times == {"A": 10.0, "B": 4.0, "C": 6.0}
    # 4, 6, 10 → 중앙값 6, P75는 4·6·10에서 0.75 위치 = 8
    assert got.median_seconds_per_candidate == 6.0
    assert got.p75_seconds_per_candidate == 8.0


# ── 무엇을 빼는가 ────────────────────────────────────────────────────────────

def test_탭이_숨은_시간을_뺀다():
    """화면을 안 보고 있었다."""
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(5, "visibility_changed", visible=False),
        ev(300, "visibility_changed", visible=True),
        ev(310, "verdict_set", "A", verdict="hit"),
        ev(310, "session_ended"),
    ]
    got = summarise_activity(events)
    # 0~5초는 활동, 5~300초는 숨음, 300~310초는 다시 활동.
    assert got.active_seconds == 15.0
    assert got.wall_seconds == 310.0


def test_포커스를_잃은_시간을_뺀다():
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(3, "focus_changed", focused=False),
        ev(100, "focus_changed", focused=True),
        ev(107, "verdict_set", "A", verdict="hit"),
        ev(107, "session_ended"),
    ]
    assert summarise_activity(events).active_seconds == 10.0


def test_문턱을_넘긴_부분만_뺀다():
    """**문턱까지는 남긴다.**

    넘겼다고 구간을 통째로 0으로 만들면 어려운 후보가 공짜가 된다 — 박스 하나를
    1분 넘게 들여다보는 일은 실제로 있다.
    """
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(500, "verdict_set", "A", verdict="hit"),
        ev(500, "session_ended"),
    ]
    got = summarise_activity(events)
    assert got.active_seconds == IDLE_THRESHOLD_SECONDS
    assert got.idle_seconds == 500 - IDLE_THRESHOLD_SECONDS
    assert got.per_candidate[0].active_seconds == IDLE_THRESHOLD_SECONDS


def test_문턱을_바꾸면_계산도_바뀐다():
    """바꿀 수 있게 두되, 바꾼 이유는 문서에 적는다."""
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(100, "verdict_set", "A", verdict="hit"),
    ]
    assert summarise_activity(events, idle_threshold=30).active_seconds == 30.0


def test_저장을_기다린_시간이_판정_시간에_안_섞인다():
    """**기계가 느린 것과 사람이 느린 것은 다른 문제다.**"""
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(5, "verdict_set", "A", verdict="hit"),
        ev(5, "save_started", "A"),
        ev(25, "save_succeeded", "A"),
        ev(30, "verdict_set", "A", verdict="miss"),
        ev(30, "session_ended"),
    ]
    got = summarise_activity(events)
    assert got.wait_seconds == 20.0
    assert got.active_seconds == 10.0          # 0~5, 25~30
    assert got.per_candidate[0].active_seconds == 10.0


def test_저장_실패와_재시도_시간이_따로_잡힌다():
    """**도구 결함이지 검수 비용이 아니다.**

    섞으면 우리 버그가 "검수가 오래 걸린다"로 보고된다.
    """
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(4, "verdict_set", "A", verdict="hit"),
        ev(4, "save_started", "A"),
        ev(9, "save_failed", "A"),
        ev(12, "save_retried", "A"),
        ev(12, "save_started", "A"),
        ev(15, "save_succeeded", "A"),
        ev(15, "session_ended"),
    ]
    got = summarise_activity(events)
    assert got.save_failures == 1
    assert got.save_retries == 1

    # 두 구간이 겹친다. 나눠 세는 것이 아니라 **다른 이름으로 같은 시간을**
    # 부르는 것이다.
    #
    #   4~9    기계를 기다림          → wait
    #   9~12   실패를 보고 다시 누름  → save_retry (사람 시간이지만 우리 탓)
    #   12~15  다시 기계를 기다림     → wait + save_retry
    #
    # wait = 5 + 3 = 8, save_retry = 9~15 전체 = 6.
    assert got.wait_seconds == pytest.approx(8.0)
    assert got.save_retry_seconds == pytest.approx(6.0)
    # **검수 시간은 0~4초뿐이다.** 우리 버그가 "검수가 오래 걸린다"로
    # 보고되면 안 된다.
    assert got.active_seconds == 4.0


# ── 세지 않는 것 ─────────────────────────────────────────────────────────────

def test_판정을_바꿔도_후보_하나로_센다():
    """두 번 세면 후보당 시간이 줄어 N이 부풀려진다."""
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(5, "verdict_set", "A", verdict="hit"),
        ev(8, "verdict_set", "A", verdict="miss"),
        ev(8, "session_ended"),
    ]
    got = summarise_activity(events)
    assert got.judged_candidates == 1
    assert got.per_candidate[0].verdict_changes == 2
    assert got.per_candidate[0].active_seconds == 8.0


def test_판정을_취소하면_판정_완료가_아니다():
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(5, "verdict_set", "A", verdict="hit"),
        ev(7, "verdict_cleared", "A"),
        ev(7, "session_ended"),
    ]
    got = summarise_activity(events)
    assert got.judged_candidates == 0
    assert got.opened_candidates == 1        # 시간은 썼다


def test_보류도_작업한_후보로_센다():
    """사람이 시간을 썼다. 정밀도의 분모에서만 빠진다."""
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(9, "verdict_set", "A", verdict="hold"),
        ev(9, "session_ended"),
    ]
    got = summarise_activity(events)
    assert got.judged_candidates == 1
    assert got.holds == 1
    assert got.median_seconds_per_candidate == 9.0


def test_누락_객체를_고르는_시간이_따로_잡힌다():
    """**만든 뒤가 아니라 만들기까지가 그 작업이다.**

        0s   candidate_opened C1
        6s   verdict_set C1=hit          판정에 6초
        20s  missing_object_created      **어느 객체인지 고르는 데 14초**
        26s  moved_next                  만든 뒤 6초는 다음으로 넘어가는 시간

    dry pilot에서 이 값이 0으로 나와 잡혔다 — 만든 **뒤**의 간격을 세고 있었고,
    그 간격은 대개 저장을 기다리는 시간이라 늘 0이었다.
    """
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "C1"),
        ev(6, "verdict_set", "C1", verdict="hit"),
        ev(20, "missing_object_created", "C1", name="M1"),
        ev(26, "moved_next"),
        ev(26, "session_ended"),
    ]
    got = summarise_activity(events)
    assert got.active_seconds == 26.0
    assert got.missing_link_seconds == 14.0
    assert got.adjudication_seconds == 12.0
    assert got.per_candidate[0].missing_link_seconds == 14.0


def test_저장을_기다린_뒤_이어진_구간은_연결_시간이_아니다():
    """만든 직후에는 저장이 나가므로, 그 뒤를 세면 늘 기다림에 먹힌다."""
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "C1"),
        ev(10, "missing_object_created", "C1", name="M1"),
        ev(10, "save_started", "C1"),
        ev(13, "save_succeeded", "C1"),
        ev(19, "moved_next"),
    ]
    got = summarise_activity(events)
    assert got.missing_link_seconds == 10.0
    assert got.wait_seconds == 3.0


# ── 세션 ─────────────────────────────────────────────────────────────────────

def test_새로고침하면_새_세션으로_이어진다():
    """`elapsed_ms`는 세션 안에서만 뜻이 있다. 섞어서 빼면 음수가 나온다."""
    events = [
        ev(0, "session_started", session="s1"),
        ev(0, "candidate_opened", "A", session="s1"),
        ev(10, "verdict_set", "A", session="s1", verdict="hit"),
        ev(0, "session_started", session="s2"),
        ev(0, "candidate_opened", "B", session="s2"),
        ev(7, "verdict_set", "B", session="s2", verdict="miss"),
    ]
    got = summarise_activity(events)
    assert got.sessions == 2
    assert got.wall_seconds == 17.0
    assert got.active_seconds == 17.0
    assert got.judged_candidates == 2


def test_벽시계가_뒤로_가도_시간이_음수가_안_된다():
    """자정을 넘거나 시스템 시계가 바뀌면 벽시계는 뒤로 갈 수 있다.

    길이는 단조 시계로만 재므로 영향이 없어야 한다.
    """
    events = [
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(5, "verdict_set", "A", verdict="hit"),
    ]
    events[2]["at"] = "2026-09-08T23:59:00+00:00"     # 앞 이벤트보다 이르다
    got = summarise_activity(events)
    assert got.active_seconds == 5.0
    assert got.wall_seconds >= 0


# ── 입력 검증 ────────────────────────────────────────────────────────────────

def test_모르는_기록_판이면_멈춘다():
    events = [ev(0, "session_started")]
    events[0]["event_schema_version"] = 99
    with pytest.raises(ValidationError, match="기록 판"):
        summarise_activity(events)


def test_세션_id가_없으면_멈춘다():
    events = [ev(0, "session_started")]
    del events[0]["session_id"]
    with pytest.raises(ValidationError, match="session_id"):
        summarise_activity(events)


def test_깨진_줄을_조용히_건너뛰지_않는다():
    """건너뛰면 그 시점의 작업이 빠져 후보당 시간이 짧게 나온다."""
    with pytest.raises(ValidationError, match="2번째 줄"):
        read_events('{"a": 1}\n{깨짐\n')


def test_빈_줄은_넘긴다():
    assert len(read_events('{"a": 1}\n\n{"b": 2}\n')) == 2


def test_기록이_없으면_빈_요약이다():
    got = summarise_activity([])
    assert got.judged_candidates == 0
    assert got.p75_seconds_per_candidate is None


# ── 중복 이벤트 ──────────────────────────────────────────────────────────────

def test_같은_이벤트를_두_번_받아도_한_번만_센다():
    """응답을 못 받은 묶음을 다시 보내면 서버에 두 벌이 남을 수 있다.

    **활동 시간은 두 배가 안 된다** — 겹친 이벤트는 같은 순번·같은 시각이라
    사이 간격이 0이다. 망가지는 것은 판정 횟수와 순번 무결성이다.
    """
    rows = session(
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(10, "verdict_set", "A", verdict="hit"),
        ev(10, "session_ended"),
    )
    doubled = rows + [dict(r) for r in rows[1:3]]     # 가운데 두 건을 재전송
    got = summarise_activity(doubled)

    assert got.duplicate_events == 2
    assert got.active_seconds == 10.0
    assert got.judged_candidates == 1
    # 걸러내지 않으면 판정을 두 번 한 것으로 세고, 순번이 겹쳐 세션이 손상으로
    # 잡힌다. 걸러내면 둘 다 멀쩡하다.
    assert got.per_candidate[0].verdict_changes == 1
    assert got.session_reports[0].duplicate_sequences == []
    assert got.complete_sessions == 1


def test_중복이_있으면_시간을_쓸_수_없다고_말한다():
    """겹침이 있었다는 사실 자체가 기록의 상태를 말한다."""
    rows = session(
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(5, "verdict_set", "A", verdict="hit"),
        ev(5, "session_ended"),
    )
    got = summarise_activity(rows + [dict(rows[2])])
    assert got.duplicate_events == 1
    assert got.timing_usable is False


def test_event_id가_없으면_멈춘다():
    """중복을 가려낼 수 없다."""
    rows = session(ev(0, "session_started"))
    del rows[0]["event_id"]
    with pytest.raises(ValidationError, match="event_id"):
        summarise_activity(rows)


# ── 기록 완전성 ──────────────────────────────────────────────────────────────

def test_끝을_못_본_세션은_불완전이다():
    """브라우저가 죽으면 마지막 후보의 시간이 잘린 채 남는다."""
    rows = session(
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(3, "verdict_set", "A", verdict="hit"),
    )
    got = summarise_activity(rows)
    assert got.complete_sessions == 0
    assert got.incomplete_sessions == 1
    assert got.invalid_sessions == ["s1"]
    assert got.session_reports[0].ended is False
    # **잘린 시간을 통계에 안 넣는다.**
    assert got.mean_seconds_per_candidate is None
    assert got.timing_usable is False


def test_빠진_순번을_찾아낸다():
    """전송이 통째로 유실되면 순번에 구멍이 난다."""
    rows = session(
        ev(0, "session_started"),
        ev(1, "candidate_opened", "A"),
        ev(4, "verdict_set", "A", verdict="hit"),
        ev(4, "session_ended"),
    )
    del rows[2]                               # 2번 순번이 사라졌다
    got = summarise_activity(rows)
    assert got.missing_sequences == 1
    assert got.session_reports[0].missing_sequences == [2]
    assert got.timing_usable is False


def test_순번이_겹치면_불완전이다():
    rows = session(
        ev(0, "session_started"),
        ev(1, "candidate_opened", "A"),
        ev(4, "verdict_set", "A", verdict="hit"),
        ev(4, "session_ended"),
    )
    rows[2]["sequence"] = 1
    got = summarise_activity(rows)
    assert got.session_reports[0].duplicate_sequences == [1]
    assert got.complete_sessions == 0


def test_시간이_뒤로_가면_불완전이다():
    rows = session(
        ev(0, "session_started"),
        ev(10, "candidate_opened", "A"),
        ev(4, "verdict_set", "A", verdict="hit"),
        ev(11, "session_ended"),
    )
    got = summarise_activity(rows)
    assert got.session_reports[0].elapsed_regressions == 1
    assert got.complete_sessions == 0


def test_StrictMode의_시작_끝_시작을_손상으로_보지_않는다():
    """개발 모드는 effect를 두 번 돌려 시작·끝·시작이 남을 수 있다.

    **순번과 시각이 이어져 있으면 그건 한 세션이다.** 손상 기록과 갈라야 한다.
    """
    rows = session(
        ev(0, "session_started"),
        ev(0, "session_ended"),
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(6, "verdict_set", "A", verdict="hit"),
        ev(6, "session_ended"),
    )
    got = summarise_activity(rows)
    assert got.complete_sessions == 1
    assert got.incomplete_sessions == 0
    assert got.session_reports[0].complete is True


def test_한_세션이_끊겨도_다른_세션은_쓴다():
    good = session(
        ev(0, "session_started"),
        ev(0, "candidate_opened", "A"),
        ev(8, "verdict_set", "A", verdict="hit"),
        ev(8, "session_ended"),
        name="ok")
    broken = session(
        ev(0, "session_started"),
        ev(0, "candidate_opened", "B"),
        ev(1, "verdict_set", "B", verdict="hit"),
        name="broken")
    got = summarise_activity(good + broken)

    assert got.complete_sessions == 1
    assert got.incomplete_sessions == 1
    # 끊긴 세션의 1초가 평균을 끌어내리지 않는다.
    assert got.mean_seconds_per_candidate == 8.0


# ── 목록 조회 대기 ───────────────────────────────────────────────────────────

def test_목록을_기다린_시간은_판정_시간이_아니다():
    rows = session(
        ev(0, "session_started"),
        ev(0, "queue_load_started"),
        ev(9, "queue_load_succeeded"),
        ev(9, "candidate_opened", "A"),
        ev(14, "verdict_set", "A", verdict="hit"),
        ev(14, "session_ended"),
    )
    got = summarise_activity(rows)
    assert got.queue_load_seconds == 9.0
    assert got.wait_seconds == 9.0
    assert got.active_seconds == 5.0
    assert got.per_candidate[0].active_seconds == 5.0


def test_판정_시간에_첫_후보_이전의_시간이_안_들어간다():
    """`adjudication_seconds`가 이름보다 넓은 값이면 안 된다.

    예전에는 `active - missing_link`라서 첫 후보가 뜨기 전의 시간까지
    "판정 시간"에 들어갔다.
    """
    rows = session(
        ev(0, "session_started"),
        ev(7, "candidate_opened", "A"),     # 뜨기 전 7초는 후보의 시간이 아니다
        ev(12, "verdict_set", "A", verdict="hit"),
        ev(12, "session_ended"),
    )
    got = summarise_activity(rows)
    assert got.active_seconds == 12.0
    assert got.adjudication_seconds == 5.0
    assert got.unattributed_seconds == 7.0


# ── 계획값 ───────────────────────────────────────────────────────────────────

def _pilot(sessions_count=2, per_session=6, seconds=10.0, prefix="s"):
    rows = []
    for s_index in range(sessions_count):
        events = [ev(0, "session_started")]
        clock = 0.0
        for c in range(per_session):
            events.append(ev(clock, "candidate_opened", f"{prefix}{s_index}_{c}"))
            clock += seconds
            events.append(ev(clock, "verdict_set", f"{prefix}{s_index}_{c}",
                             verdict="hit"))
        events.append(ev(clock, "session_ended"))
        rows += session(*events, name=f"{prefix}{s_index}")
    return rows


def test_표본이_모자라면_계획값을_만들지_않는다():
    """숫자를 지어내는 대신 왜 못 만드는지 말한다."""
    got = plan_seconds_per_candidate(summarise_activity(_pilot(1, 3)))
    assert got["status"] == "insufficient_pilot_data"
    assert got["s_plan_seconds"] is None
    assert "온전한 세션" in got["reason"] or "판정한 후보" in got["reason"]
    # 최소 기준이 근거가 약하다는 것을 결과에 적는다.
    assert "짐작" in got["minimum_basis"]


def test_계획값은_평균의_보수적_상한이다():
    """**P75가 아니다.** P75는 후보 난이도 분포의 기술 통계다."""
    summary = summarise_activity(_pilot(2, 6, seconds=10.0))
    got = plan_seconds_per_candidate(summary, judging_mode="unaided_human")

    assert got["status"] == "ok"
    assert got["mean_seconds"] == pytest.approx(10.0)
    assert got["s_plan_seconds"] >= got["mean_seconds"]
    # P75도 함께 보고하되, 그것이 계획값이 아님을 적는다.
    assert "p75_seconds" in got
    assert "총 세션 시간" in got["p75_basis"]
    assert "확률 보장이 아니라" in got["s_plan_basis"]


def test_변동이_크면_상한이_평균보다_높다():
    """세션마다 속도가 다르면 계획값이 더 보수적이어야 한다."""
    fast = _pilot(1, 6, seconds=5.0, prefix="fast")
    slow = _pilot(1, 6, seconds=25.0, prefix="slow")
    summary = summarise_activity(fast + slow)
    got = plan_seconds_per_candidate(summary, judging_mode="unaided_human")
    assert got["status"] == "ok"
    assert got["s_plan_seconds"] > got["mean_seconds"]


def test_재표집은_세션_단위다():
    """후보 단위로 뽑으면 같은 세션의 후보가 서로 독립인 척한다."""
    summary = summarise_activity(_pilot(2, 6, seconds=10.0))
    # 모든 세션이 똑같으면 재표집해도 평균이 안 흔들린다.
    assert bootstrap_mean_upper(summary) == pytest.approx(10.0)


# ── N 공식 ───────────────────────────────────────────────────────────────────

def test_예산은_계획값으로_나눈_몫이다():
    """N = floor((T / D) / s_plan)."""
    assert budget_from_pilot(10800, 3, 12.0) == 300


def test_입력이_없으면_숫자를_지어내지_않는다():
    """D와 T는 사용자가 정하고 s_plan은 예비 평가에서 나온다."""
    assert budget_from_pilot(10800, 3, None) is None
    assert budget_from_pilot(10800, 0, 12.0) is None
    assert budget_from_pilot(0, 3, 12.0) is None
    assert budget_from_pilot(10800, 3, 0.0) is None
    assert budget_from_pilot(10800, 3, float("inf")) is None


def test_계획값이_클수록_예산이_작다():
    """보수적인 값을 넣으면 N이 작아진다 — 그게 보수적이라는 뜻이다."""
    assert budget_from_pilot(3600, 1, 20.0) < budget_from_pilot(3600, 1, 10.0)


# ── Δ 선택지 ─────────────────────────────────────────────────────────────────

def test_델타를_고르지_않고_늘어놓기만_한다():
    rows = delta_scenarios(100)
    assert [r["name"] for r in rows] == ["A", "B", "C", "D"]
    assert [r["delta"] for r in rows] == [1, 5, 10, None]
    # ROI 안은 계산하지 않는다 — 인건비와 오류 누락 비용이 저장소에 없다.
    assert rows[-1]["delta"] is None


def test_예산이_없으면_비례_안도_수를_안_만든다():
    rows = delta_scenarios(None)
    assert [r["delta"] for r in rows] == [1, None, None, None]


# ── 사람이 판정한 기록인가 ───────────────────────────────────────────────────
#
# 자동 클릭으로 잰 시간이 N으로 흘러가면 안 된다. 처음 dry pilot이 그랬고,
# 그 값으로 N을 계산하면 868이 나왔다.

def test_너무_빠르면_사람_판정으로_안_본다():
    summary = summarise_activity(_pilot(2, 6, seconds=0.5))
    got = plan_seconds_per_candidate(summary)
    assert got["status"] == "implausible_for_human_judging"
    assert got["s_plan_seconds"] is None
    assert "자동 클릭" in got["reason"]


def test_표본이_충분해도_자동_클릭이면_막는다():
    """많이 모아도 자동 클릭 시간은 사람의 검수 시간이 되지 않는다."""
    summary = summarise_activity(_pilot(5, 20, seconds=0.3))
    assert summary.timing_usable is True          # 표본 기준은 넘겼다
    assert plan_seconds_per_candidate(summary)["status"] == \
        "implausible_for_human_judging"


def test_전부_보류면_경고한다():
    """화면을 안 보고 눌렀거나, 판정할 수 없는 자료였다는 뜻이다."""
    rows = []
    for s_index in range(2):
        events = [ev(0, "session_started")]
        clock = 0.0
        for c in range(6):
            events.append(ev(clock, "candidate_opened", f"h{s_index}_{c}"))
            clock += 8.0
            events.append(ev(clock, "verdict_set", f"h{s_index}_{c}",
                             verdict="hold"))
        events.append(ev(clock, "session_ended"))
        rows += session(*events, name=f"h{s_index}")

    summary = summarise_activity(rows)
    got = plan_seconds_per_candidate(summary)
    assert got["status"] == "implausible_for_human_judging"
    assert "보류가" in got["reason"]


def test_사람_속도이면_통과한다():
    got = plan_seconds_per_candidate(summarise_activity(_pilot(2, 6, seconds=12.0)),
                                     judging_mode="unaided_human")
    assert got["status"] == "ok"
    assert got["provenance_warnings"] == []


def test_경고를_따로도_볼_수_있다():
    assert provenance_warnings(summarise_activity(_pilot(2, 6, seconds=0.4)))
    assert provenance_warnings(summarise_activity(_pilot(2, 6, seconds=15.0))) == []


# ── 재표집할 세션이 실제로 둘인가 ────────────────────────────────────────────
#
# timing1에서 잡혔다. 세 세션 중 판정이 든 것은 하나뿐인데 complete_sessions가
# 2라서 timing_usable이 참이 됐고, 세션 하나를 반복해 뽑은 "95% 상한"이
# 평균과 똑같이 나왔다. **구간이 아무것도 말하지 않는데 숫자는 나왔다.**

def _empty_session(name):
    """열고 닫기만 한 세션. 온전하지만 잰 시간이 없다."""
    return session(
        ev(0, "session_started"),
        ev(0, "queue_load_started"),
        ev(1, "queue_load_succeeded"),
        ev(2, "session_ended"),
        name=name)


def test_판정이_든_세션이_하나면_시간을_못_쓴다():
    rows = _pilot(1, 12, seconds=10.0, prefix="work") + _empty_session("empty")
    got = summarise_activity(rows)

    assert got.complete_sessions == 2          # 둘 다 온전하긴 하다
    assert got.judged_candidates == 12
    # **그래도 재표집할 것이 하나뿐이다.**
    assert got.timing_usable is False


def test_왜_못_쓰는지_말한다():
    rows = _pilot(1, 12, seconds=10.0, prefix="work") + _empty_session("empty")
    got = plan_seconds_per_candidate(summarise_activity(rows))
    assert got["status"] == "insufficient_pilot_data"
    assert "판정이 든 세션" in got["reason"]


def test_세션이_하나면_상한을_만들지_않는다():
    """세션 하나를 반복해 뽑으면 늘 그 세션의 평균이 나온다 — 구간이 아니다."""
    summary = summarise_activity(_pilot(1, 12, seconds=10.0, prefix="solo"))
    assert bootstrap_mean_upper(summary) is None


def test_판정이_든_세션이_둘이면_쓴다():
    got = summarise_activity(_pilot(2, 6, seconds=10.0, prefix="two"))
    assert got.sessions_with_judgements == 2
    assert got.timing_usable is True


# ── 도움을 받았는가 — 기록만으로는 알 수 없다 ───────────────────────────────
#
# timing1이 증거다. 후보당 중앙값 5.3초에 보류 0%로 자동 클릭 검사를 전부
# 통과했지만, 판정자가 화면을 다른 도구에 보내 도움을 받았다. 그 도구에서
# 들여다본 시간은 판정 탭의 활동 시간에 안 들어간다.

def test_보조받은_기록은_계획값을_안_낸다():
    summary = summarise_activity(_pilot(2, 6, seconds=12.0, prefix="a"))
    assert summary.timing_usable is True         # 표본도 속도도 멀쩡하다
    got = plan_seconds_per_candidate(summary, judging_mode="assisted_rehearsal")
    assert got["status"] == "not_unaided_human"
    assert got["s_plan_seconds"] is None
    assert got["diagnostic_only"] is True


def test_안_적혀_있으면_안_받았다고_읽지_않는다():
    """실수 하나가 기준이 되면 안 된다."""
    got = plan_seconds_per_candidate(
        summarise_activity(_pilot(2, 6, seconds=12.0, prefix="b")))
    assert got["status"] == "not_unaided_human"
    assert "적혀 있지 않습니다" in got["reason"]


def test_도움_없이_한_기록만_계획값을_낸다():
    got = plan_seconds_per_candidate(
        summarise_activity(_pilot(2, 6, seconds=12.0, prefix="c")),
        judging_mode="unaided_human")
    assert got["status"] == "ok"
    assert got["judging_mode"] == "unaided_human"
    assert got["s_plan_seconds"] is not None


def test_모르는_판정_방식은_거부한다():
    with pytest.raises(ValidationError, match="판정 방식"):
        plan_seconds_per_candidate(
            summarise_activity(_pilot(2, 6, seconds=12.0, prefix="d")),
            judging_mode="아무거나")


# ── 후보가 얼마나 실제 같은가 ────────────────────────────────────────────────
#
# 주입한 오류는 크고 종류도 셋뿐이라 실제 후보보다 잘 보인다. 그렇게 잰 시간은
# 하한이고, **하한을 N에 넣으면 N이 과대해져 시간 상한이 깨진다** — 방향이
# 보수적인 쪽의 반대다.

def test_주입한_오류로_잰_값은_하한이다():
    got = plan_seconds_per_candidate(
        summarise_activity(_pilot(2, 6, seconds=12.0, prefix="syn")),
        judging_mode="unaided_human", candidate_source="injected_synthetic")
    assert got["status"] == "ok"                 # 측정 자체는 유효하다
    assert got["s_plan_bound"] == "lower"
    assert got["adoption_blocked"] is True
    assert "과대해져" in got["adoption_note"]


def test_출처를_안_적으면_하한으로_본다():
    """모르는 것을 '실제 후보였다'로 읽으면 실수 하나가 기준이 된다."""
    got = plan_seconds_per_candidate(
        summarise_activity(_pilot(2, 6, seconds=12.0, prefix="unk")),
        judging_mode="unaided_human")
    assert got["adoption_blocked"] is True


def test_실제_진단_후보로_잰_값은_안_막는다():
    got = plan_seconds_per_candidate(
        summarise_activity(_pilot(2, 6, seconds=12.0, prefix="real")),
        judging_mode="unaided_human", candidate_source="actual_diagnosis")
    assert got["s_plan_bound"] == "estimate"
    assert got["adoption_blocked"] is False


def test_모르는_후보_출처는_거부한다():
    with pytest.raises(ValidationError, match="후보 출처"):
        plan_seconds_per_candidate(
            summarise_activity(_pilot(2, 6, seconds=12.0, prefix="bad")),
            judging_mode="unaided_human", candidate_source="아무거나")


# ── 지속 판정의 구간 분석 (docs/sustained-pilot-protocol.md) ────────────────
#
# **데이터를 만들기 전에 고정한다.** 구간을 어떻게 끊고 무엇을 재는지가 결과를
# 본 뒤에 정해지면 그건 기준이 아니라 사후 설명이다.

def _sustained(times, prefix="s", name="one"):
    """한 세션에서 순서대로 판정한 기록. `times`는 후보당 초."""
    events = [ev(0, "session_started")]
    clock = 0.0
    for i, seconds in enumerate(times):
        events.append(ev(clock, "candidate_opened", f"{prefix}{i:03d}"))
        clock += seconds
        events.append(ev(clock, "verdict_set", f"{prefix}{i:03d}", verdict="hit"))
    events.append(ev(clock, "session_ended"))
    return session(*events, name=name)


def test_판정_순서대로_구간을_끊는다():
    """**시계가 아니라 작업량으로 끊는다** — 피로는 몇 번째 후보인가를 따라온다."""
    rows = _sustained([2.0] * 60, prefix="a")
    got = interval_reports(rows, summarise_activity(rows), size=25)

    assert [r.index for r in got] == [1, 2, 3]
    assert [(r.first, r.last) for r in got] == [(1, 25), (26, 50), (51, 60)]
    assert [r.complete for r in got] == [True, True, False]


def test_마지막_반쪽_구간은_비교에_안_쓴다():
    """25건과 10건의 평균을 나란히 놓으면 뒤가 흔들려 보인다."""
    rows = _sustained([2.0] * 25 + [9.0] * 10, prefix="b")
    reports = interval_reports(rows, summarise_activity(rows), size=25)

    assert reports[-1].complete is False
    # 반쪽 구간이 느려도 상한 계산에서 빠진다.
    assert bootstrap_mean_upper_by_interval(reports) is None   # 완성 구간 1개


def test_구간별_손계산과_맞는다():
    """1~25는 2초, 26~50은 6초, 51~75는 4초."""
    rows = _sustained([2.0] * 25 + [6.0] * 25 + [4.0] * 25, prefix="c")
    got = interval_reports(rows, summarise_activity(rows), size=25)

    assert [round(r.mean_seconds, 2) for r in got] == [2.0, 6.0, 4.0]
    assert all(r.judged == 25 and r.complete for r in got)


def test_되돌아본_판정은_처음_자리로_센다():
    """같은 후보를 다시 판정해도 순서가 밀리면 안 된다."""
    events = [ev(0, "session_started")]
    for i in range(3):
        events.append(ev(i * 2.0, "candidate_opened", f"d{i}"))
        events.append(ev(i * 2.0 + 2.0, "verdict_set", f"d{i}", verdict="hit"))
    # 0번으로 되돌아가 다시 판정한다.
    events.append(ev(7.0, "candidate_opened", "d0"))
    events.append(ev(8.0, "verdict_set", "d0", verdict="miss"))
    events.append(ev(8.0, "session_ended"))
    rows = session(*events, name="back")

    order = [c.canonical_candidate_id
             for c in judged_in_order(rows, summarise_activity(rows))]
    assert order == ["d0", "d1", "d2"]


def test_보류를_구간별로_센다():
    """판단을 미루는 빈도가 느는지 보려는 것이다."""
    rows = _sustained([2.0] * 50, prefix="e")
    summary = summarise_activity(rows)
    holds = {f"e{i:03d}": "hold" for i in (30, 31, 32)}
    got = interval_reports(rows, summary, size=25, holds_by_candidate=holds)

    assert got[0].holds == 0
    assert got[1].holds == 3
    assert got[1].hold_rate == pytest.approx(3 / 25)


# ── 구간 단위 재표집 ─────────────────────────────────────────────────────────

def test_구간이_모자라면_상한을_안_만든다():
    """둘이면 재표집 결과가 셋뿐이라 아무것도 말하지 않는다."""
    rows = _sustained([2.0] * 50, prefix="f")
    reports = interval_reports(rows, summarise_activity(rows), size=25)
    assert len([r for r in reports if r.complete]) == 2
    assert bootstrap_mean_upper_by_interval(reports) is None


def test_구간이_셋이면_상한이_나온다():
    rows = _sustained([3.0] * 75, prefix="g")
    reports = interval_reports(rows, summarise_activity(rows), size=25)
    # 모든 구간이 똑같으면 재표집해도 평균이 안 흔들린다.
    assert bootstrap_mean_upper_by_interval(reports) == pytest.approx(3.0)


def test_후반이_느려지면_상한이_평균보다_크다():
    """피로. **임의 문턱 없이 변동이 값에 반영된다.**"""
    rows = _sustained([2.0] * 25 + [4.0] * 25 + [8.0] * 25, prefix="h")
    summary = summarise_activity(rows)
    reports = interval_reports(rows, summary, size=25)

    upper = bootstrap_mean_upper_by_interval(reports)
    assert upper > summary.mean_seconds_per_candidate


def test_후반이_빨라져도_상한이_평균보다_크다():
    """숙련. 초반 느린 구간이 상한에 남는다 — 어느 방향이든 보수적이다."""
    rows = _sustained([8.0] * 25 + [4.0] * 25 + [2.0] * 25, prefix="i")
    summary = summarise_activity(rows)
    reports = interval_reports(rows, summary, size=25)

    upper = bootstrap_mean_upper_by_interval(reports)
    assert upper > summary.mean_seconds_per_candidate


def test_변동이_클수록_상한이_커진다():
    steady = _sustained([4.0] * 75, prefix="j")
    swingy = _sustained([1.0] * 25 + [4.0] * 25 + [7.0] * 25, prefix="k")
    # 평균은 둘 다 4초다.
    a = bootstrap_mean_upper_by_interval(
        interval_reports(steady, summarise_activity(steady), size=25))
    b = bootstrap_mean_upper_by_interval(
        interval_reports(swingy, summarise_activity(swingy), size=25))
    assert b > a


# ── 관문 ─────────────────────────────────────────────────────────────────────

def test_지속_계획값도_판정_방식_관문을_지난다():
    rows = _sustained([4.0] * 75, prefix="l")
    got = sustained_plan(rows, summarise_activity(rows),
                         judging_mode="assisted_rehearsal",
                         candidate_source="actual_diagnosis")
    assert got["status"] == "not_unaided_human"
    assert got["s_plan_seconds"] is None
    # 구간 정보는 진단용으로 그대로 준다.
    assert got["complete_intervals"] == 3


def test_주입_후보면_채택을_막는다():
    rows = _sustained([4.0] * 75, prefix="m")
    got = sustained_plan(rows, summarise_activity(rows),
                         judging_mode="unaided_human",
                         candidate_source="injected_synthetic")
    assert got["adoption_blocked"] is True


def test_구간이_모자라면_이유를_말한다():
    rows = _sustained([4.0] * 50, prefix="n")
    got = sustained_plan(rows, summarise_activity(rows),
                         judging_mode="unaided_human",
                         candidate_source="actual_diagnosis")
    assert got["status"] == "insufficient_intervals"
    assert "완성된 구간이 2개" in got["reason"]
    assert got["s_plan_seconds"] is None


def test_조건을_다_채우면_구간_상한을_낸다():
    rows = _sustained([2.0] * 25 + [4.0] * 25 + [6.0] * 25, prefix="o")
    summary = summarise_activity(rows)
    got = sustained_plan(rows, summary, judging_mode="unaided_human",
                         candidate_source="actual_diagnosis")

    assert got["status"] == "ok"
    assert got["adoption_blocked"] is False
    assert got["s_plan_seconds"] > got["mean_seconds"]
    assert got["first_interval_mean"] == pytest.approx(2.0)
    assert got["last_interval_mean"] == pytest.approx(6.0)
    assert got["change_pct"] == pytest.approx(200.0)
    assert "구간" in got["s_plan_basis"]


# ── 블록 구조 예산 ───────────────────────────────────────────────────────────

def test_블록을_반복하는_것만_외삽한다():
    """**한 시간을 쉬지 않고 간다고 가정하지 않는다.**

    3시간·3데이터셋, 100건을 이어서 판정했고 후보당 4초라면
    블록당 400초, 데이터셋당 3600초 → 9블록 → N=900.
    """
    got = block_budget(10800, 3, 100, 4.0)
    assert got["status"] == "ok"
    assert got["seconds_per_block"] == 400.0
    assert got["blocks_per_dataset"] == 9
    assert got["budget"] == 900


def test_블록_수가_결과에_드러난다():
    """20블록이 필요하다면 그것이 현실적인지 사람이 보고 판단한다."""
    got = block_budget(10800, 3, 25, 5.0)
    assert got["blocks_per_dataset"] == 28
    assert got["budget"] == 700


def test_입력이_없으면_예산을_안_만든다():
    assert block_budget(10800, 3, 100, None)["budget"] is None
    assert block_budget(10800, 3, 0, 4.0)["budget"] is None
    assert block_budget(0, 3, 100, 4.0)["budget"] is None
    assert block_budget(10800, 0, 100, 4.0)["budget"] is None
    assert block_budget(10800, 3, 100, float("inf"))["budget"] is None


def test_지속_계획값이_보고에_필요한_항목을_다_준다():
    """보고서가 KeyError로 죽었던 자리. **판정 직후에 터졌다.**"""
    rows = _sustained([4.0] * 75, prefix="p")
    got = sustained_plan(rows, summarise_activity(rows),
                         judging_mode="unaided_human",
                         candidate_source="actual_diagnosis")
    for key in ("mean_seconds", "median_seconds", "p75_seconds", "p75_basis",
                "s_plan_seconds", "s_plan_basis", "s_plan_bound",
                "adoption_blocked", "adoption_note", "judged_candidates",
                "sample_ok", "intervals", "complete_intervals"):
        assert key in got, key


def test_지속_판정은_세션_하나여도_표본이_된다():
    """세션 기준 timing_usable은 거짓이지만 구간 기준으로는 충분하다."""
    rows = _sustained([4.0] * 75, prefix="q")
    summary = summarise_activity(rows)
    assert summary.timing_usable is False        # 세션이 하나
    assert sustained_plan(rows, summary, judging_mode="unaided_human",
                          candidate_source="actual_diagnosis")["status"] == "ok"
