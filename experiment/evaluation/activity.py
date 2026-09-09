"""판정 작업 시간 (docs/pilot-evaluation-plan.md).

**"페이지를 열어 둔 시간"은 검수 시간이 아니다.** 탭을 열어 두고 점심을 먹으면
검수가 느린 것처럼 보이고, 화면을 미리 띄워 두고 재면 빨라 보인다. 둘 다 사람이
실제로 쓴 시간이 아니다.

그래서 원시 이벤트만 저장하고 **계산은 여기서 따로 한다.** 화면이 요약을 만들면
그 숫자가 화면에 뜨기 쉽고(판정자가 보고 판단을 조절한다), 규칙을 고칠 때 이미
저장된 기록을 다시 계산할 수 없다.

표준 라이브러리만 쓴다 — CI에 numpy가 없다.
"""
import json
from dataclasses import dataclass, field

from .schema import ValidationError

# 기록 형식의 판. 화면 쪽 `EVENT_SCHEMA_VERSION`과 같은 값이다.
SUPPORTED_EVENT_VERSION = 1

# 마지막 입력 뒤 이만큼을 넘긴 구간은 활동 시간에서 뺀다.
# **결과를 보기 전에 정했다**(docs/pilot-evaluation-plan.md). 바꾸려면 이유와
# 바꾸기 전후 수치를 그 문서에 적는다.
IDLE_THRESHOLD_SECONDS = 60.0

# 사람이 무언가를 한 이벤트. 이것들 사이가 활동 구간이다.
INPUT_EVENTS = frozenset({
    "candidate_opened", "verdict_set", "verdict_cleared",
    "missing_object_created", "missing_object_linked",
    "moved_previous", "moved_next", "save_retried",
})

# 사람이 아니라 기계를 기다린 구간.
WAIT_START = "save_started"
WAIT_END = frozenset({"save_succeeded", "save_failed"})

# 누락 객체를 만들거나 잇는 작업. **이 이벤트로 끝나는 구간**을 따로 잡는다 —
# 어느 객체인지 고르는 시간이 그 작업이다. 이 작업만 유독 오래 걸리면 누락
# 층의 비용이 따로 보여야 한다.
MISSING_LINK_EVENTS = frozenset({"missing_object_created",
                                 "missing_object_linked"})


@dataclass
class CandidateTime:
    canonical_candidate_id: str
    active_seconds: float = 0.0
    missing_link_seconds: float = 0.0
    # 판정을 몇 번 바꿨는가. **후보 수를 세는 데는 안 쓴다** — 같은 후보를 두 번
    # 세면 후보당 시간이 줄어 N이 부풀려진다.
    verdict_changes: int = 0
    judged: bool = False


@dataclass
class ActivitySummary:
    wall_seconds: float = 0.0
    active_seconds: float = 0.0
    wait_seconds: float = 0.0
    save_retry_seconds: float = 0.0
    idle_seconds: float = 0.0
    adjudication_seconds: float = 0.0
    missing_link_seconds: float = 0.0
    judged_candidates: int = 0
    opened_candidates: int = 0
    holds: int = 0
    hold_rate: float | None = None
    median_seconds_per_candidate: float | None = None
    p75_seconds_per_candidate: float | None = None
    save_failures: int = 0
    save_retries: int = 0
    sessions: int = 0
    per_candidate: list[CandidateTime] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "wall_seconds": round(self.wall_seconds, 3),
            "active_seconds": round(self.active_seconds, 3),
            "wait_seconds": round(self.wait_seconds, 3),
            "save_retry_seconds": round(self.save_retry_seconds, 3),
            "idle_seconds": round(self.idle_seconds, 3),
            "adjudication_seconds": round(self.adjudication_seconds, 3),
            "missing_link_seconds": round(self.missing_link_seconds, 3),
            "judged_candidates": self.judged_candidates,
            "opened_candidates": self.opened_candidates,
            "holds": self.holds,
            "hold_rate": self.hold_rate,
            "median_seconds_per_candidate": self.median_seconds_per_candidate,
            "p75_seconds_per_candidate": self.p75_seconds_per_candidate,
            "save_failures": self.save_failures,
            "save_retries": self.save_retries,
            "sessions": self.sessions,
            "per_candidate": [
                {"canonical_candidate_id": c.canonical_candidate_id,
                 "active_seconds": round(c.active_seconds, 3),
                 "missing_link_seconds": round(c.missing_link_seconds, 3),
                 "verdict_changes": c.verdict_changes,
                 "judged": c.judged}
                for c in self.per_candidate
            ],
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
            raise ValidationError(f"elapsed_ms가 수가 아니다: {e.get('elapsed_ms')!r}")
        if not e.get("session_id"):
            raise ValidationError("session_id가 없다")


