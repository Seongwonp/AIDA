"""판정 작업 시간 (docs/pilot-evaluation-plan.md).

**"페이지를 열어 둔 시간"은 검수 시간이 아니다.** 탭을 열어 두고 점심을 먹으면
검수가 느린 것처럼 보이고, 화면을 미리 띄워 두고 재면 빨라 보인다. 둘 다 사람이
실제로 쓴 시간이 아니다.

그래서 원시 이벤트만 저장하고 **계산은 여기서 따로 한다.** 화면이 요약을 만들면
그 숫자가 화면에 뜨기 쉽고(판정자가 보고 판단을 조절한다), 규칙을 고칠 때 이미
저장된 기록을 다시 계산할 수 없다.

**기록이 온전한지 먼저 본다.** 끊긴 세션의 잘린 시간을 그대로 넣으면 후보당
시간이 짧아지고 N이 부풀려진다. 그건 조용히 일어난다 — 그래서 요약이 스스로
"이 기록으로 시간을 재도 되는가"를 말한다(`timing_usable`).

표준 라이브러리만 쓴다 — CI에 numpy가 없다.
"""
import json
import math
import random
from dataclasses import dataclass, field

from .schema import ValidationError

# 기록 형식의 판. 화면·서버 쪽 `EVENT_SCHEMA_VERSION`과 같은 값이다.
SUPPORTED_EVENT_VERSION = 1

# 마지막 입력 뒤 이만큼을 넘긴 구간은 활동 시간에서 뺀다.
# **결과를 보기 전에 정했다**(docs/pilot-evaluation-plan.md). 바꾸려면 이유와
# 바꾸기 전후 수치를 그 문서에 적는다.
IDLE_THRESHOLD_SECONDS = 60.0

# 사람이 무언가를 한 이벤트. 이것들이 자리 비움 시계를 0으로 되돌린다.
INPUT_EVENTS = frozenset({
    "candidate_opened", "verdict_set", "verdict_cleared",
    "missing_object_created", "missing_object_linked",
    "moved_previous", "moved_next", "save_retried",
})

# 사람이 아니라 기계를 기다린 구간.
WAIT_START = frozenset({"save_started", "queue_load_started"})
WAIT_END = frozenset({"save_succeeded", "save_failed",
                      "queue_load_succeeded", "queue_load_failed"})

# 누락 객체를 만들거나 잇는 작업. **이 이벤트로 끝나는 구간**을 따로 잡는다 —
# 어느 객체인지 고르는 시간이 그 작업이다.
MISSING_LINK_EVENTS = frozenset({"missing_object_created",
                                 "missing_object_linked"})

# 아는 이벤트 이름 전부. 서버의 whitelist와 같아야 한다.
KNOWN_EVENTS = frozenset(INPUT_EVENTS | WAIT_START | WAIT_END | {
    "session_started", "session_ended", "visibility_changed", "focus_changed",
})

# ── N을 계산해도 되는 최소 표본 ──────────────────────────────────────────────
#
# **근거가 약한 운영 기준이다.** 통계적으로 유도한 값이 아니라 "이보다 적으면
# 평균의 구간이 아무것도 말하지 않는다"는 짐작이다. 바꾸려면 이유를
# docs/pilot-evaluation-plan.md에 적는다.
MIN_COMPLETE_SESSIONS = 2
MIN_JUDGED_CANDIDATES = 10


@dataclass
class CandidateTime:
    canonical_candidate_id: str
    active_seconds: float = 0.0
    missing_link_seconds: float = 0.0
    # 판정을 몇 번 바꿨는가. **후보 수를 세는 데는 안 쓴다** — 같은 후보를 두 번
    # 세면 후보당 시간이 줄어 N이 부풀려진다.
    verdict_changes: int = 0
    judged: bool = False
    # 어느 세션에서 잰 시간인가. 재표집 단위다.
    session_id: str = ""


