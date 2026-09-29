"""AI 보조 판정자 실행 도구 — 요청 묶음을 만들고 응답을 엄격히 읽는다. **모델을 부르지 않는다.**

사전 등록 D8(`docs/qa-preregistration.md` 5절·11절)과 프롬프트 초안
(`docs/ai-adjudicator-prompt-draft.md`)에 적힌 것만 한다:

* 입력은 `GET .../queue?adjudicator=ai`의 **가림 목록**과 `render_adjudication_images.py`의
  `manifest.json`뿐이다. 점수·순위·방법·출처·표본 여부·사람 판정은 들어오면 **거부한다**
  (렌더러와 같은 라이브러리 수준 거부).
* 응답 형식은 프롬프트에 적힌 JSON 한 줄뿐이다. 그 밖은 형식 위반으로 거부하고, 저장할 때만
  `hold`로 사상한다. 원문은 지우지 않는다.
* **모델 식별자·온도·프롬프트 원문·반복 수는 이 파일이 정하지 않는다.** 실행할 때 받는 값이고
  기본값이 없다. 실제 호출은 `--provider`가 막는다 — 비용 승인이 먼저다.

사용법 (드라이런: 아무것도 부르지 않고 요청 묶음과 실행 기록만 쓴다):

    python ai_adjudicator.py --dry-run --queue ai_queue.json --manifest out/manifest.json \\
        --prompt prompt.txt --model "<모델 식별자>" --out bundle.jsonl --run-manifest run.json \\
        [--repetitions 1] [--temperature 0]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# 판정자에게 가야 할 것이 아닌 값. 하나라도 있으면 묶음을 만들지 않는다.
FORBIDDEN_KEYS = (
    "scores", "score", "severity", "rank", "aida_rank", "ranks", "source",
    "random_sample", "suspicion", "coverage_extra", "method", "method_order",
    "ranking_version", "reason_code", "detail",
)
VERDICTS = ("hit", "miss", "hold")
SESSION_POLICY = "new conversation per candidate"
TEMPERATURE_NOT_EXPOSED = "not exposed"


class BlindingError(ValueError):
    """가려야 할 값이 입력에 있다."""


class ResponseFormatError(ValueError):
    """응답이 프롬프트가 정한 형식이 아니다."""


# ── 1. 요청 묶음 ──────────────────────────────────────────────────────────────

def _check_blinded(row: dict, where: str) -> None:
    for key in FORBIDDEN_KEYS:
        if key in row:
            raise BlindingError(f"{where}에 가려야 할 값이 있다: {key}")
    if row.get("verdict") is not None or row.get("unique_error_id") is not None:
        raise BlindingError(f"{where}에 이미 내려진 판정이 있다 — AI 입력으로 쓰지 않는다")


def _manifest_rows(rendered_manifest: Any) -> list[dict]:
    if isinstance(rendered_manifest, dict):
        rows = rendered_manifest.get("candidates") or rendered_manifest.get("entries")
        if rows is None:
            raise ValueError("manifest에 후보 목록이 없다")
        return list(rows)
    return list(rendered_manifest)


def _user_message(meta: dict) -> str:
    """프롬프트 초안 '사용자 메시지'와 같은 문구. 유도 표현을 넣지 않는다."""
    task = "기존 라벨 검수" if meta.get("task") == "labelled" else "누락 검수"
    box = meta.get("box_xyxy_px") or []
    size = meta.get("image_size") or []
    box_text = " ".join(f"{v:g}" for v in box)
    size_text = "×".join(str(v) for v in size)
    return ("[전체 장면과 대상 크롭 첨부]\n"
            f"과제: {task}\n"
            f"클래스: {meta.get('class_name')}\n"
            f"상자(원본 픽셀, x1 y1 x2 y2): {box_text}   원본 크기: {size_text}\n"
            '답: {"verdict": ..., "reason": ...}')


def build_requests(queue_json: dict, rendered_manifest: Any, prompt_text: str) -> list[dict]:
    """가림 목록 후보마다 요청 하나. 점수·순위·판정은 들어가지 않는다.

    `queue_json`은 `GET .../queue?adjudicator=ai` 응답, `rendered_manifest`는
    `render_adjudication_images.py`가 쓴 `manifest.json`(목록 또는 그것을 담은 사전)이다.
    """
    if not isinstance(prompt_text, str) or not prompt_text.strip():
        raise ValueError("프롬프트 원문이 비어 있다 — 임의로 채우지 않는다")
    candidates = list(queue_json.get("candidates") or [])
    if not candidates:
        raise ValueError("가림 목록이 비어 있다")
    for c in candidates:
        _check_blinded(c, "가림 목록")

    by_id: dict[str, dict] = {}
    for meta in _manifest_rows(rendered_manifest):
        _check_blinded(meta, "그림 manifest")
        by_id[meta["canonical_candidate_id"]] = meta

    requests = []
    for c in candidates:
        cid = c["canonical_candidate_id"]
        meta = by_id.get(cid)
        if meta is None:
            raise ValueError(f"그림이 없는 후보: {cid}")
        for key in ("file", "full_file"):
            if not meta.get(key):
                raise ValueError(f"{cid}의 그림 파일 경로가 manifest에 없다: {key}")
        requests.append({
            "canonical_candidate_id": cid,
            "task": meta.get("task"),
            "class_name": meta.get("class_name"),
            "box_xyxy_px": meta.get("box_xyxy_px"),
            "image_size": meta.get("image_size"),
            "crop_xyxy_px": meta.get("crop_xyxy_px"),
            "images": {"full_scene": meta["full_file"], "crop": meta["file"]},
            "prompt": prompt_text,
            "user_message": _user_message(meta),
            "session_policy": SESSION_POLICY,
        })
    return requests


# ── 2. 응답 읽기 ──────────────────────────────────────────────────────────────

def parse_response(text: str) -> dict:
    """프롬프트가 정한 JSON 한 줄만 받는다. 그 밖은 `ResponseFormatError`.

    돌려주는 것은 `{"verdict": hit|miss|hold, "rationale": str}`. 사상·저장은 하지 않는다 —
    형식 위반을 `hold`로 바꾸는 것은 `to_adjudications`의 일이고 원문은 따로 보존한다.
    """
    if not isinstance(text, str):
        raise ResponseFormatError("응답이 문자열이 아니다")
    stripped = text.strip()
    if not stripped:
        raise ResponseFormatError("빈 응답")
    try:
        parsed = json.loads(stripped)
    except ValueError as exc:                     # 앞뒤 설명글·코드펜스·여러 줄 모두 여기로
        raise ResponseFormatError(f"JSON 한 줄이 아니다: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ResponseFormatError("JSON 객체가 아니다")
    if set(parsed) != {"verdict", "reason"}:
        raise ResponseFormatError(f"키가 verdict·reason만이어야 한다: {sorted(parsed)}")
    verdict, reason = parsed["verdict"], parsed["reason"]
    if verdict not in VERDICTS:
        raise ResponseFormatError(f"알 수 없는 판정: {verdict!r}")
    if not isinstance(reason, str) or not reason.strip():
        raise ResponseFormatError("reason이 비어 있다")
    return {"verdict": verdict, "rationale": reason.strip()}


# ── 3. 저장 payload ──────────────────────────────────────────────────────────

def to_adjudications(responses: Any) -> dict:
    """`PUT .../adjudications?adjudicator=ai`에 보낼 몸통.

    `responses`는 응답 기록의 목록이거나 `{"candidate_set_hash": ..., "responses": [...]}`다.
    기록마다 `canonical_candidate_id`와, `raw_text`(원문) 또는 이미 읽어 둔 `verdict`가 있어야
    한다. 형식 위반·거부는 `hold`로 사상하고 그 사실을 `format_violations`에 남긴다 —
    payload 자체에는 판정만 들어간다(서버 스키마).
    """
    if isinstance(responses, dict):
        rows = list(responses.get("responses") or [])
        bundle_hash = responses.get("candidate_set_hash")
    else:
        rows, bundle_hash = list(responses), None
    if not rows:
        raise ValueError("응답이 없다")

    hashes = {r.get("candidate_set_hash") for r in rows if r.get("candidate_set_hash")}
    if bundle_hash:
        hashes.add(bundle_hash)
    if not hashes:
        raise ValueError("candidate_set_hash가 없다 — 어느 묶음의 판정인지 알 수 없다")
    if len(hashes) > 1:
        raise ValueError(f"응답이 서로 다른 묶음에 붙어 있다: {sorted(hashes)}")

    adjudications, violations, seen = [], [], set()
    for r in rows:
        cid = r.get("canonical_candidate_id")
        if not cid:
            raise ValueError("canonical_candidate_id가 없는 응답이 있다")
        if cid in seen:
            raise ValueError(f"같은 후보가 두 번 나왔다: {cid}")
        seen.add(cid)
        if r.get("verdict") in VERDICTS:
            verdict = r["verdict"]
        else:
            try:
                verdict = parse_response(r.get("raw_text", ""))["verdict"]
            except ResponseFormatError as exc:
                verdict = "hold"
                violations.append({"canonical_candidate_id": cid, "mapped_to": "hold",
                                   "error": str(exc)})
        adjudications.append({"canonical_candidate_id": cid, "verdict": verdict})
    return {"candidate_set_hash": hashes.pop(),
            "adjudications": adjudications,
            "format_violations": violations}


# ── 4. 드라이런 ──────────────────────────────────────────────────────────────

def _size_counts(requests: list[dict], images_root: Path | None, key: str) -> list[dict]:
    """실제 전송될 그림의 픽셀 크기. 파일이 있으면 파일에서, 없으면 crop 상자에서 잰다."""
    counter: Counter = Counter()
    for r in requests:
        size = None
        if images_root is not None:
            path = images_root / r["images"][key]
            if path.is_file():
                try:
                    from PIL import Image
                    with Image.open(path) as im:
                        size = tuple(im.size)
                except Exception:                 # 크기를 못 재면 추정으로 넘어간다
                    size = None
        if size is None:
            if key == "full_scene" and r.get("image_size"):
                size = tuple(r["image_size"])
            elif r.get("crop_xyxy_px"):
                x1, y1, x2, y2 = r["crop_xyxy_px"]
                size = (int(x2 - x1), int(y2 - y1))
        counter[size] += 1
    return [{"px": list(s) if s else None, "count": n}
            for s, n in sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))]


def build_run_manifest(requests: list[dict], prompt_text: str, model: str,
                       repetitions: int, temperature: Any = None,
                       images_root: Path | None = None,
                       queue_json: dict | None = None) -> dict:
    """실행 기록. 사전 등록 11절이 요구하는 칸을 채우되 **값을 지어내지 않는다.**"""
    if not model or not str(model).strip():
        raise ValueError("모델 식별자는 필수다 — 기본값이 없다")
    if repetitions < 1:
        raise ValueError("반복 수는 1 이상이다")
    return {
        "tool": "experiment/ai_adjudicator.py",
        "mode": "dry_run",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_identifier": str(model),
        "prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
        "prompt_bytes": len(prompt_text.encode("utf-8")),
        "repetitions": repetitions,
        "session_policy": SESSION_POLICY,
        "temperature": TEMPERATURE_NOT_EXPOSED if temperature is None else temperature,
        "image_sizes": {
            "full_scene": _size_counts(requests, images_root, "full_scene"),
            "crop": _size_counts(requests, images_root, "crop"),
        },
        "request_count": len(requests),
        "call_count_if_run": len(requests) * repetitions,
        "candidate_set_hash": (queue_json or {}).get("candidate_set_hash"),
        "evaluation_id": (queue_json or {}).get("evaluation_id"),
        "tasks": dict(Counter(r["task"] for r in requests)),
        "calls_made": 0,
        "note": "아무것도 부르지 않았다. 실제 호출은 비용 승인 뒤 사용자가 연다.",
    }


def write_bundle(requests: Iterable[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for r in requests:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def call_provider(*args, **kwargs):
    """일부러 막아 둔 자리. 실수로라도 호출이 나가지 않게 한다."""
    raise NotImplementedError(
        "AI 판정자 호출은 구현되어 있지 않다. 유료 모델 호출이므로 "
        "**사용자가 비용 상한과 모델 식별자를 먼저 승인**해야 한다. "
        "승인 전까지 이 도구는 --dry-run만 한다.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI 보조 판정자 요청 묶음 (드라이런 전용)")
    ap.add_argument("--queue", required=True, help="GET .../queue?adjudicator=ai 응답 JSON")
    ap.add_argument("--manifest", required=True, help="render_adjudication_images.py의 manifest.json")
    ap.add_argument("--prompt", required=True, help="프롬프트 원문 파일")
    ap.add_argument("--model", required=True, help="모델 식별자 — 기본값 없음, 사용자가 정한다")
    ap.add_argument("--out", required=True, help="요청 묶음 JSONL")
    ap.add_argument("--run-manifest", required=True, help="실행 기록 JSON")
    ap.add_argument("--repetitions", type=int, default=1)
    ap.add_argument("--temperature", default=None,
                    help="설정 가능할 때만 적는다. 없으면 'not exposed'로 기록한다")
    ap.add_argument("--dry-run", action="store_true", help="아무것도 부르지 않는다")
    ap.add_argument("--provider", default=None, help="막혀 있다 — 비용 승인 전에는 열지 않는다")
    a = ap.parse_args(argv)

    if a.provider:
        call_provider(a.provider)               # 항상 NotImplementedError
    if not a.dry_run:
        raise SystemExit("--dry-run만 지원한다. 실제 호출은 비용 승인 뒤에 연다.")

    queue = json.loads(Path(a.queue).read_text(encoding="utf-8"))
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    prompt = Path(a.prompt).read_text(encoding="utf-8")
    requests = build_requests(queue, manifest, prompt)
    n = write_bundle(requests, Path(a.out))
    run = build_run_manifest(requests, prompt, a.model, a.repetitions, a.temperature,
                             images_root=Path(a.manifest).parent, queue_json=queue)
    Path(a.run_manifest).parent.mkdir(parents=True, exist_ok=True)
    Path(a.run_manifest).write_text(json.dumps(run, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    line = (f"요청 {n}건 → {a.out} (호출 0건, 모델 {run['model_identifier']}, "
            f"반복 {run['repetitions']}, 온도 {run['temperature']})")
    try:
        print(line)
    except UnicodeEncodeError:                  # 콘솔 인코딩이 좁으면 옮겨 적는다
        enc = (getattr(__import__("sys").stdout, "encoding", None) or "ascii")
        print(line.encode(enc, "backslashreplace").decode(enc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
