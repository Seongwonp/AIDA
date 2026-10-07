"""AI 보조 판정자 실행 도구 — 요청 묶음을 만들고 응답을 엄격히 읽는다. **모델을 부르지 않는다.**

사전 등록 D8(`docs/qa-preregistration.md` 5절·11절)과 프롬프트 초안
(`docs/ai-adjudicator-prompt-draft.md`)에 적힌 것만 한다:

* 입력은 `GET .../queue?adjudicator=ai`의 **가림 목록**과 `render_adjudication_images.py`의
  `manifest.json`뿐이다. 점수·순위·방법·출처·표본 여부·사람 판정은 들어오면 **거부한다**
  (렌더러와 같은 라이브러리 수준 거부).
* 응답 형식은 프롬프트에 적힌 JSON 한 줄뿐이다. 그 밖(거부 포함)은 **`ai_format_error`** 상태로 남기고
  `hold`로 사상하지 않는다(사전 등록 5-4절, 2026-10-07 개정). 고치거나 다시 묻지 않고 원문을 보존한다.
* 처리하지 못한 후보(비용 상한·중단·전송 실패)는 **`ai_unjudged`** — `hold`와도 `ai_format_error`와도 다르다.
  하나라도 있으면 그 실행은 부분 실행이고 AI 일치도를 내지 않는다(`ai_agreement_report`).
* **모델 식별자·온도·프롬프트 원문·반복 수는 이 파일이 정하지 않는다.** 실행할 때 받는 값이고
  기본값이 없다. 실제 호출은 이 파일에 없다 — 별도 도구 `ai_provider.py`가 합성 입력·명시 승인 플래그·
  SDK·API 키를 모두 확인한 뒤에만 연다(지금은 합성 드라이런만 허용).
* **비용 상한 $10은 코드 상수**(`COST_CAP_USD`)다. 인자로는 낮추기만 된다. 단가는 실행 시점에 읽은
  공개 단가를 인자로 받고(기본값 없음) `CostGuard`가 시작 전·호출마다 막는다(사전 등록 5-4절).
* 실행 기록에 프롬프트·응답 스키마 SHA-256과 후보마다 두 그림 파일의 바이트 SHA-256을 남긴다.

사용법 (드라이런: 아무것도 부르지 않고 요청 묶음과 실행 기록만 쓴다):

    python ai_adjudicator.py --dry-run --queue ai_queue.json --manifest out/manifest.json \\
        --prompt prompt.txt --model "<모델 식별자>" --out bundle.jsonl --run-manifest run.json \\
        [--repetitions 1] [--temperature 0]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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
# 후보별 AI 처리 상태 (사전 등록 5-4절). hold는 판정이고, 아래 둘은 판정이 아니다.
AI_JUDGED = "ai_judged"              # 형식에 맞는 응답 — verdict는 hit/miss/hold
AI_FORMAT_ERROR = "ai_format_error"  # 응답은 받았으나 형식 위반·거부 — 원문 보존, 사상·보정 없음
AI_UNJUDGED = "ai_unjudged"          # 처리하지 못함(비용 상한·중단·전송 실패) — hold로 채우지 않음
AI_STATUSES = (AI_JUDGED, AI_FORMAT_ERROR, AI_UNJUDGED)
MODEL_ID = "claude-sonnet-5"         # 사용자 결정 2026-10-07 — 응답 모델 식별자가 다르면 멈춘다
TEMPERATURE = 0                      # 사용자 결정 2026-10-07 — 0이어도 결정성은 보장되지 않는다
SESSION_POLICY = "new conversation per candidate"
TEMPERATURE_NOT_EXPOSED = "not exposed"
NOT_SET = "[실행 전 기입]"

# 응답 형식 — 프롬프트의 JSON 한 줄. `parse_response`가 이것과 같은 규칙으로 읽는다.
RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "reason"],
    "properties": {
        "verdict": {"enum": list(VERDICTS)},
        "reason": {"type": "string", "minLength": 1},
    },
}

# ── 비용 상한 ────────────────────────────────────────────────────────────────
#
# 사용자 결정(2026-10-07): 비용 상한 $10. **코드를 고치지 않고는 올릴 수 없다** — 인자로는 낮추기만
# 된다. 단가는 이 파일이 정하지 않는다. 실행 직전 공개 단가를 읽어 인자로 넘기고 출처·읽은 시각을
# 실행 기록에 남긴다.
COST_CAP_USD = 10.0


class CostCapError(RuntimeError):
    """예상 또는 누적 비용이 상한을 넘는다 — 호출하지 않는다."""


def resolve_cost_cap(requested: float | None = None) -> float:
    """상한을 정한다. 주지 않으면 $10, 주면 0 초과 $10 이하만."""
    if requested is None:
        return COST_CAP_USD
    value = float(requested)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"비용 상한은 0보다 커야 한다: {requested!r}")
    if value > COST_CAP_USD:
        raise ValueError(f"비용 상한은 ${COST_CAP_USD:g}를 넘길 수 없다(코드 상수): {requested!r}")
    return value


def _nonneg(name: str, value: Any) -> float:
    v = float(value)
    if not math.isfinite(v) or v < 0:
        raise ValueError(f"{name}은 0 이상의 유한한 수여야 한다: {value!r}")
    return v


class CostGuard:
    """호출 전·중에 비용을 막는다. **기본 단가가 없다** — 단가를 받지 않으면 만들어지지 않는다.

    * `preflight(calls, 입력 토큰, 출력 토큰)` — 실행 시작 전 전체 예상 비용이 상한을 넘으면 거부.
      출력 토큰 추정에는 요청의 `max_tokens`(출력 상한)를 쓴다 — 짧게 답하리라는 가정을 하지 않는다.
    * `before_call(입력 토큰, 출력 토큰)` — 호출마다 **누적 + 이번 호출 최대치**가 상한을 넘으면 멈춤.
    * `record(입력 토큰, 출력 토큰)` — 응답의 실제 사용량을 더한다. 넘었으면 다음 호출 전에 멈춘다.
    """

    def __init__(self, input_usd_per_mtok: float, output_usd_per_mtok: float,
                 price_source: str, cap_usd: float | None = None):
        if not str(price_source or "").strip():
            raise ValueError("단가 출처(문서 주소·읽은 시각)를 적는다 — 기억한 단가를 쓰지 않는다")
        self.input_usd_per_mtok = _nonneg("입력 단가", input_usd_per_mtok)
        self.output_usd_per_mtok = _nonneg("출력 단가", output_usd_per_mtok)
        if self.input_usd_per_mtok == 0 and self.output_usd_per_mtok == 0:
            raise ValueError("단가가 둘 다 0이다 — 상한이 아무것도 막지 못한다")
        self.price_source = str(price_source)
        self.cap_usd = resolve_cost_cap(cap_usd)
        self.spent_usd = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self.stopped_reason: str | None = None

    def cost(self, input_tokens: float, output_tokens: float) -> float:
        return (_nonneg("입력 토큰", input_tokens) * self.input_usd_per_mtok
                + _nonneg("출력 토큰", output_tokens) * self.output_usd_per_mtok) / 1_000_000

    def preflight(self, calls: int, input_tokens_per_call: float,
                  max_output_tokens_per_call: float) -> float:
        if int(calls) < 0:
            raise ValueError(f"호출 수가 음수다: {calls}")
        projected = int(calls) * self.cost(input_tokens_per_call, max_output_tokens_per_call)
        if projected > self.cap_usd:
            self.stopped_reason = "preflight"
            raise CostCapError(f"예상 비용 ${projected:.4f}가 상한 ${self.cap_usd:g}를 넘는다 — 시작하지 않는다")
        return projected

    def before_call(self, input_tokens: float, max_output_tokens: float) -> None:
        worst = self.spent_usd + self.cost(input_tokens, max_output_tokens)
        if worst > self.cap_usd:
            self.stopped_reason = "before_call"
            raise CostCapError(f"누적 ${self.spent_usd:.4f} + 이번 호출 최대 → ${worst:.4f}, "
                               f"상한 ${self.cap_usd:g} — 멈춘다")

    def record(self, input_tokens: int, output_tokens: int) -> None:
        self.spent_usd += self.cost(input_tokens, output_tokens)
        self.input_tokens += int(input_tokens)
        self.output_tokens += int(output_tokens)
        self.calls += 1
        if self.spent_usd > self.cap_usd:
            self.stopped_reason = "after_call"
            raise CostCapError(f"누적 비용 ${self.spent_usd:.4f}가 상한 ${self.cap_usd:g}를 넘었다 — 멈춘다")

    def as_dict(self) -> dict:
        return {"cap_usd": self.cap_usd, "hard_max_usd": COST_CAP_USD,
                "input_usd_per_mtok": self.input_usd_per_mtok,
                "output_usd_per_mtok": self.output_usd_per_mtok,
                "price_source": self.price_source,
                "spent_usd": round(self.spent_usd, 6), "calls_recorded": self.calls,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "stopped_reason": self.stopped_reason}


# ── 프롬프트·스키마 지문 ─────────────────────────────────────────────────────

PROMPT_DRAFT_HEADINGS = {"system": "## 시스템 프롬프트", "user_template": "## 사용자 메시지"}


def normalise_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def prompt_blocks_from_draft(md_text: str) -> dict[str, str]:
    """`docs/ai-adjudicator-prompt-draft.md`에서 시스템 프롬프트와 사용자 메시지 틀을 꺼낸다.

    **지문을 내는 바이트의 정의:** 해당 제목(`## 시스템 프롬프트…`, `## 사용자 메시지…`) 아래 첫 코드
    펜스(```로 시작하는 줄)와 닫는 펜스 **사이의 줄들**을 LF(`\\n`)로 이어 붙인 문자열(펜스 줄 제외,
    맨 끝 줄바꿈 없음, 각 줄 끝 공백은 그대로), 그 UTF-8 바이트. 작업 폴더의 CRLF는 LF로 바꾼 뒤 센다.
    """
    lines = normalise_newlines(md_text).split("\n")
    out = {}
    for key, heading in PROMPT_DRAFT_HEADINGS.items():
        starts = [i for i, line in enumerate(lines) if line.startswith(heading)]
        if len(starts) != 1:
            raise ValueError(f"프롬프트 문서에서 제목을 하나만 찾아야 한다: {heading} ({len(starts)}개)")
        i = starts[0] + 1
        while i < len(lines) and not lines[i].startswith("```"):
            if lines[i].startswith("## "):
                raise ValueError(f"{heading} 아래에 코드 블록이 없다")
            i += 1
        j = i + 1
        while j < len(lines) and not lines[j].startswith("```"):
            j += 1
        if i >= len(lines) or j >= len(lines):
            raise ValueError(f"{heading}의 코드 블록이 닫히지 않았다")
        block = "\n".join(lines[i + 1:j])
        if not block.strip():
            raise ValueError(f"{heading}의 코드 블록이 비어 있다")
        out[key] = block
    return out


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def response_schema_sha256() -> str:
    """스키마 지문 — 키 정렬·공백 없는 JSON(`sort_keys=True, separators=(",", ":")`)의 UTF-8 바이트."""
    return sha256_text(json.dumps(RESPONSE_SCHEMA, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=False))


def image_hashes(requests: list[dict], images_root: Path | None) -> dict[str, dict]:
    """후보마다 실제로 보낼 두 그림 파일의 바이트 SHA-256. 파일이 없으면 None(지어내지 않는다)."""
    out = {}
    for r in requests:
        row = {}
        for key in ("full_scene", "crop"):
            path = images_root / r["images"][key] if images_root is not None else None
            row[key] = (hashlib.sha256(path.read_bytes()).hexdigest()
                        if path is not None and path.is_file() else None)
        out[r["canonical_candidate_id"]] = row
    return out


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

    돌려주는 것은 `{"verdict": hit|miss|hold, "rationale": str}`. 형식 위반을 고치거나 다른 판정으로
    사상하지 않는다 — 부르는 쪽이 `ai_format_error`로 남기고 원문을 보존한다.
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
    기록마다 `canonical_candidate_id`와, `raw_text`(원문) 또는 이미 읽어 둔 `verdict`가 있어야 한다.
    `status`가 `ai_unjudged`인 기록은 판정이 없다.

    * 형식에 맞는 응답만 `adjudications`(hit/miss/hold)에 들어간다.
    * 형식 위반·거부는 `format_errors`(상태 `ai_format_error`, 오류 사유)에만 — **`hold`로 사상하지 않는다**
      (사전 등록 5-4절, 2026-10-07 개정. 이전 판은 `hold`로 사상했다).
    * 처리하지 못한 후보는 `unjudged`(상태 `ai_unjudged`)에만.
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

    adjudications, format_errors, unjudged, seen = [], [], [], set()
    for r in rows:
        cid = r.get("canonical_candidate_id")
        if not cid:
            raise ValueError("canonical_candidate_id가 없는 응답이 있다")
        if cid in seen:
            raise ValueError(f"같은 후보가 두 번 나왔다: {cid}")
        seen.add(cid)
        status = r.get("status")
        if status is not None and status not in AI_STATUSES:
            raise ValueError(f"알 수 없는 AI 처리 상태: {status!r}")
        if status == AI_UNJUDGED:
            unjudged.append({"canonical_candidate_id": cid, "status": AI_UNJUDGED,
                             "reason": r.get("reason")})
            continue
        if status != AI_FORMAT_ERROR and r.get("verdict") in VERDICTS:
            adjudications.append({"canonical_candidate_id": cid, "verdict": r["verdict"]})
            continue
        try:
            verdict = parse_response(r.get("raw_text", ""))["verdict"]
        except ResponseFormatError as exc:
            format_errors.append({"canonical_candidate_id": cid, "status": AI_FORMAT_ERROR,
                                  "error": str(exc)})
            continue
        if status == AI_FORMAT_ERROR:
            raise ValueError(f"{cid}: 상태는 ai_format_error인데 원문이 형식에 맞는다 — 기록이 어긋났다")
        adjudications.append({"canonical_candidate_id": cid, "verdict": verdict})
    return {"candidate_set_hash": hashes.pop(),
            "adjudications": adjudications,
            "format_errors": format_errors,
            "unjudged": unjudged}


# ── 3-1. AI 일치도 (부분 실행 거부) ──────────────────────────────────────────

class PartialRunError(ValueError):
    """AI 실행이 끝나지 않았다(ai_unjudged가 있거나 중단됐다) — 전체 일치도를 내지 않는다."""


def _load_backend_agreement():
    """일치도 계산은 백엔드와 같은 함수를 쓴다(`backend/app/agreement.py`, 표준 라이브러리만 쓴다)."""
    import importlib.util
    path = Path(__file__).resolve().parent.parent / "backend" / "app" / "agreement.py"
    spec = importlib.util.spec_from_file_location("aida_backend_agreement", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"일치도 모듈을 읽지 못했다: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ai_agreement_report(ai_run: dict, sample_ids: list[str], human_verdicts: dict,
                        registry: dict | None = None) -> dict:
    """보조 표본에서 사람–AI 일치도. **완결된 실행에서만** 낸다.

    * `ai_run`은 `ai_provider.py`의 실행 기록(`candidates`: 후보별 `status`·`verdict`). 출처가 `synthetic_dryrun`이거나
      출처 등록부의 연습·손상 자료면 거부한다.
    * 표본의 모든 후보가 처리돼야 한다 — `ai_unjudged`가 하나라도 있거나, 표본 후보가 실행 기록에 없거나, 실행이
      중단 사유와 함께 끝났으면 `PartialRunError`. 부분 실행으로 전체 일치도를 내지 않는다.
    * `ai_format_error` 후보는 AI 판정이 없는 것으로 넣고(hold로 바꾸지 않는다) 건수를 따로 적는다.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from evaluation.provenance import assert_official_input
    assert_official_input(ai_run, "AI 실행 기록", registry=registry)
    if not sample_ids:
        raise PartialRunError("보조 표본이 비어 있다")
    rows = {r["canonical_candidate_id"]: r for r in ai_run.get("candidates") or []}
    missing = sorted(set(sample_ids) - set(rows))
    unjudged = sorted(cid for cid in sample_ids if rows.get(cid, {}).get("status") == AI_UNJUDGED)
    if ai_run.get("stop_reason") or ai_run.get("complete") is not True or missing or unjudged:
        raise PartialRunError(
            f"부분 실행이다 — 전체 AI 일치도를 내지 않는다 (중단 사유 {ai_run.get('stop_reason')!r}, "
            f"complete={ai_run.get('complete')!r}, 기록 없음 {len(missing)}건, ai_unjudged {len(unjudged)}건)")
    for cid in sample_ids:
        status = rows[cid].get("status")
        if status not in (AI_JUDGED, AI_FORMAT_ERROR):
            raise PartialRunError(f"{cid}: 알 수 없는 상태 {status!r}")
    ai = {cid: (rows[cid].get("verdict") if rows[cid]["status"] == AI_JUDGED else None) for cid in sample_ids}
    report = _load_backend_agreement().agreement_report(list(sample_ids), human_verdicts, ai)
    report["ai_format_error"] = sum(1 for cid in sample_ids if rows[cid]["status"] == AI_FORMAT_ERROR)
    report["ai_unjudged"] = 0
    report["ai_run_complete"] = True
    return report


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


RETRY_POLICY = ("응답을 받지 못한 네트워크·서버 오류(시간 초과·연결 실패·429·529 과부하·5xx)만 다시 보낸다. "
                "응답을 받았으면(형식 위반·거부 포함) 다시 묻지도 고치지도 않고 그 원문을 ai_format_error로 둔다. "
                "최대 시도 수를 다 써도 응답이 없으면 그 후보는 ai_unjudged — 반복 1회")


def build_run_manifest(requests: list[dict], prompt_text: str, model: str,
                       repetitions: int, temperature: Any = None,
                       images_root: Path | None = None,
                       queue_json: dict | None = None,
                       cost_guard: "CostGuard | None" = None,
                       api_version: str | None = None,
                       max_attempts: int | None = None,
                       timeout_seconds: float | None = None) -> dict:
    """실행 기록. 사전 등록 11절이 요구하는 칸을 채우되 **값을 지어내지 않는다.**"""
    if not model or not str(model).strip():
        raise ValueError("모델 식별자는 필수다 — 기본값이 없다")
    if repetitions < 1:
        raise ValueError("반복 수는 1 이상이다")
    hashes = image_hashes(requests, images_root)
    return {
        "tool": "experiment/ai_adjudicator.py",
        "mode": "dry_run",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_identifier": str(model),
        "prompt_sha256": sha256_text(normalise_newlines(prompt_text)),
        "prompt_bytes": len(normalise_newlines(prompt_text).encode("utf-8")),
        "prompt_hash_definition": "UTF-8 bytes of the prompt text after CRLF/CR -> LF",
        "response_schema": RESPONSE_SCHEMA,
        "response_schema_sha256": response_schema_sha256(),
        "image_sha256": hashes,
        "image_hashes_complete": all(v is not None for row in hashes.values() for v in row.values()),
        "api_version": api_version or NOT_SET,
        "retry_policy": RETRY_POLICY,
        "max_attempts": max_attempts if max_attempts is not None else NOT_SET,
        "timeout_seconds": timeout_seconds if timeout_seconds is not None else NOT_SET,
        "cost_guard": cost_guard.as_dict() if cost_guard is not None else None,
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
    """일부러 막아 둔 자리. 이 도구에서는 실수로라도 호출이 나가지 않게 한다."""
    raise NotImplementedError(
        "이 도구는 AI 판정자를 부르지 않는다. 유료 모델 호출이므로 "
        "**사용자가 비용 상한과 외부 전송을 먼저 승인**해야 한다. 호출 경로는 ai_provider.py에만 있고 "
        "합성 입력·--approve-external-call·SDK·API 키를 모두 확인한 뒤에만 연다.")


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
    ap.add_argument("--prompt-from-draft", action="store_true",
                    help="--prompt가 docs/ai-adjudicator-prompt-draft.md면 그 '시스템 프롬프트' 블록을 꺼내 쓴다")
    ap.add_argument("--expected-prompt-sha256", default=None,
                    help="사전 등록에 고정한 프롬프트 지문. 다르면 묶음을 만들지 않는다")
    ap.add_argument("--cost-cap", type=float, default=None,
                    help=f"비용 상한(USD). 주지 않으면 {COST_CAP_USD:g}, 그보다 크게는 줄 수 없다")
    ap.add_argument("--price-input-per-mtok", type=float, default=None,
                    help="실행 시점에 읽은 공개 입력 단가(USD/100만 토큰). 기본값 없음")
    ap.add_argument("--price-output-per-mtok", type=float, default=None,
                    help="실행 시점에 읽은 공개 출력 단가(USD/100만 토큰). 기본값 없음")
    ap.add_argument("--price-source", default=None, help="단가 문서 주소와 읽은 시각")
    ap.add_argument("--est-input-tokens-per-call", type=float, default=None,
                    help="호출당 입력 토큰 추정(그림 2장 + 텍스트)")
    ap.add_argument("--max-output-tokens", type=float, default=None,
                    help="요청의 출력 상한(max_tokens) — 예상 비용은 이 값으로 잡는다")
    ap.add_argument("--api-version", default=None, help="실제 쓴 API 버전 문자열·SDK 버전")
    ap.add_argument("--max-attempts", type=int, default=None)
    ap.add_argument("--timeout-seconds", type=float, default=None)
    a = ap.parse_args(argv)

    if a.provider:
        call_provider(a.provider)               # 항상 NotImplementedError
    if not a.dry_run:
        raise SystemExit("--dry-run만 지원한다. 실제 호출은 비용 승인 뒤에 연다.")

    queue = json.loads(Path(a.queue).read_text(encoding="utf-8"))
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    prompt = Path(a.prompt).read_text(encoding="utf-8")
    if a.prompt_from_draft:
        prompt = prompt_blocks_from_draft(prompt)["system"]
    if a.expected_prompt_sha256 and sha256_text(normalise_newlines(prompt)) != a.expected_prompt_sha256:
        raise SystemExit("프롬프트 지문이 사전 등록 값과 다르다 — 묶음을 만들지 않는다")
    requests = build_requests(queue, manifest, prompt)

    guard = None
    price_args = (a.price_input_per_mtok, a.price_output_per_mtok)
    if any(v is not None for v in price_args) or a.cost_cap is not None:
        if None in price_args or a.est_input_tokens_per_call is None or a.max_output_tokens is None:
            raise SystemExit("비용 점검에는 입력·출력 단가, 단가 출처, 호출당 입력 토큰, 출력 상한이 모두 필요하다")
        try:
            guard = CostGuard(a.price_input_per_mtok, a.price_output_per_mtok,
                              a.price_source, cap_usd=a.cost_cap)
            guard.preflight(len(requests) * a.repetitions, a.est_input_tokens_per_call,
                            a.max_output_tokens)
        except (CostCapError, ValueError) as exc:
            raise SystemExit(f"비용 점검에서 멈췄다: {exc}") from exc

    n = write_bundle(requests, Path(a.out))
    run = build_run_manifest(requests, prompt, a.model, a.repetitions, a.temperature,
                             images_root=Path(a.manifest).parent, queue_json=queue,
                             cost_guard=guard, api_version=a.api_version,
                             max_attempts=a.max_attempts, timeout_seconds=a.timeout_seconds)
    if guard is not None:
        run["cost_guard"]["projected_usd"] = round(
            len(requests) * a.repetitions
            * guard.cost(a.est_input_tokens_per_call, a.max_output_tokens), 6)
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