@dataclass
class SessionReport:
    """세션 하나가 온전한가."""
    session_id: str
    started: bool = False
    ended: bool = False
    events: int = 0
    first_event: str | None = None
    last_event: str | None = None
    missing_sequences: list[int] = field(default_factory=list)
    duplicate_sequences: list[int] = field(default_factory=list)
    elapsed_regressions: int = 0

    @property
    def complete(self) -> bool:
        """**끝을 못 본 세션은 시간을 재지 않는다.**

        브라우저가 죽으면 마지막 후보의 시간이 잘린 채 남는다. 그걸 그대로
        넣으면 후보당 시간이 짧아지고 N이 부풀려진다.
        """
        return (self.started and self.ended and not self.missing_sequences
                and not self.duplicate_sequences
                and self.elapsed_regressions == 0)

    def as_dict(self) -> dict:
        return {
            "session_id": self.session_id, "started": self.started,
            "ended": self.ended, "events": self.events,
            "first_event": self.first_event, "last_event": self.last_event,
            "missing_sequences": self.missing_sequences,
            "duplicate_sequences": self.duplicate_sequences,
            "elapsed_regressions": self.elapsed_regressions,
            "complete": self.complete,
        }


@dataclass
class ActivitySummary:
    wall_seconds: float = 0.0
    active_seconds: float = 0.0
    wait_seconds: float = 0.0
    queue_load_seconds: float = 0.0
    save_retry_seconds: float = 0.0
    idle_seconds: float = 0.0
    adjudication_seconds: float = 0.0
    missing_link_seconds: float = 0.0
    unattributed_seconds: float = 0.0
    judged_candidates: int = 0
    opened_candidates: int = 0
    holds: int = 0
    hold_rate: float | None = None
    mean_seconds_per_candidate: float | None = None
    median_seconds_per_candidate: float | None = None
    p75_seconds_per_candidate: float | None = None
    save_failures: int = 0
    save_retries: int = 0
    sessions: int = 0
    complete_sessions: int = 0
    incomplete_sessions: int = 0
    invalid_sessions: list[str] = field(default_factory=list)
    duplicate_events: int = 0
    missing_sequences: int = 0
    timing_usable: bool = False
    per_candidate: list[CandidateTime] = field(default_factory=list)
    session_reports: list[SessionReport] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "wall_seconds": round(self.wall_seconds, 3),
            "active_seconds": round(self.active_seconds, 3),
            "wait_seconds": round(self.wait_seconds, 3),
            "queue_load_seconds": round(self.queue_load_seconds, 3),
            "save_retry_seconds": round(self.save_retry_seconds, 3),
            "idle_seconds": round(self.idle_seconds, 3),
            "adjudication_seconds": round(self.adjudication_seconds, 3),
            "missing_link_seconds": round(self.missing_link_seconds, 3),
            "unattributed_seconds": round(self.unattributed_seconds, 3),
            "judged_candidates": self.judged_candidates,
            "opened_candidates": self.opened_candidates,
            "holds": self.holds,
            "hold_rate": self.hold_rate,
            "mean_seconds_per_candidate": self.mean_seconds_per_candidate,
            "median_seconds_per_candidate": self.median_seconds_per_candidate,
            "p75_seconds_per_candidate": self.p75_seconds_per_candidate,
            "save_failures": self.save_failures,
            "save_retries": self.save_retries,
            "sessions": self.sessions,
            "complete_sessions": self.complete_sessions,
            "incomplete_sessions": self.incomplete_sessions,
            "invalid_sessions": self.invalid_sessions,
            "duplicate_events": self.duplicate_events,
            "missing_sequences": self.missing_sequences,
            "timing_usable": self.timing_usable,
            "per_candidate": [
                {"canonical_candidate_id": c.canonical_candidate_id,
                 "active_seconds": round(c.active_seconds, 3),
                 "missing_link_seconds": round(c.missing_link_seconds, 3),
                 "verdict_changes": c.verdict_changes,
                 "judged": c.judged, "session_id": c.session_id}
                for c in self.per_candidate
            ],
            "session_reports": [r.as_dict() for r in self.session_reports],
        }


