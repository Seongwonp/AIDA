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

# ── 사람이 판정한 기록인가 ───────────────────────────────────────────────────
#
# **자동 클릭으로 잰 시간이 N으로 흘러가면 안 된다.** 처음 dry pilot이 후보당
# 2~4초였고, 그 값으로 N을 계산하면 868이 나왔다 — 사람이 클릭 속도로
# 검수한다는 가정이다.
#
# 아래 값들도 **근거가 약한 운영 기준**이다. "사람이 이미지를 보고 판단하는
# 데 최소 이 정도는 걸린다"는 짐작이고, 통계적으로 유도한 값이 아니다.
# 넘겼다고 사람이 한 것이 증명되지는 않는다 — **못 한 것만 걸러낸다.**
MIN_HUMAN_MEDIAN_SECONDS = 2.0

# ── 누가 어떻게 판정했는가 ───────────────────────────────────────────────────
#
# **속도와 보류 비율로는 알 수 없다.** timing1이 그 증거다 — 후보당 중앙값
# 5.3초에 보류 0%로 자동 클릭 검사를 전부 통과했지만, 판정자가 화면을 다른
# 도구에 보내 도움을 받았다. 그 도구에서 들여다본 시간은 판정 탭의 활동
# 시간에 안 들어간다.
#
# 그래서 **밖에서 명시적으로 적어 준다.** 기록만 보고 알아낼 수 있는 척하지
# 않는다.
UNAIDED_HUMAN = "unaided_human"
ASSISTED_REHEARSAL = "assisted_rehearsal"
JUDGING_MODES = (UNAIDED_HUMAN, ASSISTED_REHEARSAL)

