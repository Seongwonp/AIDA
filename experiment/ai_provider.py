"""AI 보조 판정자 **호출 경로** (Anthropic Messages API) — 준비만 됐고, 여기서는 돌리지 않는다.

**지금 허용되는 것은 합성 비용 드라이런뿐이다**(사용자 결정 2026-10-07):

* 입력은 `make_synthetic_ai_dryrun.py`가 만든 합성 그림만(`evaluation.provenance.check_synthetic_inputs`) —
  nuImages 그림(val·연습·크롭·썸네일)은 라이선스·외부 전송 허가를 따로 확인하기 전까지 **어떤 경우에도 보내지 않는다.**
* 후보 최대 20건, 비용 하드 상한 **$1**(`DRYRUN_COST_CAP_USD`). 호출 전에 최대 예상 비용을 계산해 $1을 넘을 수 있으면
  시작하지 않는다.
* 실제 호출에는 `--approve-external-call`이 있어야 하고, SDK(`anthropic`)와 API 키가 있어야 한다. 하나라도 없으면 거부한다.
  `--dry-run`은 네트워크·SDK 없이 요청 묶음과 최대 예상 비용만 쓴다.

계약(사전 등록 5-4절):

* 모델 식별자는 정확히 `claude-sonnet-5`. 응답의 `model`이 다르면 **즉시 멈춘다**(남은 후보는 `ai_unjudged`).
* `temperature=0`을 요청에 명시한다. **0이어도 결정성은 보장되지 않는다.** 제공자가 이 값을 거부하면(400) 비재시도 오류로
  멈추고 그 사실을 기록한다 — 값을 바꿔 다시 보내지 않는다.
* 후보마다 새 요청 하나(대화 이어 붙이지 않음). 재시도는 응답을 받지 못한 네트워크·서버 오류(시간 초과·연결 실패·429·
  529·5xx)만. 형식 오류는 다시 묻지도 고치지도 않고 원문과 함께 `ai_format_error`.
* 비용 상한으로 처리하지 못한 후보는 `ai_unjudged`(hold 아님)이고 실행은 거기서 멈춘다.
* 실행 기록: API 버전·SDK 버전·프롬프트/스키마 SHA-256·그림 SHA-256과 픽셀 크기·토큰 사용량·실제 비용·시간 제한·시도 수.

    # 드라이런(네트워크 없음)
    python ai_provider.py --dry-run --queue runs_ai_dryrun/synthetic_v1/queue.json \\
        --manifest runs_ai_dryrun/synthetic_v1/rendered/manifest.json --prompt-draft ../docs/ai-adjudicator-prompt-draft.md \\
        --expected-prompt-sha256 <5-4절 값> --model claude-sonnet-5 --max-output-tokens 1024 --thinking disabled \\
        --timeout-seconds 60 --max-attempts 3 --price-input-per-mtok <단가> --price-output-per-mtok <단가> \\
        --price-source "<문서 주소·읽은 시각>" --out-dir runs_ai_dryrun/synthetic_v1/dryrun
"""
from __future__ import annotations

import argparse
import base64
import importlib
import json
import math
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_adjudicator as A  # noqa: E402
from evaluation.provenance import (SYNTHETIC_DRYRUN, ProvenanceError,  # noqa: E402
                                   check_synthetic_inputs)

MODEL_ID = A.MODEL_ID
TEMPERATURE = A.TEMPERATURE
DRYRUN_COST_CAP_USD = 1.0
DRYRUN_MAX_CANDIDATES = 20
THINKING_CHOICES = ("disabled", "adaptive")
TEMPERATURE_NOTE = "temperature=0을 요청에 명시했다. 0이어도 같은 입력에 같은 출력이 나온다는 보장은 없다(결정성 비보장)."