def read_events(text: str) -> list[dict]:
    """JSON Lines를 읽는다. **깨진 줄을 조용히 건너뛰지 않는다.**

    한 줄이 깨졌다는 것은 그 시점의 작업이 기록에서 빠졌다는 뜻이고, 그러면
    후보당 시간이 실제보다 짧게 나온다. 빈 줄만 넘긴다.
    """
    events = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except ValueError as exc:
            raise ValidationError(f"{number}번째 줄을 읽지 못했다: {exc}") from exc
    return events


def _check(events: list[dict]) -> None:
    for e in events:
        version = e.get("event_schema_version")
        if version != SUPPORTED_EVENT_VERSION:
            raise ValidationError(
                f"모르는 기록 판이다: {version} "
                f"(이 코드가 아는 것은 {SUPPORTED_EVENT_VERSION})")
        if not isinstance(e.get("elapsed_ms"), (int, float)):
            raise ValidationError(
                f"elapsed_ms가 수가 아니다: {e.get('elapsed_ms')!r}")
        if not e.get("session_id"):
            raise ValidationError("session_id가 없다")
        if not e.get("event_id"):
            raise ValidationError("event_id가 없다 — 중복을 가려낼 수 없다")


def dedupe(events: list[dict]) -> tuple[list[dict], int]:
    """같은 `event_id`를 두 번 세지 않는다.

    응답을 못 받은 묶음을 다시 보내면 서버에 같은 이벤트가 두 벌 남을 수 있다.

    **활동 시간이 두 배가 되지는 않는다** — 겹친 이벤트는 같은 순번·같은 시각에
    놓여 사이 간격이 0이다. 대신 망가지는 것은 **세는 값과 무결성 판정**이다:
    판정 횟수()가 부풀고, 순번이 겹쳐 그 세션이 손상으로
    잡힌다. 실제로 재어 보고 확인했다.

    몇 건이 겹쳤는지 함께 돌려준다 — 겹침이 있었다는 사실 자체가 기록의 상태를
    말한다.
    """
    seen: set[str] = set()
    unique = []
    duplicates = 0
    for e in events:
        key = e.get("event_id")
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(e)
    return unique, duplicates


def _sessions(events: list[dict]) -> list[list[dict]]:
    """세션별로 나눈다. **새로고침하면 새 세션이다.**

    `elapsed_ms`는 세션 안에서만 뜻이 있다 — 세션이 바뀌면 0부터 다시 센다.
    섞어서 빼면 음수가 나온다.

    세션 안에서는 `sequence`로 줄 세운다. `elapsed_ms`로만 세우면 같은 순간에
    일어난 이벤트들의 순서가 파일에 적힌 순서에 달리게 된다.
    """
    grouped: dict[str, list[dict]] = {}
    order: list[str] = []
    for e in events:
        sid = e["session_id"]
        if sid not in grouped:
            grouped[sid] = []
            order.append(sid)
        grouped[sid].append(e)
    return [sorted(grouped[sid],
                   key=lambda e: (e.get("sequence", 0), e["elapsed_ms"]))
            for sid in order]


def session_report(session: list[dict]) -> SessionReport:
    """세션 하나가 온전한가. **끊긴 기록을 온전한 것처럼 세지 않는다.**"""
    report = SessionReport(session_id=session[0]["session_id"],
                           events=len(session))
    names = [e.get("event") for e in session]
    report.started = "session_started" in names
    report.ended = "session_ended" in names
    report.first_event = names[0]
    report.last_event = names[-1]

    numbers = [e.get("sequence") for e in session
               if isinstance(e.get("sequence"), int)]
    if numbers:
        counts: dict[int, int] = {}
        for n in numbers:
            counts[n] = counts.get(n, 0) + 1
        report.duplicate_sequences = sorted(n for n, c in counts.items() if c > 1)
        report.missing_sequences = [n for n in range(min(numbers), max(numbers))
                                    if n not in counts]

    previous = None
    for e in session:
        value = e["elapsed_ms"]
        if previous is not None and value < previous:
            report.elapsed_regressions += 1
        previous = value
    return report