def _sessions(events: list[dict]) -> list[list[dict]]:
    """세션별로 나눈다. **새로고침하면 새 세션이다.**

    `elapsed_ms`는 세션 안에서만 뜻이 있다 — 세션이 바뀌면 0부터 다시 센다.
    섞어서 빼면 음수가 나온다.
    """
    grouped: dict[str, list[dict]] = {}
    order: list[str] = []
    for e in events:
        sid = e["session_id"]
        if sid not in grouped:
            grouped[sid] = []
            order.append(sid)
        grouped[sid].append(e)
    return [sorted(grouped[sid], key=lambda e: e["elapsed_ms"]) for sid in order]


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

    **활동 시간은 "사람이 한 일" 사이의 간격을 더한 것이다.** 이벤트 사이의
    간격마다 그 구간이 활동이었는지 판단한다.

    | 빼는 구간 | 왜 |
    |---|---|
    | 탭이 숨은 동안 | 화면을 안 보고 있었다 |
    | 창이 포커스를 잃은 동안 | 다른 일을 하고 있었다 |
    | 마지막 입력 뒤 문턱을 넘긴 부분 | 자리를 비웠다 |
    | 저장을 기다린 동안 | 기계가 느린 것은 검수 비용이 아니다 |

    **문턱까지는 남긴다.** 넘겼다고 구간을 통째로 0으로 만들면 어려운 후보가
    공짜가 된다 — 박스 하나를 1분 넘게 들여다보는 일은 실제로 있다.
    """
    if not events:
        return ActivitySummary()
    _check(events)

    summary = ActivitySummary()
    per_candidate: dict[str, CandidateTime] = {}
    holds_by_candidate: dict[str, str | None] = {}

    for session in _sessions(events):
        summary.sessions += 1
        summary.wall_seconds += (session[-1]["elapsed_ms"]
                                 - session[0]["elapsed_ms"]) / 1000.0

        visible = True
        focused = True
        waiting = False
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

            if waiting:
                # 기계를 기다린 구간. 사람 시간이 아니다.
                summary.wait_seconds += gap
                if recovering:
                    summary.save_retry_seconds += gap
            elif recovering:
                # 실패를 보고 다시 누르기까지. 검수 시간에서 뺀다.
                summary.save_retry_seconds += gap
            elif not visible or not focused:
                pass                      # 화면을 안 보고 있었다
            else:
                # **문턱까지는 남긴다.** 넘겼다고 구간을 통째로 0으로 만들면
                # 어려운 후보가 공짜가 된다.
                allowed = max(0.0, idle_threshold - since_input)
                counted = min(gap, allowed)
                summary.idle_seconds += gap - counted
                summary.active_seconds += counted
                since_input += counted
                if current is not None and counted:
                    slot = per_candidate.setdefault(
                        current, CandidateTime(current))
                    slot.active_seconds += counted
                    # **만든 뒤가 아니라 만들기까지가 그 작업이다.** 어느
                    # 객체인지 고르는 시간은 이 이벤트로 **끝난다.** 뒤를 세면
                    # 대개 저장을 기다리는 시간이라 늘 0이 된다 — dry pilot에서
                    # 그렇게 나와 잡혔다.
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
                    per_candidate.setdefault(current, CandidateTime(current))
            elif name == WAIT_START:
                waiting = True
            elif name in WAIT_END:
                waiting = False
                if name == "save_failed":
                    summary.save_failures += 1
                    recovering = True
                else:
                    recovering = False
            elif name == "save_retried":
                summary.save_retries += 1
            elif name == "verdict_set":
                cid = event.get("canonical_candidate_id")
                if cid:
                    slot = per_candidate.setdefault(cid, CandidateTime(cid))
                    slot.verdict_changes += 1
                    slot.judged = True
                    holds_by_candidate[cid] = event.get("meta", {}).get("verdict")
            elif name == "verdict_cleared":
                cid = event.get("canonical_candidate_id")
                if cid:
                    slot = per_candidate.setdefault(cid, CandidateTime(cid))
                    slot.verdict_changes += 1
                    slot.judged = False
                    holds_by_candidate.pop(cid, None)

    summary.per_candidate = [per_candidate[k] for k in sorted(per_candidate)]
    summary.opened_candidates = len(summary.per_candidate)
    # **판정을 바꿔도 후보 하나로 센다.** 두 번 세면 후보당 시간이 줄어 N이
    # 부풀려진다. **보류도 작업한 후보다** — 사람이 시간을 썼다.
    judged = [c for c in summary.per_candidate if c.judged]
    summary.judged_candidates = len(judged)
    summary.holds = sum(1 for v in holds_by_candidate.values() if v == "hold")
    summary.hold_rate = (summary.holds / len(judged)) if judged else None

    summary.missing_link_seconds = sum(c.missing_link_seconds
                                       for c in summary.per_candidate)
    summary.adjudication_seconds = (summary.active_seconds
                                    - summary.missing_link_seconds)

    times = [c.active_seconds for c in judged]
    summary.median_seconds_per_candidate = _percentile(times, 0.5)
    summary.p75_seconds_per_candidate = _percentile(times, 0.75)
    return summary


def budget_from_pilot(total_seconds: float, datasets: int,
                      p75_seconds_per_candidate: float | None) -> int | None:
    """예비 평가의 P75로 데이터셋별 예산 N을 낸다.

        N = floor((T / D) / P75)

    **평균이 아니라 P75를 쓴다.** 평균으로 잡으면 절반의 경우 상한을 넘는다.
    시간 상한은 지키라고 두는 것이므로 보수적인 쪽이 맞다.

    **입력이 없으면 숫자를 지어내지 않고 `None`을 돌려준다.** `D`와 `T`는
    사용자가 정하고, P75는 예비 평가에서 나온다 — 셋이 다 있어야 계산이다.

    이 값을 그대로 쓰기 전에 세 가지를 확인한다(docs/pilot-evaluation-plan.md):
    각 데이터셋에 후보가 N개 이상 있는가, N이 너무 작아 부트스트랩이
    무의미해지지 않는가, 총 검수량이 `D × N`인가.
    """
    if not p75_seconds_per_candidate or p75_seconds_per_candidate <= 0:
        return None
    if datasets <= 0 or total_seconds <= 0:
        return None
    return int((total_seconds / datasets) // p75_seconds_per_candidate)


def delta_scenarios(budget: int | None) -> list[dict]:
    """Δ 선택지. **고르지 않는다 — 늘어놓기만 한다.**

    Δ는 "이만큼 더 찾아야 쓸모 있다"는 사업적 최소 기준이다. 예비 평가에서
    관측한 성능 차이를 보고 정하면 기준이 아니라 결과에 맞춘 설명이 된다.

    ROI 안은 여기서 계산하지 않는다 — 검수 인건비와 오류 하나를 놓쳤을 때의
    비용이 이 저장소에 없다.
    """
    import math

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