# 입력 토큰 상한 추정 — **검증 필요.** 그림 토큰 공식은 제공자 문서로 확인해야 한다. 두 근사(28×28 패치당 1토큰,
# 픽셀 수/750) 중 큰 값에 안전 계수 1.5를 곱하고, 글자는 UTF-8 바이트 수(토큰 수의 상한으로 쓴다)를 더한다.
IMAGE_PATCH_PX = 28
IMAGE_PX_PER_TOKEN = 750
IMAGE_SAFETY = 1.5
TEXT_OVERHEAD_TOKENS = 64


class ExternalCallRefused(RuntimeError):
    """외부 호출의 전제 조건이 하나라도 빠졌다 — 부르지 않는다."""


class TransientProviderError(RuntimeError):
    """응답을 받지 못한 네트워크·서버 오류 — 재시도 대상."""


class FatalProviderError(RuntimeError):
    """재시도하지 않는 오류(400·401·403·404 등) — 실행을 멈춘다."""


class ModelMismatchError(RuntimeError):
    """응답의 모델 식별자가 요청과 다르다 — 즉시 멈춘다."""


# ── 토큰·비용 상한 ───────────────────────────────────────────────────────────

def image_token_upper_bound(width: int, height: int) -> int:
    patches = math.ceil(width / IMAGE_PATCH_PX) * math.ceil(height / IMAGE_PATCH_PX)
    by_area = math.ceil(width * height / IMAGE_PX_PER_TOKEN)
    return math.ceil(max(patches, by_area) * IMAGE_SAFETY)


def _png_size(path: Path) -> tuple[int, int]:
    from PIL import Image
    with Image.open(path) as im:
        return tuple(im.size)


def input_token_upper_bound(request: dict, images_root: Path) -> dict:
    sizes = {k: _png_size(images_root / request["images"][k]) for k in ("full_scene", "crop")}
    image_tokens = sum(image_token_upper_bound(*wh) for wh in sizes.values())
    text_bytes = len(request["prompt"].encode("utf-8")) + len(request["user_message"].encode("utf-8"))
    return {"image_px": {k: list(v) for k, v in sizes.items()},
            "upper_bound_input_tokens": image_tokens + text_bytes + TEXT_OVERHEAD_TOKENS}


def projected_max_cost(requests: list[dict], images_root: Path, guard: A.CostGuard,
                       max_output_tokens: int) -> dict:
    per = {r["canonical_candidate_id"]: input_token_upper_bound(r, images_root) for r in requests}
    total = sum(guard.cost(v["upper_bound_input_tokens"], max_output_tokens) for v in per.values())
    return {"per_candidate": per, "max_output_tokens": max_output_tokens,
            "projected_max_usd": round(total, 6), "cap_usd": guard.cap_usd,
            "method": ("후보마다 (그림 두 장 토큰 상한 + 글자 UTF-8 바이트 + 64) × 입력 단가 + max_tokens × 출력 단가. "
                       "그림 토큰 상한 = max(28px 패치 수, 픽셀/750) × 1.5 — 공식은 제공자 문서로 검증 필요")}


# ── 요청 ────────────────────────────────────────────────────────────────────

def build_payload(request: dict, images_root: Path, *, model: str, max_tokens: int, thinking: str) -> dict:
    """Messages API 요청 몸통. 후보마다 새 요청 — 이전 대화를 붙이지 않는다.

    [검증 필요] 필드 모양은 claude-api 스킬 참조(2026-09-25 캐시)를 따랐다: 이미지 블록
    `{"type":"image","source":{"type":"base64","media_type":"image/png","data":...}}`, 그림을 글보다 앞에,
    `thinking={"type": "disabled"|"adaptive"}`, `temperature` 최상위.
    """
    def image_block(name: str) -> dict:
        data = base64.standard_b64encode((images_root / name).read_bytes()).decode("ascii")
        return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}

    return {
        "model": model,
        "max_tokens": int(max_tokens),
        "temperature": TEMPERATURE,
        "thinking": {"type": thinking},
        "system": request["prompt"],
        "messages": [{"role": "user", "content": [
            image_block(request["images"]["full_scene"]),
            image_block(request["images"]["crop"]),
            {"type": "text", "text": request["user_message"]},
        ]}],
    }