def _percentile(values: list[float], q: float) -> float | None:
    """오름차순 정렬 뒤 선형 보간. 값이 없으면 None.

    numpy가 없으므로 직접 센다. 0%가 아니라 **말할 수 없음**이 None이다.
    """
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] + (ordered[high] - ordered[low]) * weight


def summarise_activity(events: list[dict],
                       idle_threshold: float = IDLE_THRESHOLD_SECONDS,
                       ) -> ActivitySummary:
    """원시 이벤트 → 시간 요약.

    **활동 시간은 사람이 화면을 보고 있던 구간의 합이다.** 이벤트 사이의 간격마다
    그 구간이 활동이었는지 판단한다.

    | 빼는 구간 | 왜 |
    |---|---|
    | 탭이 숨은 동안 | 화면을 안 보고 있었다 |
    | 창이 포커스를 잃은 동안 | 다른 일을 하고 있었다 |
    | 마지막 입력 뒤 문턱을 넘긴 부분 | 자리를 비웠다 |
    | 저장·목록 조회를 기다린 동안 | 기계가 느린 것은 검수 비용이 아니다 |

    **문턱까지는 남긴다.** 넘겼다고 구간을 통째로 0으로 만들면 어려운 후보가
    공짜가 된다 — 박스 하나를 1분 넘게 들여다보는 일은 실제로 있다.

    **시간 통계는 온전한 세션에서만 낸다.** 끊긴 세션의 잘린 시간을 섞으면
    후보당 시간이 짧아져 N이 부풀려진다.
    """
    if not events:
        return ActivitySummary()
    _check(events)
    events, duplicates = dedupe(events)

    summary = ActivitySummary(duplicate_events=duplicates)
    per_candidate: dict[tuple[str, str], CandidateTime] = {}
    holds_by_candidate: dict[str, str | None] = {}

    for session in _sessions(events):
        report = session_report(session)
        summary.session_reports.append(report)
        summary.sessions += 1
        summary.missing_sequences += len(report.missing_sequences)
        if report.complete:
            summary.complete_sessions += 1
        else:
            summary.incomplete_sessions += 1
            summary.invalid_sessions.append(report.session_id)

        summary.wall_seconds += (session[-1]["elapsed_ms"]
                                 - session[0]["elapsed_ms"]) / 1000.0

        visible = True
        focused = True
        waiting: str | None = None
        # 저장이 실패한 뒤 성공할 때까지. **사람 시간이지만 검수 비용이 아니다** —
        # 우리 도구가 실패해서 든 시간이다.
        recovering = False
        current: str | None = None
        # 마지막 입력 뒤 얼마나 흘렀는가. 문턱은 여기서부터 잰다.
        since_input = 0.0

        for previous, event in zip(session, session[1:]):
            gap = (event["elapsed_ms"] - previous["elapsed_ms"]) / 1000.0
            # 단조 시계라 음수가 나올 수 없지만, 기록이 손상되면 나올 수 있다.
            gap = max(gap, 0.0)

            if waiting is not None:
                # 기계를 기다린 구간. 사람 시간이 아니다.
                summary.wait_seconds += gap
                if waiting == "queue_load_started":
                    summary.queue_load_seconds += gap
                if recovering:
                    summary.save_retry_seconds += gap
            elif recovering:
                # 실패를 보고 다시 누르기까지. 검수 시간에서 뺀다.
                summary.save_retry_seconds += gap
            elif not visible or not focused:
                pass                      # 화면을 안 보고 있었다
            else:
                allowed = max(0.0, idle_threshold - since_input)
                counted = min(gap, allowed)
                summary.idle_seconds += gap - counted
                summary.active_seconds += counted
                since_input += counted
                if current is not None and counted:
                    slot = per_candidate.setdefault(
                        (report.session_id, current),
                        CandidateTime(current, session_id=report.session_id))
                    slot.active_seconds += counted
                    if event.get("event") in MISSING_LINK_EVENTS:
                        slot.missing_link_seconds += counted

            name = event.get("event")
            if name in INPUT_EVENTS or name == "session_started":
                since_input = 0.0

            if name == "visibility_changed":
                was = visible
                visible = bool(event.get("meta", {}).get("visible", True))
                # 돌아왔으면 자리를 비운 시계도 다시 0부터다.
                if visible and not was:
                    since_input = 0.0
            elif name == "focus_changed":
                was = focused
                focused = bool(event.get("meta", {}).get("focused", True))
                if focused and not was:
                    since_input = 0.0
            elif name == "candidate_opened":
                current = event.get("canonical_candidate_id")
                if current:
                    per_candidate.setdefault(
                        (report.session_id, current),
                        CandidateTime(current, session_id=report.session_id))
            elif name in WAIT_START:
                waiting = name
            elif name in WAIT_END:
                waiting = None
                if name == "save_failed":
                    summary.save_failures += 1
                    recovering = True
                elif name == "save_succeeded":
                    recovering = False
            elif name == "save_retried":
                summary.save_retries += 1
            elif name == "verdict_set":
                cid = event.get("canonical_candidate_id")
                if cid:
                    slot = per_candidate.setdefault(
                        (report.session_id, cid),
                        CandidateTime(cid, session_id=report.session_id))
                    slot.verdict_changes += 1
                    slot.judged = True
                    holds_by_candidate[cid] = event.get("meta", {}).get("verdict")
            elif name == "verdict_cleared":
                cid = event.get("canonical_candidate_id")
                if cid:
                    slot = per_candidate.setdefault(
                        (report.session_id, cid),
                        CandidateTime(cid, session_id=report.session_id))
                    slot.verdict_changes += 1
                    slot.judged = False
                    holds_by_candidate.pop(cid, None)

    summary.per_candidate = [per_candidate[k] for k in sorted(per_candidate)]
    summary.opened_candidates = len({c.canonical_candidate_id
                                     for c in summary.per_candidate})
    # **판정을 바꿔도 후보 하나로 센다.** 두 번 세면 후보당 시간이 줄어 N이
    # 부풀려진다. **보류도 작업한 후보다** — 사람이 시간을 썼다.
    judged = [c for c in summary.per_candidate if c.judged]
    summary.judged_candidates = len({c.canonical_candidate_id for c in judged})
    summary.holds = sum(1 for v in holds_by_candidate.values() if v == "hold")
    summary.hold_rate = ((summary.holds / summary.judged_candidates)
                         if summary.judged_candidates else None)

    attributed = sum(c.active_seconds for c in summary.per_candidate)
    summary.missing_link_seconds = sum(c.missing_link_seconds
                                       for c in summary.per_candidate)
    # **후보에 붙은 시간에서만 뺀다.** 예전에는 `active - missing_link`였는데,
    # 그러면 첫 후보가 뜨기 전의 시간까지 "판정 시간"에 들어갔다. 이름이
    # 가리키는 것보다 넓은 값이었다.
    summary.adjudication_seconds = attributed - summary.missing_link_seconds
    summary.unattributed_seconds = summary.active_seconds - attributed

    # **온전한 세션의 후보만 시간 통계에 넣는다.**
    good = {r.session_id for r in summary.session_reports if r.complete}
    times = [c.active_seconds for c in judged if c.session_id in good]
    summary.mean_seconds_per_candidate = ((sum(times) / len(times))
                                          if times else None)
    summary.median_seconds_per_candidate = _percentile(times, 0.5)
    summary.p75_seconds_per_candidate = _percentile(times, 0.75)
    summary.timing_usable = (
        summary.complete_sessions >= MIN_COMPLETE_SESSIONS
        and len(times) >= MIN_JUDGED_CANDIDATES
        and summary.duplicate_events == 0
        and summary.missing_sequences == 0)
    return summary