# ── 후보가 얼마나 실제 같은가 ────────────────────────────────────────────────
#
# **주입한 오류로 잰 시간은 하한이다.** 파일럿 후보는 40% 늘리기·35% 줄이기·
# 30% 옮기기 세 가지뿐이고 전부 눈에 띄게 크다. 실제 후보는 더 미묘하고 유형도
# 섞여 있어 사람이 더 오래 본다.
#
# **하한을 N에 넣으면 N이 과대해진다** — `N = (T/D)/s_plan`이라 분모가 작으면
# 몫이 커지고, 보수적으로 잡으려던 시간 상한이 오히려 깨진다. 방향이 반대다.
INJECTED_SYNTHETIC = "injected_synthetic"
ACTUAL_DIAGNOSIS = "actual_diagnosis"
CANDIDATE_SOURCES = (INJECTED_SYNTHETIC, ACTUAL_DIAGNOSIS)
# 전부 보류면 화면을 안 보고 눌렀을 수 있다. 판정을 못 할 자료였다는 뜻이기도
# 하다 — 어느 쪽이든 그 시간으로 N을 정하면 안 된다.
MAX_HOLD_RATE = 0.9


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
    # 온전하면서 **판정이 실제로 들어 있는** 세션 수. 재표집 단위가 이것이다.
    sessions_with_judgements: int = 0
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
            "sessions_with_judgements": self.sessions_with_judgements,
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
    usable = [c for c in judged if c.session_id in good]
    times = [c.active_seconds for c in usable]
    # **열고 닫기만 한 세션은 세지 않는다.** 재표집 단위는 "판정이 든 세션"이라,
    # 빈 세션을 함께 세면 뽑을 것이 하나뿐인데도 구간이 나온 것처럼 보인다
    # (timing1에서 실제로 그랬다 — 상한이 평균과 똑같이 나왔다).
    summary.sessions_with_judgements = len({c.session_id for c in usable})
    summary.mean_seconds_per_candidate = ((sum(times) / len(times))
                                          if times else None)
    summary.median_seconds_per_candidate = _percentile(times, 0.5)
    summary.p75_seconds_per_candidate = _percentile(times, 0.75)
    summary.timing_usable = (
        summary.sessions_with_judgements >= MIN_COMPLETE_SESSIONS
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
    # **세션이 하나면 상한을 만들지 않는다.** 하나를 반복해 뽑으면 늘 그
    # 세션의 평균이 나온다 — 값은 나오지만 구간이 아니다.
    if len(sessions) < MIN_COMPLETE_SESSIONS:
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


def provenance_warnings(summary: ActivitySummary) -> list[str]:
    """**사람이 판정한 기록으로 보이는가.**

    자동 클릭은 사람보다 훨씬 빠르고, 화면을 안 보므로 판정이 한쪽으로 쏠린다.
    그 시간으로 N을 정하면 "사람이 클릭 속도로 검수한다"고 가정하는 셈이다.

    **여기서 통과한다고 사람이 한 것이 증명되지는 않는다.** 못 한 것만
    걸러낸다 — 기록만 보고 누가 눌렀는지 알 방법은 없다.
    """
    warnings = []
    median = summary.median_seconds_per_candidate
    if median is not None and median < MIN_HUMAN_MEDIAN_SECONDS:
        warnings.append(
            f"후보당 중앙값이 {median:.2f}초입니다 "
            f"(사람 판정의 최소 기준 {MIN_HUMAN_MEDIAN_SECONDS}초). "
            "자동 클릭으로 잰 시간일 수 있습니다.")
    if summary.hold_rate is not None and summary.hold_rate > MAX_HOLD_RATE:
        warnings.append(
            f"보류가 {summary.hold_rate * 100:.0f}%입니다. 화면을 안 보고 "
            "눌렀거나, 판정할 수 없는 자료였을 수 있습니다.")
    if summary.opened_candidates and not summary.judged_candidates:
        warnings.append("후보를 열기만 하고 판정하지 않았습니다.")
    return warnings


# ── 보고서가 읽는 항목 (docs/sustained-pilot-protocol.md) ──────────────────
#
# **상태마다 담기는 것이 다르다.** 보고서가 없는 키를 꺼내면 사람이 판정을
# 끝낸 **직후에** 죽는다 — 실제로 두 번 그랬다(timing4 이름 불일치, timing5
# `p75_basis` 누락). 보고서는 `.get`으로 읽고, 계약은 여기서 검사로 고정한다.
PLAN_KEYS = {
    "ok": ("mean_seconds", "median_seconds", "p75_seconds", "p75_basis",
           "s_plan_seconds", "s_plan_basis", "s_plan_bound",
           "adoption_blocked", "adoption_note", "judging_mode",
           "judged_candidates"),
    "insufficient_pilot_data": ("reason", "minimum_sessions",
                                "minimum_candidates", "minimum_basis"),
    "implausible_for_human_judging": ("reason", "provenance_warnings", "basis"),
    "not_unaided_human": ("reason", "judging_mode", "basis", "diagnostic_only"),
    "insufficient_intervals": ("reason", "minimum_intervals", "minimum_basis",
                               "intervals", "complete_intervals"),
}


def missing_plan_keys(plan: dict) -> list[str]:
    """계약에 적힌 항목 중 빠진 것. **비어 있어야 한다.**"""
    return [k for k in PLAN_KEYS.get(plan.get("status"), ()) if k not in plan]


def usable_times(summary: ActivitySummary) -> list[float]:
    """시간 통계에 쓰는 값들 — **온전한 세션에서 판정을 끝낸 후보**의 활동 시간."""
    good = {r.session_id for r in summary.session_reports if r.complete}
    return [c.active_seconds for c in summary.per_candidate
            if c.judged and c.session_id in good]


def sample_ok(summary: ActivitySummary, *, require_sessions: bool = True) -> bool:
    """표본이 시간 통계를 낼 만한가.

    `require_sessions`는 **재표집 단위가 세션일 때만** 참이다. 지속 판정은
    세션이 하나인 것이 정상이고(끊지 않고 이어서 하는 것이 측정 대상), 거기서는
    구간이 재표집 단위가 된다(docs/sustained-pilot-protocol.md).
    """
    ok = (len(usable_times(summary)) >= MIN_JUDGED_CANDIDATES
          and summary.duplicate_events == 0
          and summary.missing_sequences == 0)
    if require_sessions:
        ok = ok and summary.sessions_with_judgements >= MIN_COMPLETE_SESSIONS
    return ok


def _why_unusable(summary: ActivitySummary,
                  require_sessions: bool = True) -> str:
    reasons = []
    if (require_sessions
            and summary.sessions_with_judgements < MIN_COMPLETE_SESSIONS):
        reasons.append(f"판정이 든 세션이 {summary.sessions_with_judgements}개다 "
                       f"(최소 {MIN_COMPLETE_SESSIONS}). 열고 닫기만 한 세션은 "
                       "재표집할 것이 없다")
    if len(usable_times(summary)) < MIN_JUDGED_CANDIDATES:
        reasons.append(f"판정한 후보가 {summary.judged_candidates}개다 "
                       f"(최소 {MIN_JUDGED_CANDIDATES})")
    if summary.duplicate_events:
        reasons.append(f"중복 이벤트가 {summary.duplicate_events}건 있다")
    if summary.missing_sequences:
        reasons.append(f"빠진 순번이 {summary.missing_sequences}개 있다")
    return "; ".join(reasons) or "알 수 없음"


def plan_seconds_per_candidate(summary: ActivitySummary, seed: int = 0,
                              judging_mode: str | None = None,
                              candidate_source: str | None = None,
                              require_sessions: bool = True) -> dict:
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

    `judging_mode`는 **밖에서 적어 준다.** 도움을 받았는지는 기록만 보고 알 수
    없다 — 다른 도구에서 들여다본 시간은 이 탭의 활동 시간에 안 들어가므로
    속도도 보류 비율도 멀쩡해 보인다. `unaided_human`만 계획값을 낸다.
    """
    if judging_mode is not None and judging_mode not in JUDGING_MODES:
        raise ValidationError(
            f"모르는 판정 방식이다: {judging_mode!r} "
            f"(아는 것은 {', '.join(JUDGING_MODES)})")
    if candidate_source is not None and candidate_source not in CANDIDATE_SOURCES:
        raise ValidationError(
            f"모르는 후보 출처다: {candidate_source!r} "
            f"(아는 것은 {', '.join(CANDIDATE_SOURCES)})")

    warnings = provenance_warnings(summary)
    if warnings:
        # **표본이 충분해도 막는다.** 자동 클릭 시간은 많이 모아도 사람의
        # 검수 시간이 되지 않는다.
        return {
            "status": "implausible_for_human_judging",
            "reason": " ".join(warnings),
            "provenance_warnings": warnings,
            "median_seconds": summary.median_seconds_per_candidate,
            "hold_rate": summary.hold_rate,
            "s_plan_seconds": None,
            "basis": ("근거가 약한 운영 기준이다. 넘겼다고 사람이 한 것이 "
                      "증명되지는 않는다 — 못 한 것만 걸러낸다."),
        }

    if not sample_ok(summary, require_sessions=require_sessions):
        return {
            "status": "insufficient_pilot_data",
            "reason": _why_unusable(summary, require_sessions),
            "complete_sessions": summary.complete_sessions,
            "sessions_with_judgements": summary.sessions_with_judgements,
            "judged_candidates": summary.judged_candidates,
            "minimum_sessions": MIN_COMPLETE_SESSIONS,
            "minimum_candidates": MIN_JUDGED_CANDIDATES,
            "minimum_basis": (
                "근거가 약한 운영 기준이다. 통계적으로 유도한 값이 아니라 "
                "'이보다 적으면 평균의 구간이 아무것도 말하지 않는다'는 짐작이다."),
            "s_plan_seconds": None,
        }

    if judging_mode != UNAIDED_HUMAN:
        # **도움을 받았거나, 받았는지 안 적혀 있다.** 둘 다 계획값을 못 낸다 —
        # 안 적힌 것을 "안 받았다"로 읽으면 실수 하나가 기준이 된다.
        return {
            "status": "not_unaided_human",
            "judging_mode": judging_mode,
            "reason": (
                "보조받은 리허설이라 N 산정에 쓰지 않습니다."
                if judging_mode == ASSISTED_REHEARSAL else
                "판정 방식이 적혀 있지 않습니다. 도움 없이 한 기록만 계획값을 "
                "냅니다 — 안 적힌 것을 '안 받았다'로 읽지 않습니다."),
            "s_plan_seconds": None,
            "diagnostic_only": True,
            "basis": ("도움을 받았는지는 기록만 보고 알 수 없다. 다른 도구에서 "
                      "들여다본 시간은 이 탭의 활동 시간에 안 들어가므로 속도도 "
                      "보류 비율도 멀쩡해 보인다."),
        }


    # **주입한 오류로 잰 값은 하한이다.** 실제 후보는 더 미묘해 더 오래 걸린다.
    lower_bound = candidate_source != ACTUAL_DIAGNOSIS
    return {
        "status": "ok",
        "candidate_source": candidate_source,
        "s_plan_bound": "lower" if lower_bound else "estimate",
        "adoption_blocked": lower_bound,
        "adoption_note": (
            "주입한 오류로 잰 값이라 **하한**입니다. 실제 후보는 더 미묘해 "
            "사람이 더 오래 봅니다. N = (T/D)/s_plan이므로 하한을 넣으면 N이 "
            "과대해져 시간 상한이 깨집니다 — 안전계수를 명시하거나 실제 후보로 "
            "다시 재기 전에는 채택하지 않습니다."
            if lower_bound else
            "실제 진단 후보로 잰 값입니다."),
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
        "sessions_with_judgements": summary.sessions_with_judgements,
        "judged_candidates": summary.judged_candidates,
        "judging_mode": judging_mode,
        "provenance_warnings": [],
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


# ── 지속 판정의 구간 분석 (docs/sustained-pilot-protocol.md) ────────────────
#
# timing1~4는 짧은 묶음이라 **세션**을 재표집 단위로 썼다. 지속 판정은 세션이
# 하나이므로 그 방식을 못 쓴다. 대신 **판정 순서를 25건씩 끊어** 그 구간을
# 단위로 삼는다.
#
# **순서로 끊는 이유**는 피로가 시계가 아니라 작업량을 따라오기 때문이다.
# 화면을 열어 둔 시간이 아니라 "몇 번째 후보인가"가 기준이다.
INTERVAL_SIZE = 25
# 구간이 둘이면 재표집 결과가 셋뿐이라 아무것도 말하지 않는다(timing2에서
# 세션으로 겪은 것과 같은 문제). **근거가 약한 운영 기준이다.**
MIN_COMPLETE_INTERVALS = 3


@dataclass
class IntervalReport:
    """판정 순서 한 구간. **끝까지 찬 구간만 비교에 쓴다.**"""
    index: int                  # 1부터
    first: int                  # 이 구간의 첫 후보 순번 (1부터)
    last: int
    judged: int
    complete: bool              # 구간이 `INTERVAL_SIZE`만큼 찼는가
    mean_seconds: float | None = None
    median_seconds: float | None = None
    holds: int = 0
    hold_rate: float | None = None
    seconds: list[float] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "index": self.index, "first": self.first, "last": self.last,
            "judged": self.judged, "complete": self.complete,
            "mean_seconds": self.mean_seconds,
            "median_seconds": self.median_seconds,
            "holds": self.holds, "hold_rate": self.hold_rate,
        }


def judged_in_order(events: list[dict], summary: ActivitySummary) -> list[CandidateTime]:
    """판정을 끝낸 후보를 **판정한 순서대로**.

    `per_candidate`는 이름순이라 순서 정보가 없다. 구간은 순서로 끊으므로
    기록에서 순서를 되살린다 — 같은 후보를 여러 번 판정했으면 **처음 판정한
    자리**로 센다(그 뒤는 되돌아본 것이다).
    """
    seen: set[str] = set()
    order: list[str] = []
    for session in _sessions(dedupe(events)[0]):
        for event in session:
            if event.get("event") != "verdict_set":
                continue
            cid = event.get("canonical_candidate_id")
            if cid and cid not in seen:
                seen.add(cid)
                order.append(cid)

    by_id = {c.canonical_candidate_id: c for c in summary.per_candidate
             if c.judged}
    return [by_id[cid] for cid in order if cid in by_id]


def interval_reports(events: list[dict], summary: ActivitySummary,
                     size: int = INTERVAL_SIZE,
                     holds_by_candidate: dict[str, str] | None = None,
                     ) -> list[IntervalReport]:
    """판정 순서를 `size`건씩 끊어 구간별로 잰다.

    **마지막 반쪽 구간은 `complete=False`로 남긴다.** 보고는 하되 비교에는
    쓰지 않는다 — 25건과 7건의 평균을 나란히 놓으면 뒤가 흔들려 보인다.
    """
    rows = judged_in_order(events, summary)
    holds = holds_by_candidate or {}
    reports = []
    for start in range(0, len(rows), size):
        chunk = rows[start:start + size]
        seconds = [c.active_seconds for c in chunk]
        held = sum(1 for c in chunk
                   if holds.get(c.canonical_candidate_id) == "hold")
        reports.append(IntervalReport(
            index=start // size + 1,
            first=start + 1, last=start + len(chunk),
            judged=len(chunk), complete=len(chunk) == size,
            mean_seconds=(sum(seconds) / len(seconds)) if seconds else None,
            median_seconds=_percentile(seconds, 0.5),
            holds=held,
            hold_rate=(held / len(chunk)) if chunk else None,
            seconds=seconds,
        ))
    return reports


def bootstrap_mean_upper_by_interval(reports: list[IntervalReport],
                                     confidence: float = 0.95,
                                     iterations: int = 2000,
                                     seed: int = 0) -> float | None:
    """후보당 평균 시간의 보수적 상한. **재표집 단위가 구간이다.**

    **임의 문턱이 필요 없다는 것이 이 방식의 요점이다.**

    - 후반이 느려지면(피로) 느린 구간이 상한을 밀어 올린다 → 보수적
    - 후반이 빨라지면(숙련) 초반 느린 구간이 상한에 남는다 → 보수적

    어느 쪽이든 **변동이 클수록 계획값이 커진다.** "몇 % 이상 변하면 실패"를
    정하지 않아도 변동이 값에 반영된다.

    **확률 보장은 아니다.** 구간이 몇 개뿐이라 재표집 분포가 거칠고, 부트스트랩이
    가정하는 "구간이 서로 교환 가능하다"는 것도 피로가 있으면 틀린다.
    """
    usable = [r.seconds for r in reports if r.complete and r.seconds]
    if len(usable) < MIN_COMPLETE_INTERVALS:
        return None

    rng = random.Random(seed)
    means = []
    for _ in range(iterations):
        drawn: list[float] = []
        for _ in range(len(usable)):
            drawn += rng.choice(usable)
        if drawn:
            means.append(sum(drawn) / len(drawn))
    return _percentile(means, confidence)


def sustained_plan(events: list[dict], summary: ActivitySummary,
                   judging_mode: str | None = None,
                   candidate_source: str | None = None,
                   size: int = INTERVAL_SIZE, seed: int = 0,
                   holds_by_candidate: dict[str, str] | None = None) -> dict:
    """지속 판정 기록 → 구간별 결과와 계획값.

    `plan_seconds_per_candidate`와 **관문은 같다**(판정 방식·후보 출처·중복·
    순번). 다른 것은 재표집 단위와, **완성된 구간이 셋 이상이어야 한다**는
    조건뿐이다.
    """
    reports = interval_reports(events, summary, size, holds_by_candidate)
    complete = [r for r in reports if r.complete]
    base = {
        "intervals": [r.as_dict() for r in reports],
        "complete_intervals": len(complete),
        "interval_size": size,
        "minimum_intervals": MIN_COMPLETE_INTERVALS,
        "minimum_basis": ("근거가 약한 운영 기준이다. 구간이 둘이면 재표집 "
                          "결과가 셋뿐이라 아무것도 말하지 않는다."),
    }
    if complete:
        base["first_interval_mean"] = complete[0].mean_seconds
        base["last_interval_mean"] = complete[-1].mean_seconds
        if len(complete) > 1 and complete[0].mean_seconds:
            base["change_pct"] = round(
                (complete[-1].mean_seconds - complete[0].mean_seconds)
                / complete[0].mean_seconds * 100, 1)

    # 판정 방식·후보 출처·표본 관문은 기존 함수가 그대로 본다.
    # **세션 조건은 안 건다.** 지속 판정은 세션이 하나인 것이 정상이고,
    # 재표집 단위는 구간이다.
    gate = plan_seconds_per_candidate(summary, seed=seed,
                                      judging_mode=judging_mode,
                                      candidate_source=candidate_source,
                                      require_sessions=False)
    if gate["status"] != "ok":
        return {**base, **gate, "s_plan_seconds": None}

    if len(complete) < MIN_COMPLETE_INTERVALS:
        return {**base, "status": "insufficient_intervals",
                "minimum_basis": base["minimum_basis"],
                "reason": (f"완성된 구간이 {len(complete)}개다 "
                           f"(최소 {MIN_COMPLETE_INTERVALS}). 구간이 모자라면 "
                           "재표집이 변동을 못 담는다."),
                "s_plan_seconds": None}

    return {
        **base,
        "status": "ok",
        "judging_mode": judging_mode,
        "candidate_source": candidate_source,
        "mean_seconds": gate["mean_seconds"],
        "median_seconds": gate["median_seconds"],
        "p75_seconds": gate["p75_seconds"],
        "p75_basis": gate["p75_basis"],
        "s_plan_bound": gate["s_plan_bound"],
        # **지속 판정의 표본 조건은 세션이 아니라 구간이다.** `timing_usable`은
        # 세션 기준이라 여기서는 틀린 말을 한다.
        "sample_ok": True,
        "judged_candidates": gate["judged_candidates"],
        "s_plan_seconds": bootstrap_mean_upper_by_interval(
            reports, seed=seed, confidence=0.95),
        "s_plan_basis": ("후보당 평균 시간의 부트스트랩 95% 상한(**구간** 단위 "
                         "재표집). 변동이 클수록 값이 커진다 — 임의 문턱 대신 "
                         "변동을 값에 담는다. 확률 보장은 아니다."),
        "adoption_blocked": gate["adoption_blocked"],
        "adoption_note": gate["adoption_note"],
    }


# ── 처리 용량과 표본 크기는 다른 것이다 ──────────────────────────────────────
#
# 아래 계산이 내는 것은 **`N_capacity`(시간 예산으로 처리 가능한 후보 수)**이지
# 통계적으로 필요한 표본 크기가 아니다. 셋을 구분한다:
#
#   N_capacity  주어진 T·D·s_plan으로 **처리할 수 있는** 후보 수 ← 여기서 나온다
#   N_required  Δ와 검정력·정밀도 기준으로 **필요한** 후보 수    ← 미정
#   N_final     `N_required <= N_capacity`를 확인한 뒤 사전 등록하는 최종 검수량
#
# **시간이 남는다는 이유로 N을 정하지 않는다.** `N_required`가 없으면 `N_final`도
# 없다 — 필요한 것은 docs/capacity-vs-sample-size.md에 적어 두었다.
N_REQUIRED_STATUS = "undetermined"
N_FINAL_STATUS = "undetermined"

# 관측한 지속 블록은 timing5의 120건 **1회**뿐이다. 블록을 몇 번 반복한다고
# 가정하는지가 곧 근거에서 얼마나 멀어지는가다.
OBSERVED_TOTAL_BLOCKS = 1
STRONG_EXTRAPOLATION_TOTAL_BLOCKS = 10

# `s_plan`을 확률 보장이나 SLA로 읽지 않기 위한 목록. **보고서가 이것을 같이
# 찍는다** — 숫자만 옮겨 적히는 것을 막으려는 것이다.
S_PLAN_BASIS_LIMITS = (
    "판정자가 한 명이고, 그 한 명은 이 화면을 다섯 번째 쓰는 숙련자다.",
    "지속 판정은 120건 1회만 관측했다. 반복 블록 간 분산은 관측하지 않았다.",
    "다른 날의 분산(컨디션·시간대)은 관측하지 않았다.",
    "신규 사용자 속도로 일반화할 근거가 없다.",
    "후반 피로와 정상 라벨 오탐 변화는 반복 관측이 없어 추세라 말할 수 없다.",
    "확률적 상한이나 SLA가 아니다. **현재 판정자의 관측 기반 계획값**이다.",
)

# `s_plan`은 **활동(active) 판정 시간**만 잰다. 아래는 들어 있지 않다.
TIME_BASIS_EXCLUDES = (
    "블록 사이 휴식", "탭 전환", "저장 대기", "데이터셋 교체", "준비·설명 시간",
)


def evidence_range(total_blocks: int) -> str:
    """전체 블록 수 → 근거 범위 표시. **성공/실패 판정이 아니다.**

    관측한 것은 블록 1회다. 그보다 많이 반복한다고 가정할수록 근거에서 멀어진다.
    """
    if total_blocks <= OBSERVED_TOTAL_BLOCKS:
        return "observed"
    if total_blocks >= STRONG_EXTRAPOLATION_TOTAL_BLOCKS:
        return "strongly_extrapolated"
    return "extrapolated"


def _positive_finite(value) -> bool:
    """NaN·무한대·문자열·음수를 한자리에서 막는다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value > 0


def capacity_from_blocks(total_seconds: float, datasets: int,
                         block_size: int,
                         s_plan_seconds: float | None) -> dict:
    """`N_capacity` — 시간 예산으로 **처리 가능한** 데이터셋당 후보 수.

        블록당 소요 = B × s_plan        (B = 실제로 이어서 판정한 건수)
        블록 수     = floor((T/D) / 블록당 소요)
        N_capacity  = 블록 수 × B

    산술적으로는 `(T/D)/s_plan`과 같지만 **가정이 다르다.** 외삽하는 것은
    "관측한 블록을 반복한다"뿐이고, "한 시간을 쉬지 않고 같은 속도로 간다"가
    아니다.

    **한 블록을 채울 시간도 없으면 0을 돌려준다.** 120으로 올림하면 시간 상한을
    말없이 넘는다 — 그 자리가 이 함수에서 제일 위험한 곳이다.

    **`T`는 활동 판정 시간 상한이지 일정(wall-clock)이 아니다.** 휴식·탭 전환·
    저장 대기·데이터셋 교체는 `s_plan`에 없으므로 `T`에도 없다. 남는 시간
    (`unallocated_buffer_minutes`)을 **더 많은 후보에 자동으로 재할당하지 않는다.**
    """
    if not _positive_finite(s_plan_seconds):
        return {"status": "no_plan_value", "n_capacity": None,
                **_capacity_unknowns()}
    if not (_positive_finite(total_seconds) and _positive_finite(datasets)
            and _positive_finite(block_size)):
        return {"status": "missing_input", "n_capacity": None,
                **_capacity_unknowns()}

    per_block = block_size * s_plan_seconds
    blocks = int((total_seconds / datasets) // per_block)
    # **내림했다고 끝난 게 아니다.** 부동소수 나눗셈은 정확히 경계인 조합에서
    # 한 블록을 더 세기도 한다. 부등식으로 직접 되돌린다 —
    # `N_capacity × D × s_plan <= T`는 어떤 입력에서도 깨지면 안 된다.
    while blocks > 0 and blocks * block_size * datasets * s_plan_seconds > total_seconds:
        blocks -= 1

    n_capacity = blocks * block_size
    active_seconds = n_capacity * datasets * s_plan_seconds
    blocks_total = blocks * datasets
    common = {
        "block_size": block_size,
        "seconds_per_block": round(per_block, 1),
        "minutes_per_block": round(per_block / 60, 1),
        "blocks_per_dataset": blocks,
        "blocks_total": blocks_total,
        "n_capacity": n_capacity,
        "total_candidates": n_capacity * datasets,
        "expected_active_seconds": round(active_seconds, 1),
        "expected_active_minutes": round(active_seconds / 60, 1),
        "unallocated_buffer_seconds": round(total_seconds - active_seconds, 1),
        "unallocated_buffer_minutes": round((total_seconds - active_seconds) / 60, 1),
        "time_basis": ("T와 아래 수치는 **활동 판정 시간**이다. "
                       + "·".join(TIME_BASIS_EXCLUDES)
                       + "은 포함되지 않는다. wall-clock 완료 시각을 "
                         "이 표로 보장하지 않는다."),
        "n_required": None,
        "n_required_status": N_REQUIRED_STATUS,
        "n_final": None,
        "n_final_status": N_FINAL_STATUS,
    }

    if blocks == 0:
        return {**common, "status": "infeasible",
                "evidence": "none",
                "per_dataset_evidence": "none",
                "adoption_blocked": True,
                "adoption_note": (
                    f"데이터셋당 {total_seconds / datasets / 60:.1f}분으로는 "
                    f"{block_size}건 한 블록({per_block / 60:.1f}분)도 못 채운다. "
                    "블록을 채우지 못하면 올림하지 않고 0이다 — 올림하면 시간 "
                    "상한을 말없이 넘는다."),
                "note": "T를 늘리거나 D를 줄이거나 블록을 작게 다시 관측해야 한다."}

    evidence = evidence_range(blocks_total)
    per_dataset = "observed" if blocks <= OBSERVED_TOTAL_BLOCKS else evidence
    blocked = blocks > OBSERVED_TOTAL_BLOCKS
    if blocked:
        note = (f"데이터셋당 {blocks}블록을 가정한다. 관측한 것은 블록 1회뿐이라 "
                f"반복 블록 간 분산 근거가 없다 → {evidence}. 채택하려면 여러 "
                "날에 걸친 반복 지속 블록이나 추가 판정자 자료가 필요하다.")
    else:
        note = ("데이터셋당 1블록 — 관측한 범위다. 다만 전체로는 "
                f"{blocks_total}블록이라 '다른 데이터셋에서도 같은 블록이 된다'는 "
                "외삽이 남아 있다. 데이터셋 간 난이도 차이는 관측하지 않았다.")

    return {**common, "status": "ok", "evidence": evidence,
            "per_dataset_evidence": per_dataset,
            "adoption_blocked": blocked, "adoption_note": note,
            "note": ("관측한 블록을 반복한다는 가정이다. 블록 사이에는 쉰다. "
                     "블록 수가 현실적인지는 사람이 판단한다.")}


def _capacity_unknowns() -> dict:
    """입력이 모자랄 때도 **호출부가 같은 열쇠로 읽게 한다.**

    보고서가 없는 열쇠를 꺼내 판정 직후에 죽은 일이 여러 번 있었다.
    """
    return {
        "block_size": None, "seconds_per_block": None, "minutes_per_block": None,
        "blocks_per_dataset": None, "blocks_total": None,
        "total_candidates": None,
        "expected_active_seconds": None, "expected_active_minutes": None,
        "unallocated_buffer_seconds": None, "unallocated_buffer_minutes": None,
        "evidence": "none", "per_dataset_evidence": "none",
        "adoption_blocked": True,
        "adoption_note": "입력이 모자라 용량을 계산하지 않는다.",
        "time_basis": "T는 활동 판정 시간 상한이다.",
        "note": "", "n_required": None, "n_required_status": N_REQUIRED_STATUS,
        "n_final": None, "n_final_status": N_FINAL_STATUS,
    }


def capacity_table(total_minutes_options, dataset_options, block_size,
                   s_plan_seconds) -> list[dict]:
    """**시간 예산별 처리 용량 예시.** "N 표"가 아니다 — 표본 크기가 아니다.

    각 칸에 블록 수와 근거 범위를 같이 담는다. 숫자만 떼어 옮기면 15블록짜리
    조합이 1블록짜리와 같아 보인다.
    """
    rows = []
    for minutes in total_minutes_options:
        for datasets in dataset_options:
            got = capacity_from_blocks(minutes * 60, datasets, block_size,
                                       s_plan_seconds)
            rows.append({"total_minutes": minutes, "datasets": datasets, **got})
    return rows
