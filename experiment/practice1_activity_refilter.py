"""practice1 작업 기록에서 판정 뒤 UI 점검 구간을 빼고 시간 요약을 다시 낸다 (계획용, val 무관).

2026-10-07 00:39~01:07(KST) 판정 화면 점검 때 같은 평가(`practice1`)의 `activity.jsonl`에 이동 기록이
더해졌다. 원시 기록은 고치지 않고, 집계할 때 `evaluation.activity.exclude_windows`로 그 구간을 뺀다.

구간은 기록에서 정했다(`at`은 브라우저가 찍은 UTC, 'Z' 접미사. KST = UTC+9):

* 마지막 판정 세션의 마지막 이벤트 2026-10-06T15:35:55.129Z(00:35:55 KST).
* 기존 요약 커밋(3c7b1ad0) 2026-10-07 00:36:15 KST.
* 점검 첫 이벤트 2026-10-06T15:39:22.165Z(00:39:22.165 KST) — 판정 시기 탭(`…g95nj6so`)의
  `session_ended`와 새 세션의 `queue_load_started`가 같은 밀리초에 찍혔다(새로고침).
* 점검 마지막 이벤트 2026-10-06T16:06:47.422Z(01:06:47 KST).

그래서 구간은 [2026-10-06T15:39:22.165Z, 2026-10-06T16:06:48Z)로, 사용자가 말한 00:40~01:00을 기록에 맞춰
양쪽으로 넓혔다. 판정 세션과 3분 27초 떨어져 있어 판정 이벤트가 걸리지 않는다.

두 번째 구간 [2026-10-07T01:05:00Z, 2026-10-07T01:08:00Z)(10:05~10:08 KST) — 판정 화면 개편 뒤 프론트 작업의 UI 확인.
기록의 세션 `…ang8tenx`(01:07:07.408Z~01:07:59.131Z)는 이동만 있고 판정·저장이 없다.

    ./venv/Scripts/python.exe practice1_activity_refilter.py \\
        --activity ../backend/app/data/uploads/006e49d2cbc9/evaluations/practice1/activity.jsonl \\
        --adjudications ../backend/app/data/uploads/006e49d2cbc9/evaluations/practice1/adjudications.json \\
        --previous planning_evidence/practice1_judging_summary_2026-10-07.json \\
        --out planning_evidence/practice1_activity_refilter_2026-10-07.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from evaluation.activity import (_percentile, exclude_windows, read_events,
                                 summarise_activity)

PRACTICE1_UI_INSPECTION_WINDOWS = [{
    "start": "2026-10-06T15:39:22.165Z",
    "end": "2026-10-06T16:06:48Z",
    "start_local": "2026-10-07T00:39:22.165+09:00",
    "end_local": "2026-10-07T01:06:48+09:00",
    "reason": ("판정 뒤 판정 화면 UI 점검(2026-10-07 00:40~01:00 KST 무렵). 점검 세션 전체가 들어가도록 "
               "기록의 첫·마지막 이벤트에 맞춰 넓혔다"),
}, {
    "start": "2026-10-07T01:05:00Z",
    "end": "2026-10-07T01:08:00Z",
    "start_local": "2026-10-07T10:05:00+09:00",
    "end_local": "2026-10-07T10:08:00+09:00",
    "reason": ("판정 화면 개편 뒤 UI 확인(프론트 작업, 이동만). 작업자가 알린 01:05~01:08 UTC를 그대로 쓰고, "
               "기록의 해당 세션(…ang8tenx, 01:07:07.408Z~01:07:59.131Z, verdict_set·save 0건)이 전부 들어감을 확인했다"),
}]

# 기존 요약에서 다시 맞춰 볼 값 (practice1_judging_summary_2026-10-07.json의 timing·save)
COMPARED_KEYS = ("active_seconds", "adjudication_seconds", "median_seconds_per_candidate",
                 "mean_seconds_per_candidate", "p75", "p90_approx", "idle_seconds_excluded",
                 "sessions", "sessions_with_judgements", "timing_usable_flag")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timing_block(events: list[dict]) -> dict:
    """기존 요약과 같은 반올림으로 시간 값을 낸다."""
    s = summarise_activity(events)
    good = {r.session_id for r in s.session_reports if r.complete}
    times = [c.active_seconds for c in s.per_candidate if c.judged and c.session_id in good]
    r = lambda v, d: None if v is None else round(v, d)
    return {
        "active_seconds": r(s.active_seconds, 1),
        "adjudication_seconds": r(s.adjudication_seconds, 1),
        "median_seconds_per_candidate": r(s.median_seconds_per_candidate, 2),
        "mean_seconds_per_candidate": r(s.mean_seconds_per_candidate, 2),
        "p75": r(_percentile(times, 0.75), 2),
        "p90_approx": r(_percentile(times, 0.9), 2),
        "idle_seconds_excluded": r(s.idle_seconds, 1),
        "sessions": s.sessions,
        "sessions_with_judgements": s.sessions_with_judgements,
        "timing_usable_flag": s.timing_usable,
        "judged_candidates": s.judged_candidates,
        "save_failures": s.save_failures,
        "save_retries": s.save_retries,
        "incomplete_sessions": [x.session_id for x in s.session_reports if not x.complete],
    }


def _sessions_overview(events: list[dict]) -> list[dict]:
    by: dict[str, list[dict]] = {}
    for e in events:
        by.setdefault(e["session_id"], []).append(e)
    return [{"session_id": sid, "events": len(evs),
             "first_at": min(e["at"] for e in evs), "last_at": max(e["at"] for e in evs),
             "event_counts": dict(sorted(Counter(e["event"] for e in evs).items()))}
            for sid, evs in by.items()]


def _ranges(numbers: list[int]) -> list[str]:
    """[1,2,3,7,8] → ["1-3", "7-8"]."""
    out: list[str] = []
    for n in sorted(numbers):
        if out and int(out[-1].split("-")[-1]) == n - 1:
            out[-1] = f"{out[-1].split('-')[0]}-{n}"
        else:
            out.append(f"{n}-{n}")
    return out


def last_verdicts(events: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in events:
        if e.get("event") == "verdict_set":
            out[e["canonical_candidate_id"]] = (e.get("meta") or {}).get("verdict")
        elif e.get("event") == "verdict_cleared":
            out.pop(e["canonical_candidate_id"], None)
    return out


def build(activity: Path, adjudications: Path, previous: Path) -> dict:
    raw = activity.read_text(encoding="utf-8")
    events = read_events(raw)
    kept, dropped = exclude_windows(events, PRACTICE1_UI_INSPECTION_WINDOWS)
    kept_ids = {e["event_id"] for e in kept}
    kept_lines = [i + 1 for i, e in enumerate(events) if e["event_id"] in kept_ids]

    old = json.loads(previous.read_text(encoding="utf-8"))
    old_timing = old["timing"]
    new_timing = timing_block(kept)
    comparison = {k: {"previous": old_timing.get(k), "refiltered": new_timing.get(k),
                      "equal": old_timing.get(k) == new_timing.get(k)} for k in COMPARED_KEYS}
    for k in ("save_failures", "save_retries"):
        comparison[k] = {"previous": old["save"][k], "refiltered": new_timing[k],
                         "equal": old["save"][k] == new_timing[k]}

    saved = json.loads(adjudications.read_text(encoding="utf-8"))
    saved_map = {a["canonical_candidate_id"]: a["verdict"] for a in saved["adjudications"]}
    before = last_verdicts(kept)
    differs = sorted(c for c in set(before) | set(saved_map) if before.get(c) != saved_map.get(c))
    dropped_verdicts = [{"line": events.index(e) + 1, "session_id": e["session_id"],
                         "canonical_candidate_id": e["canonical_candidate_id"], "at": e["at"],
                         "verdict": (e.get("meta") or {}).get("verdict")}
                        for e in dropped if e.get("event") == "verdict_set"]

    dropped_sessions = {e["session_id"] for e in dropped}
    partial = sorted(sid for sid in dropped_sessions
                     if any(e["session_id"] == sid for e in kept))
    return {
        "name": "practice1_activity_refilter",
        "date": "2026-10-07",
        "label": ("practice1(train fit_check) 작업 기록에서 판정 뒤 UI 점검 구간 두 개를 뺀 재집계 — 계획용. "
                  "분석·논문 결과에 쓰지 않는다. val 미개봉."),
        "tool": "experiment/practice1_activity_refilter.py (evaluation.activity.exclude_windows)",
        "timestamps": {
            "field": "at",
            "format": "ISO 8601 UTC with 'Z' suffix (browser clock)",
            "local_timezone": "Korea Standard Time, UTC+09:00 (Windows Get-TimeZone)",
        },
        "raw_activity": {
            "path": "backend/app/data/uploads/006e49d2cbc9/evaluations/practice1/activity.jsonl",
            "sha256_now": _sha256(activity),
            "lines_now": len(events),
        },
        "previous_summary": {
            "file": "experiment/planning_evidence/practice1_judging_summary_2026-10-07.json",
            "commit": "3c7b1ad0 (2026-10-07 00:36:15 KST)",
            "inferred_input": {
                "lines": "1-1123",
                "events": 1123,
                "last_event_at": "2026-10-06T15:35:55.129Z",
                "basis": ("1123줄(마지막 판정 이벤트까지)에서 기존 요약의 모든 시간 값과 '끊긴 세션 1개'"
                          "(g95nj6so, session_ended가 아직 없음)가 재현된다. 1124줄이면 끊긴 세션이 0개가 되어 "
                          "기존 요약의 note와 맞지 않는다. 기존 요약 파일에는 줄 수·SHA가 적혀 있지 않아 "
                          "그때 원시 파일의 SHA-256은 알 수 없다."),
            },
        },
        "exclusion_windows": PRACTICE1_UI_INSPECTION_WINDOWS,
        "excluded": {
            "events": len(dropped),
            "lines": _ranges([events.index(e) + 1 for e in dropped]),
            "sessions": _sessions_overview(dropped),
            "sessions_partially_excluded": partial,
            "verdict_set_events": dropped_verdicts,
        },
        "kept": {"events": len(kept),
                 "lines": _ranges(kept_lines),
                 "identical_to_first_1123_lines": [e["event_id"] for e in kept]
                 == [e["event_id"] for e in events[:1123]]},
        "timing_refiltered": new_timing,
        "comparison_with_previous": comparison,
        "reproduces_previous": all(v["equal"] for v in comparison.values()),
        "adjudications": {
            "sha256_now": _sha256(adjudications),
            "updated_at": saved.get("updated_at"),
            "entries": len(saved_map),
            "verdicts_now": dict(Counter(saved_map.values())),
            "last_verdicts_before_window": dict(Counter(before.values())),
            "candidates_differing": differs,
        },
        "findings": [
            ("점검 구간 안 세션 하나(…1tgrp159, 00:50:53~00:51:01 KST)에 판정 화면 키 점검으로 보이는 verdict_set 8건과 "
             "저장 8건이 있다 — 한 후보(Ldbc6b5d4d95dac73)에 hit→miss→hold→miss→hit→miss→hold→miss. 마지막 값 miss가 "
             "점검 전 판정과 같아 저장된 판정 수는 바뀌지 않았다(차이 0건). 다만 adjudications.json이 그때 다시 쓰여 "
             "updated_at이 점검 시각이다. 점검 전 파일의 바이트·SHA-256은 남아 있지 않다."),
            ("판정 시기 탭(…g95nj6so)의 session_ended 한 건만 구간 시작 시각에 걸려 빠진다. 그 탭이 점검 새로고침으로 "
             "닫히며 찍힌 것이고, 빼야 기존 요약의 입력(1123줄)과 같아진다."),
            ("두 번째 구간(01:05~01:08 UTC = 10:05~10:08 KST)은 판정 화면 개편 뒤 UI 확인 세션 하나(…ang8tenx)다 — "
             "session·candidate_opened 22·moved_previous 1·moved_next 21, verdict_set·save 0건. 작업자는 UTC로 알렸고 "
             "기록의 at(UTC 'Z')과 맞는다."),
            "두 구간을 빼면 기존 요약의 시간·저장 값이 전부 재현된다(reproduces_previous).",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--activity", required=True)
    ap.add_argument("--adjudications", required=True)
    ap.add_argument("--previous", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"이미 있다 — 덮어쓰지 않는다: {out}")
    result = build(Path(a.activity), Path(a.adjudications), Path(a.previous))
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"reproduces_previous": result["reproduces_previous"],
                      "excluded_events": result["excluded"]["events"],
                      "kept_events": result["kept"]["events"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