def bootstrap_mean_upper(summary: ActivitySummary, confidence: float = 0.95,
                         iterations: int = 2000, seed: int = 0) -> float | None:
    """후보당 **평균** 시간의 보수적 상한.

    재표집 단위는 **세션**이다. 후보 단위로 뽑으면 같은 세션의 후보들이 서로
    독립인 척하게 되어 구간이 실제보다 좁아진다 — 한 사람이 한 자리에서 연달아
    판정하므로 그 시간들은 서로 닮아 있다
    (docs/evaluation-methodology-sources.md 3절).

    **온전한 세션만 쓴다.** 끊긴 세션의 잘린 시간을 섞으면 평균이 낮아진다.
    """
    by_session: dict[str, list[float]] = {}
    good = {r.session_id for r in summary.session_reports if r.complete}
    for c in summary.per_candidate:
        if c.judged and c.session_id in good:
            by_session.setdefault(c.session_id, []).append(c.active_seconds)
    sessions = list(by_session.values())
    if not sessions:
        return None

    rng = random.Random(seed)
    means = []
    for _ in range(iterations):
        drawn: list[float] = []
        for _ in range(len(sessions)):
            drawn += rng.choice(sessions)
        if drawn:
            means.append(sum(drawn) / len(drawn))
    return _percentile(means, confidence)


