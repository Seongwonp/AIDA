"""세션의 끝과, 저장된 판정과 작업 기록의 대조.

prelim1에서 잡혔다. 판정 파일은 186건인데 작업 기록이 판정했다고 센 후보는
185건이었다. 마지막 후보(섞인 순서 186번째)의 판정은 저장됐지만 그 후보의 기록은
서버에 한 건도 없었다 — 마지막 세션의 기록은 앞 후보의 `save_started`에서 끊겼다.

그런데 요약은 그 세션을 **온전하다**고 셌다. 개발 모드의 React StrictMode가
화면을 띄울 때 effect 정리를 한 번 돌려 **맨 앞에** `session_ended`를 남기고,
세션 판정은 `session_ended`가 어디에든 있으면 끝났다고 봤기 때문이다. 뒤쪽이
잘려도 순번 구멍은 생기지 않아 잡히지 않았다.
"""
from evaluation.activity import reconcile_verdicts, session_report


def ev(seq, event, cid=None, ms=0, sid="s1", meta=None):
    return {"event_id": f"{sid}-{seq}", "session_id": sid, "sequence": seq,
            "event": event, "canonical_candidate_id": cid,
            "at": "2026-09-14T00:00:00Z", "elapsed_ms": ms, "meta": meta or {}}


def test_맨_앞의_session_ended로_세션이_끝났다고_보지_않는다():
    """prelim1 마지막 세션의 모양 — 앞에 StrictMode의 끝, 뒤는 저장 도중에 끊김."""
    session = [ev(0, "queue_load_started"), ev(1, "session_started"),
               ev(2, "session_ended"), ev(3, "queue_load_started"),
               ev(4, "session_started"), ev(5, "candidate_opened", "A", 100),
               ev(6, "verdict_set", "A", 900, meta={"verdict": "miss"}),
               ev(7, "save_started", None, 901)]
    report = session_report(session)
    assert report.ended is False
    assert report.complete is False


def test_끝난_뒤의_가시성_포커스_이벤트는_끝을_지우지_않는다():
    """창을 닫을 때 `session_ended` 뒤에 `visibility_changed`·`focus_changed`가 온다."""
    session = [ev(0, "session_started"), ev(1, "candidate_opened", "A", 100),
               ev(2, "verdict_set", "A", 900, meta={"verdict": "miss"}),
               ev(3, "session_ended", None, 1000),
               ev(4, "visibility_changed", None, 1001, meta={"visible": False}),
               ev(5, "focus_changed", None, 1002, meta={"focused": False})]
    report = session_report(session)
    assert report.ended is True
    assert report.complete is True


def test_저장된_판정인데_기록이_없는_후보를_가려낸다():
    events = [ev(0, "session_started"),
              ev(1, "candidate_opened", "A", 10),
              ev(2, "verdict_set", "A", 20, meta={"verdict": "miss"}),
              ev(3, "candidate_opened", "C", 30),
              ev(4, "verdict_set", "C", 40, meta={"verdict": "hit"}),
              ev(5, "verdict_cleared", "C", 50)]
    got = reconcile_verdicts(events, {"A": "miss", "B": "miss"})
    assert got["saved_judged"] == 2
    assert got["telemetry_judged"] == 1          # A만. C는 지웠다.
    assert got["missing_telemetry"] == ["B"]
    assert got["telemetry_only"] == []
    assert got["verdict_mismatch"] == []
    assert got["consistent"] is False


def test_기록의_마지막_판정과_저장된_판정이_다르면_가려낸다():
    events = [ev(0, "verdict_set", "A", 10, meta={"verdict": "hit"}),
              ev(1, "verdict_set", "A", 20, meta={"verdict": "miss"}),
              ev(2, "verdict_set", "D", 30, meta={"verdict": "hold"})]
    got = reconcile_verdicts(events, {"A": "hit"})
    assert got["verdict_mismatch"] == ["A"]       # 기록의 마지막은 miss
    assert got["telemetry_only"] == ["D"]         # 기록엔 있는데 저장엔 없다
    assert got["consistent"] is False


def test_모두_맞으면_일치한다():
    events = [ev(0, "verdict_set", "A", 10, meta={"verdict": "miss"})]
    got = reconcile_verdicts(events, {"A": "miss"})
    assert got["consistent"] is True
    assert got["missing_telemetry"] == [] and got["verdict_mismatch"] == []