def normalise_response(msg: Any) -> dict:
    """SDK 응답 객체(또는 검사용 dict)를 기록용 dict로. 글 블록만 이어 붙여 원문으로 쓴다."""
    raw = msg.to_dict() if hasattr(msg, "to_dict") else dict(msg)
    blocks = raw.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    usage = raw.get("usage") or {}
    return {"model": raw.get("model"), "text": text, "stop_reason": raw.get("stop_reason"),
            "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens",
                                                 "cache_creation_input_tokens", "cache_read_input_tokens")},
            "request_id": getattr(msg, "_request_id", None) or raw.get("_request_id"),
            "raw": raw}


# ── 실행 ────────────────────────────────────────────────────────────────────

def run_candidates(requests: list[dict], send: Callable[[dict], Any], *, guard: A.CostGuard,
                   images_root: Path, model: str, max_tokens: int, thinking: str, max_attempts: int,
                   sleep: Callable[[float], None] = time.sleep, backoff_seconds: float = 2.0) -> dict:
    """후보마다 한 번 보낸다. `send(payload)`는 응답을 돌려주거나 Transient/FatalProviderError를 던진다."""
    if model != MODEL_ID:
        raise ExternalCallRefused(f"모델 식별자는 정확히 {MODEL_ID}여야 한다: {model!r}")
    if max_attempts < 1:
        raise ValueError("최대 시도 수는 1 이상")
    records: list[dict] = []
    stop_reason: str | None = None

    def unjudged_rest(start: int, reason: str) -> None:
        for r in requests[start:]:
            records.append({"canonical_candidate_id": r["canonical_candidate_id"], "status": A.AI_UNJUDGED,
                            "reason": reason, "attempts": 0})

    for idx, req in enumerate(requests):
        cid = req["canonical_candidate_id"]
        bound = input_token_upper_bound(req, images_root)
        try:
            guard.before_call(bound["upper_bound_input_tokens"], max_tokens)
        except A.CostCapError as exc:
            stop_reason = "cost_cap"
            unjudged_rest(idx, f"cost_cap: {exc}")
            break
        payload = build_payload(req, images_root, model=model, max_tokens=max_tokens, thinking=thinking)
        errors, response, attempts = [], None, 0
        try:
            for attempt in range(1, max_attempts + 1):
                attempts = attempt
                try:
                    response = normalise_response(send(payload))
                    break
                except TransientProviderError as exc:
                    errors.append({"attempt": attempt, "kind": "transient", "error": str(exc)})
                    if attempt < max_attempts:
                        sleep(backoff_seconds * (2 ** (attempt - 1)))
        except FatalProviderError as exc:
            errors.append({"attempt": attempts, "kind": "fatal", "error": str(exc)})
            records.append({"canonical_candidate_id": cid, "status": A.AI_UNJUDGED, "reason": "fatal_error",
                            "attempts": attempts, "errors": errors})
            stop_reason = "fatal_error"
            unjudged_rest(idx + 1, "run_stopped: fatal_error")
            break
        if response is None:
            records.append({"canonical_candidate_id": cid, "status": A.AI_UNJUDGED,
                            "reason": "no_response_after_max_attempts", "attempts": attempts, "errors": errors})
            continue
        usage = response["usage"]
        in_tok, out_tok = int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
        cost = guard.cost(in_tok, out_tok)
        record = {"canonical_candidate_id": cid, "attempts": attempts, "errors": errors,
                  "response_model": response["model"], "stop_reason": response["stop_reason"],
                  "usage": usage, "cost_usd": round(cost, 6), "request_id": response["request_id"],
                  "raw_text": response["text"], "raw_response": response["raw"],
                  "image_px": bound["image_px"]}
        cap_exc = None
        try:
            guard.record(in_tok, out_tok)
        except A.CostCapError as exc:
            cap_exc = exc
        if response["model"] != model:
            record.update(status=A.AI_UNJUDGED, reason=f"model_mismatch: 요청 {model!r}, 응답 {response['model']!r}")
            records.append(record)
            stop_reason = "model_mismatch"
            unjudged_rest(idx + 1, "run_stopped: model_mismatch")
            break
        try:
            parsed = A.parse_response(response["text"])
            record.update(status=A.AI_JUDGED, verdict=parsed["verdict"], rationale=parsed["rationale"])
        except A.ResponseFormatError as exc:
            record.update(status=A.AI_FORMAT_ERROR, format_error=str(exc))
        records.append(record)
        if cap_exc is not None:
            stop_reason = "cost_cap"
            unjudged_rest(idx + 1, f"cost_cap: {cap_exc}")
            break
    counts = {s: sum(1 for r in records if r["status"] == s) for s in A.AI_STATUSES}
    return {"candidates": records, "stop_reason": stop_reason, "counts": counts,
            "complete": stop_reason is None and counts[A.AI_UNJUDGED] == 0,
            "cost_guard": guard.as_dict()}