def _why_unusable(summary: ActivitySummary) -> str:
    reasons = []
    if summary.complete_sessions < MIN_COMPLETE_SESSIONS:
        reasons.append(f"온전한 세션이 {summary.complete_sessions}개다 "
                       f"(최소 {MIN_COMPLETE_SESSIONS})")
    if summary.judged_candidates < MIN_JUDGED_CANDIDATES:
        reasons.append(f"판정한 후보가 {summary.judged_candidates}개다 "
                       f"(최소 {MIN_JUDGED_CANDIDATES})")
    if summary.duplicate_events:
        reasons.append(f"중복 이벤트가 {summary.duplicate_events}건 있다")
    if summary.missing_sequences:
        reasons.append(f"빠진 순번이 {summary.missing_sequences}개 있다")
    return "; ".join(reasons) or "알 수 없음"


def plan_seconds_per_candidate(summary: ActivitySummary, seed: int = 0) -> dict:
    """N 계획에 쓸 후보당 시간값.

    **P75는 계획값이 아니다.** P75는 "후보 하나가 이보다 오래 걸릴 확률이 25%"를
    말하는 **후보 난이도 분포의 기술 통계**이고, N건을 다 보는 데 걸리는 **총**
    시간의 상한을 말하지 않는다. 총 시간은 개별 후보의 P75가 아니라 **평균과
    분산, 그리고 세션 간 상관**에 좌우된다.

    그래서 계획값은 **평균의 보수적 상한**으로 잡는다.

        s_plan = 후보당 평균 시간의 부트스트랩 95% 상한 (세션 단위 재표집)

    **이것도 확률 보장은 아니다.** 재표집이 가정하는 것은 "앞으로의 세션이
    관측한 세션들과 같은 분포에서 온다"인데, 예비 평가 세션 몇 개로 그것을
    확인할 수 없다. **보수적인 참고값**으로만 쓴다.

    표본이 모자라면 값을 만들지 않고 `insufficient_pilot_data`를 돌려준다.
    """
    if not summary.timing_usable:
        return {
            "status": "insufficient_pilot_data",
            "reason": _why_unusable(summary),
            "complete_sessions": summary.complete_sessions,
            "judged_candidates": summary.judged_candidates,
            "minimum_sessions": MIN_COMPLETE_SESSIONS,
            "minimum_candidates": MIN_JUDGED_CANDIDATES,
            "minimum_basis": (
                "근거가 약한 운영 기준이다. 통계적으로 유도한 값이 아니라 "
                "'이보다 적으면 평균의 구간이 아무것도 말하지 않는다'는 짐작이다."),
            "s_plan_seconds": None,
        }

    return {
        "status": "ok",
        "mean_seconds": summary.mean_seconds_per_candidate,
        "median_seconds": summary.median_seconds_per_candidate,
        # **함께 보고하되 N의 근거로 쓰지 않는다.** 난이도 분포를 보는 값이다.
        "p75_seconds": summary.p75_seconds_per_candidate,
        "p75_basis": ("후보 난이도 분포의 기술 통계다. 총 세션 시간이 상한을 "
                      "넘을 확률을 말하지 않는다."),
        "s_plan_seconds": bootstrap_mean_upper(summary, seed=seed),
        "s_plan_basis": ("후보당 평균 시간의 부트스트랩 95% 상한(세션 단위 "
                         "재표집). 확률 보장이 아니라 보수적 참고값이다."),
        "complete_sessions": summary.complete_sessions,
        "judged_candidates": summary.judged_candidates,
    }


def budget_from_pilot(total_seconds: float, datasets: int,
                      s_plan_seconds: float | None) -> int | None:
    """데이터셋별 예산 N.

        N = floor((T / D) / s_plan)

    `s_plan`은 **후보당 평균 시간의 보수적 상한**이다
    (`plan_seconds_per_candidate`). **P75를 넣지 않는다** — P75는 후보 난이도
    분포의 기술 통계이지 총 시간의 상한이 아니다.

    **입력이 없으면 숫자를 지어내지 않고 `None`을 돌려준다.** `D`와 `T`는
    사용자가 정하고, `s_plan`은 예비 평가에서 나온다 — 셋이 다 있어야 계산이다.

    이 값을 그대로 쓰기 전에 세 가지를 확인한다(docs/pilot-evaluation-plan.md):
    각 데이터셋에 후보가 N개 이상 있는가, N이 너무 작아 부트스트랩이
    무의미해지지 않는가, 총 검수량이 `D × N`인가.
    """
    if (not s_plan_seconds or s_plan_seconds <= 0
            or not math.isfinite(s_plan_seconds)):
        return None
    if datasets <= 0 or total_seconds <= 0:
        return None
    return int((total_seconds / datasets) // s_plan_seconds)


def delta_scenarios(budget: int | None) -> list[dict]:
    """Δ 선택지. **고르지 않는다 — 늘어놓기만 한다.**

    Δ는 "이만큼 더 찾아야 쓸모 있다"는 사업적 최소 기준이다. 예비 평가에서
    관측한 성능 차이를 보고 정하면 기준이 아니라 결과에 맞춘 설명이 된다.

    ROI 안은 여기서 계산하지 않는다 — 검수 인건비와 오류 하나를 놓쳤을 때의
    비용이 이 저장소에 없다.
    """
    def scaled(ratio: float) -> int | None:
        return None if budget is None else math.ceil(ratio * budget)

    return [
        {"name": "A", "rule": "데이터셋마다 고유 오류 1건 더", "delta": 1,
         "note": "가장 약한 기준. 넘기기 쉽다"},
        {"name": "B", "rule": "ceil(0.05 × N)", "delta": scaled(0.05),
         "note": "N에 비례. 많이 보면 많이 찾는 효과를 성과로 안 센다"},
        {"name": "C", "rule": "ceil(0.10 × N)", "delta": scaled(0.10),
         "note": "B와 같은 성격, 더 엄격"},
        {"name": "D", "rule": "ROI 환산 최소 기준", "delta": None,
         "note": "검수 인건비와 오류 누락 비용이 있어야 계산된다 — 둘 다 없다"},
    ]