# ── Anthropic SDK 연결 (지연 import) ─────────────────────────────────────────

def make_anthropic_sender(timeout_seconds: float) -> tuple[Callable[[dict], Any], dict]:
    """SDK가 없거나 API 키가 없으면 `ExternalCallRefused`. 키 값은 읽어 쓰기만 하고 기록·출력하지 않는다.

    SDK 자체 재시도는 끈다(`max_retries=0`) — 재시도 수는 이 도구의 `max_attempts`가 정한다.
    [검증 필요] 오류 클래스 이름(`APITimeoutError`·`APIConnectionError`·`RateLimitError`·`InternalServerError`·
    `APIStatusError`)과 `__version__`은 claude-api 스킬 참조를 따랐다. 실제 SDK에서 확인한다.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ExternalCallRefused("ANTHROPIC_API_KEY가 없다 — 부르지 않는다")
    try:
        sdk = importlib.import_module("anthropic")
    except ImportError as exc:
        raise ExternalCallRefused("anthropic SDK가 설치돼 있지 않다 — 부르지 않는다(설치는 사용자 승인 뒤)") from exc
    client = sdk.Anthropic(timeout=float(timeout_seconds), max_retries=0)
    transient = tuple(getattr(sdk, n) for n in ("APITimeoutError", "APIConnectionError", "RateLimitError",
                                                 "InternalServerError") if hasattr(sdk, n))
    status_error = getattr(sdk, "APIStatusError", None)

    def send(payload: dict) -> Any:
        try:
            return client.messages.create(**payload)
        except transient as exc:
            raise TransientProviderError(f"{type(exc).__name__}: {exc}") from exc
        except Exception as exc:                 # noqa: BLE001 — 분류 뒤 다시 던진다
            code = getattr(exc, "status_code", None)
            if status_error is not None and isinstance(exc, status_error) and code is not None \
                    and (code == 429 or code == 529 or code >= 500):
                raise TransientProviderError(f"{type(exc).__name__} {code}: {exc}") from exc
            raise FatalProviderError(f"{type(exc).__name__} {code}: {exc}") from exc

    info = {"sdk": "anthropic", "sdk_version": getattr(sdk, "__version__", "미확인"),
            "api_version": (getattr(client, "default_headers", {}) or {}).get("anthropic-version", "미확인"),
            "sdk_max_retries": 0, "timeout_seconds": float(timeout_seconds)}
    return send, info


# ── 전제 조건 ────────────────────────────────────────────────────────────────

def _verify_reproducible(images_root: Path, provenance: dict) -> None:
    """합성 그림을 같은 씨앗으로 다시 만들어 바이트가 같은지 본다 — 합성 표시만 붙인 다른 그림을 막는다."""
    import make_synthetic_ai_dryrun as G
    with tempfile.TemporaryDirectory() as tmp:
        again = G.generate(Path(tmp) / "regen", scenes=int(provenance["scenes"]), seed=int(provenance["seed"]),
                           candidates=int(provenance["candidates"]))
    listed = json.loads((images_root / "provenance.json").read_text(encoding="utf-8"))["files"]
    if again["files"] != listed:
        raise ProvenanceError("합성 그림을 같은 씨앗으로 다시 만들었더니 바이트가 다르다 — 보내지 않는다")


def check_inputs(requests: list[dict], images_root: Path, queue: dict, deny: dict | None = None,
                 verify_reproducible: bool = True) -> dict:
    if queue.get("provenance") != SYNTHETIC_DRYRUN:
        raise ProvenanceError("가림 목록의 출처 표시가 synthetic_dryrun이 아니다 — 외부로 보내지 않는다")
    if len(requests) > DRYRUN_MAX_CANDIDATES:
        raise ExternalCallRefused(f"드라이런 후보는 최대 {DRYRUN_MAX_CANDIDATES}건: {len(requests)}")
    files = [r["images"][k] for r in requests for k in ("full_scene", "crop")]
    checked = check_synthetic_inputs(images_root, files, deny=deny)
    meta = json.loads((images_root / "provenance.json").read_text(encoding="utf-8"))
    if verify_reproducible:
        _verify_reproducible(images_root, meta)
    checked["reproducible_verified"] = bool(verify_reproducible)
    return checked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI 보조 판정자 호출 경로 — 합성 비용 드라이런 전용")
    ap.add_argument("--queue", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--prompt-draft", required=True, help="docs/ai-adjudicator-prompt-draft.md")
    ap.add_argument("--expected-prompt-sha256", required=True, help="사전 등록 5-4절의 시스템 프롬프트 지문")
    ap.add_argument("--model", required=True)
    ap.add_argument("--max-output-tokens", type=int, required=True)
    ap.add_argument("--thinking", choices=THINKING_CHOICES, required=True)
    ap.add_argument("--timeout-seconds", type=float, required=True)
    ap.add_argument("--max-attempts", type=int, required=True)
    ap.add_argument("--price-input-per-mtok", type=float, required=True)
    ap.add_argument("--price-output-per-mtok", type=float, required=True)
    ap.add_argument("--price-source", required=True)
    ap.add_argument("--cost-cap", type=float, default=DRYRUN_COST_CAP_USD,
                    help=f"USD, 최대 {DRYRUN_COST_CAP_USD:g}")
    ap.add_argument("--out-dir", required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="네트워크·SDK 없이 요청 묶음과 최대 예상 비용만")
    mode.add_argument("--approve-external-call", action="store_true",
                      help="사용자가 이번 합성 드라이런의 외부 호출을 승인했다")
    a = ap.parse_args(argv)

    if a.model != MODEL_ID:
        raise SystemExit(f"모델 식별자는 정확히 {MODEL_ID}: {a.model!r}")
    if not 0 < a.cost_cap <= DRYRUN_COST_CAP_USD:
        raise SystemExit(f"드라이런 비용 상한은 0 초과 ${DRYRUN_COST_CAP_USD:g} 이하: {a.cost_cap}")
    if a.max_output_tokens < 1 or a.max_attempts < 1 or a.timeout_seconds <= 0:
        raise SystemExit("max_tokens·최대 시도 수·시간 제한은 양수")
    out = Path(a.out_dir)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"이미 산출물이 있다 — 덮어쓰지 않는다: {out}")

    draft = Path(a.prompt_draft).read_text(encoding="utf-8")
    blocks = A.prompt_blocks_from_draft(draft)
    prompt = blocks["system"]
    if A.sha256_text(prompt) != a.expected_prompt_sha256:
        raise SystemExit("프롬프트 지문이 사전 등록 값과 다르다 — 묶음을 만들지 않는다")
    queue = json.loads(Path(a.queue).read_text(encoding="utf-8"))
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    images_root = Path(a.manifest).parent
    requests = A.build_requests(queue, manifest, prompt)
    try:
        checked = check_inputs(requests, images_root, queue)
    except (ProvenanceError, ExternalCallRefused) as exc:
        raise SystemExit(f"입력 출처 점검에서 멈췄다: {exc}") from exc

    guard = A.CostGuard(a.price_input_per_mtok, a.price_output_per_mtok, a.price_source, cap_usd=a.cost_cap)
    projection = projected_max_cost(requests, images_root, guard, a.max_output_tokens)
    if projection["projected_max_usd"] > guard.cap_usd:
        raise SystemExit(f"최대 예상 비용 ${projection['projected_max_usd']:.4f}가 상한 ${guard.cap_usd:g}를 넘을 수 "
                         "있다 — 시작하지 않는다")

    header = {
        "tool": "experiment/ai_provider.py", "provenance": SYNTHETIC_DRYRUN,
        "purpose": "비용·API 계약 점검 전용. 정확도·난이도·모델 성능·일치도의 근거가 아니다.",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_requested": a.model, "temperature": TEMPERATURE, "temperature_note": TEMPERATURE_NOTE,
        "thinking": a.thinking, "max_tokens": a.max_output_tokens,
        "timeout_seconds": a.timeout_seconds, "max_attempts": a.max_attempts, "retry_policy": A.RETRY_POLICY,
        "session_policy": A.SESSION_POLICY, "repetitions": 1,
        "prompt_sha256": A.sha256_text(prompt), "user_template_sha256": A.sha256_text(blocks["user_template"]),
        "response_schema_sha256": A.response_schema_sha256(),
        "input_provenance": {k: v for k, v in checked.items() if k != "image_sha256"},
        "image_sha256": A.image_hashes(requests, images_root),
        "projection": projection, "cost_cap_usd": guard.cap_usd,
        "candidate_set_hash": queue.get("candidate_set_hash"), "dataset_id": queue.get("dataset_id"),
        "evaluation_id": queue.get("evaluation_id"), "request_count": len(requests),
    }
    out.mkdir(parents=True, exist_ok=True)
    if a.dry_run:
        bundle = [{**r, "payload_shape": {"model": a.model, "max_tokens": a.max_output_tokens,
                                          "temperature": TEMPERATURE, "thinking": {"type": a.thinking},
                                          "content_order": ["image/png full_scene", "image/png crop", "text"]},
                   "provenance": SYNTHETIC_DRYRUN} for r in requests]
        A.write_bundle(bundle, out / "request_bundle.jsonl")
        run = {**header, "mode": "dry_run", "calls_made": 0, "actual_cost_usd": 0.0,
               "sdk_version": "미사용(드라이런)", "api_version": "미사용(드라이런)",
               "complete": False, "stop_reason": "dry_run_no_calls"}
        (out / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"드라이런: 요청 {len(requests)}건, 호출 0건, 최대 예상 ${projection['projected_max_usd']:.4f} "
              f"(상한 ${guard.cap_usd:g}) → {out}")
        return 0

    try:
        send, sdk_info = make_anthropic_sender(a.timeout_seconds)
    except ExternalCallRefused as exc:
        raise SystemExit(f"외부 호출 전제 조건에서 멈췄다: {exc}") from exc
    result = run_candidates(requests, send, guard=guard, images_root=images_root, model=a.model,
                            max_tokens=a.max_output_tokens, thinking=a.thinking, max_attempts=a.max_attempts)
    run = {**header, **sdk_info, "mode": "provider_run", "calls_made": guard.calls,
           "actual_cost_usd": round(guard.spent_usd, 6), **result}
    (out / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"호출 {guard.calls}건, 실제 비용 ${guard.spent_usd:.4f}, 중단 사유 {result['stop_reason']}, "
          f"상태 {result['counts']} → {out}")
    return 0 if result["stop_reason"] is None else 3


if __name__ == "__main__":
    raise SystemExit(main())
