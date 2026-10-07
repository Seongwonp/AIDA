"""AI 보조 판정자 도구 — 가림 거부·엄격한 응답 읽기·드라이런 기록·호출 차단."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai_adjudicator as A  # noqa: E402

PROMPT = "당신은 라벨을 검수합니다.\n답은 JSON 한 줄.\n"


def make_inputs(n=3):
    queue = {"evaluation_id": "practice1", "dataset_id": "ds", "candidate_set_hash": "h" * 8,
             "candidates": [{"canonical_candidate_id": f"C{i}", "image": "a.png",
                             "label_index": 0 if i % 2 else None,
                             "box": [10.0, 20.0, 30.0, 40.0], "class_name": "Car",
                             "verdict": None, "unique_error_id": None} for i in range(n)]}
    manifest = [{"canonical_candidate_id": f"C{i}", "image": "a.png",
                 "task": "labelled" if i % 2 else "missing", "class_name": "Car",
                 "box_xyxy_px": [10.0, 20.0, 30.0, 40.0], "image_size": [200, 100],
                 "crop_xyxy_px": [0, 0, 70, 80], "file": f"C{i}.png", "full_file": f"C{i}.full.png"}
                for i in range(n)]
    return queue, manifest


# ── 가림 ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("extra", [{"scores": {}}, {"aida_rank": 1}, {"source": "aida_candidate"},
                                   {"random_sample": True}, {"method": "aida"}, {"severity": 0.4},
                                   {"coverage_extra": True}, {"verdict": "hit"},
                                   {"unique_error_id": "a/L0"}])
def test_큐에_샌_값이_있으면_요청을_만들지_않는다(extra):
    queue, manifest = make_inputs()
    queue["candidates"][0].update(extra)
    with pytest.raises(ValueError):
        A.build_requests(queue, manifest, PROMPT)


def test_manifest에_샌_값이_있어도_거부한다():
    queue, manifest = make_inputs()
    manifest[1]["score"] = 0.9
    with pytest.raises(A.BlindingError):
        A.build_requests(queue, manifest, PROMPT)


def test_요청에는_점수_순위_판정_필드가_없다():
    queue, manifest = make_inputs()
    reqs = A.build_requests(queue, manifest, PROMPT)
    for r in reqs:
        assert "verdict" not in r and "unique_error_id" not in r
        for key in A.FORBIDDEN_KEYS:
            assert key not in r
    # 프롬프트·답 서식을 뺀 나머지 값에도 점수·순위가 없다 (답 서식의 "verdict"는 응답 형식이다)
    payload = {k: v for k, v in reqs[0].items() if k not in ("prompt", "user_message")}
    text = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("score", "rank", "severity", "suspicion", "random_sample",
                      "verdict", "source"):
        assert forbidden not in text


def test_그림이_없는_후보는_거부한다():
    queue, manifest = make_inputs()
    manifest.pop()
    with pytest.raises(ValueError):
        A.build_requests(queue, manifest, PROMPT)


def test_빈_프롬프트는_거부한다():
    queue, manifest = make_inputs()
    with pytest.raises(ValueError):
        A.build_requests(queue, manifest, "   ")


def test_요청_수는_AI_큐_크기와_같고_두_그림을_가리킨다():
    queue, manifest = make_inputs(7)
    reqs = A.build_requests(queue, manifest, PROMPT)
    assert len(reqs) == len(queue["candidates"]) == 7
    assert [r["canonical_candidate_id"] for r in reqs] == [f"C{i}" for i in range(7)]
    assert reqs[0]["images"] == {"full_scene": "C0.full.png", "crop": "C0.png"}
    assert reqs[0]["prompt"] == PROMPT
    assert "클래스: Car" in reqs[0]["user_message"]
    assert reqs[0]["session_policy"] == A.SESSION_POLICY


# ── 응답 읽기 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("verdict", ["hit", "miss", "hold"])
def test_세_판정은_모두_읽힌다(verdict):
    out = A.parse_response(json.dumps({"verdict": verdict, "reason": "상자가 넘친다"}))
    assert out == {"verdict": verdict, "rationale": "상자가 넘친다"}


def test_앞뒤_공백은_허용한다():
    assert A.parse_response('\n  {"verdict": "hold", "reason": "가려 있다"}  \n')["verdict"] == "hold"


@pytest.mark.parametrize("bad", [
    "",
    "   ",
    "hit",
    '판정: {"verdict": "hit", "reason": "x"}',              # 앞에 설명글
    '{"verdict": "hit", "reason": "x"} 이상입니다.',        # 뒤에 설명글
    '```json\n{"verdict": "hit", "reason": "x"}\n```',      # 코드펜스
    '{"verdict": "yes", "reason": "x"}',                    # 없는 판정
    '{"verdict": "hit"}',                                   # reason 없음
    '{"verdict": "hit", "reason": ""}',                     # 빈 reason
    '{"verdict": "hit", "reason": "x", "confidence": 0.9}',  # 여분의 키
    '{"verdict": "hit", "rationale": "x"}',                 # 다른 키 이름
    '[{"verdict": "hit", "reason": "x"}]',                  # 객체가 아님
    '{"verdict": "hit", "reason": 3}',                      # reason이 문자열이 아님
])
def test_형식이_다르면_거부한다(bad):
    with pytest.raises(A.ResponseFormatError):
        A.parse_response(bad)


def test_거부_응답도_형식_위반이다():
    with pytest.raises(A.ResponseFormatError):
        A.parse_response("죄송하지만 이 이미지는 판단할 수 없습니다.")


# ── 저장 payload ─────────────────────────────────────────────────────────────

def test_payload에_candidate_set_hash와_판정이_들어간다():
    rows = [{"canonical_candidate_id": "C0", "candidate_set_hash": "abc",
             "raw_text": '{"verdict": "miss", "reason": "괜찮다"}'},
            {"canonical_candidate_id": "C1", "candidate_set_hash": "abc", "verdict": "hit"}]
    payload = A.to_adjudications(rows)
    assert payload["candidate_set_hash"] == "abc"
    assert payload["adjudications"] == [{"canonical_candidate_id": "C0", "verdict": "miss"},
                                        {"canonical_candidate_id": "C1", "verdict": "hit"}]
    assert payload["format_violations"] == []


def test_형식_위반과_거부는_hold로_사상하고_기록을_남긴다():
    payload = A.to_adjudications({"candidate_set_hash": "abc", "responses": [
        {"canonical_candidate_id": "C0", "raw_text": "판단할 수 없습니다"}]})
    assert payload["adjudications"] == [{"canonical_candidate_id": "C0", "verdict": "hold"}]
    assert payload["format_violations"][0]["mapped_to"] == "hold"
    assert payload["format_violations"][0]["error"]


def test_서로_다른_묶음의_응답은_섞지_않는다():
    with pytest.raises(ValueError):
        A.to_adjudications([{"canonical_candidate_id": "C0", "candidate_set_hash": "a",
                             "verdict": "hit"},
                            {"canonical_candidate_id": "C1", "candidate_set_hash": "b",
                             "verdict": "hit"}])


def test_묶음_지문이_없으면_거부한다():
    with pytest.raises(ValueError):
        A.to_adjudications([{"canonical_candidate_id": "C0", "verdict": "hit"}])


def test_같은_후보가_두_번_나오면_거부한다():
    with pytest.raises(ValueError):
        A.to_adjudications([{"canonical_candidate_id": "C0", "candidate_set_hash": "a",
                             "verdict": "hit"}] * 2)


# ── 드라이런 ─────────────────────────────────────────────────────────────────

def write_inputs(tmp_path, n=3):
    queue, manifest = make_inputs(n)
    (tmp_path / "queue.json").write_text(json.dumps(queue), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "prompt.txt").write_text(PROMPT, encoding="utf-8")
    return queue, manifest


def test_드라이런은_묶음과_실행_기록을_쓰고_아무것도_부르지_않는다(tmp_path):
    write_inputs(tmp_path, 4)
    rc = A.main(["--dry-run", "--queue", str(tmp_path / "queue.json"),
                 "--manifest", str(tmp_path / "manifest.json"),
                 "--prompt", str(tmp_path / "prompt.txt"),
                 "--model", "<미정 모델 식별자>",
                 "--out", str(tmp_path / "bundle.jsonl"),
                 "--run-manifest", str(tmp_path / "run.json")])
    assert rc == 0
    lines = (tmp_path / "bundle.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4
    run = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    import hashlib
    assert run["model_identifier"] == "<미정 모델 식별자>"
    assert run["prompt_sha256"] == hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()
    assert run["repetitions"] == 1
    assert run["session_policy"] == "new conversation per candidate"
    assert run["temperature"] == "not exposed"          # 주지 않으면 지어내지 않는다
    assert run["request_count"] == 4 and run["call_count_if_run"] == 4
    assert run["calls_made"] == 0 and run["mode"] == "dry_run"
    assert run["image_sizes"]["full_scene"][0]["px"] == [200, 100]
    assert run["image_sizes"]["crop"][0]["px"] == [70, 80]


def test_온도와_반복을_주면_그대로_기록한다(tmp_path):
    write_inputs(tmp_path)
    A.main(["--dry-run", "--queue", str(tmp_path / "queue.json"),
            "--manifest", str(tmp_path / "manifest.json"),
            "--prompt", str(tmp_path / "prompt.txt"), "--model", "m",
            "--out", str(tmp_path / "b.jsonl"), "--run-manifest", str(tmp_path / "r.json"),
            "--temperature", "0", "--repetitions", "3"])
    run = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert run["temperature"] == "0" and run["repetitions"] == 3
    assert run["call_count_if_run"] == 9


def test_모델_식별자는_기본값이_없다(tmp_path):
    write_inputs(tmp_path)
    with pytest.raises(SystemExit):
        A.main(["--dry-run", "--queue", str(tmp_path / "queue.json"),
                "--manifest", str(tmp_path / "manifest.json"),
                "--prompt", str(tmp_path / "prompt.txt"),
                "--out", str(tmp_path / "b.jsonl"),
                "--run-manifest", str(tmp_path / "r.json")])


def test_드라이런이_아니면_돌지_않는다(tmp_path):
    write_inputs(tmp_path)
    with pytest.raises(SystemExit):
        A.main(["--queue", str(tmp_path / "queue.json"),
                "--manifest", str(tmp_path / "manifest.json"),
                "--prompt", str(tmp_path / "prompt.txt"), "--model", "m",
                "--out", str(tmp_path / "b.jsonl"), "--run-manifest", str(tmp_path / "r.json")])


# ── 호출 차단 ────────────────────────────────────────────────────────────────

def test_provider_훅은_막혀_있다():
    with pytest.raises(NotImplementedError) as exc:
        A.call_provider("anything")
    assert "비용" in str(exc.value)


def test_provider를_주면_CLI도_막힌다(tmp_path):
    write_inputs(tmp_path)
    with pytest.raises(NotImplementedError):
        A.main(["--dry-run", "--provider", "someone", "--queue", str(tmp_path / "queue.json"),
                "--manifest", str(tmp_path / "manifest.json"),
                "--prompt", str(tmp_path / "prompt.txt"), "--model", "m",
                "--out", str(tmp_path / "b.jsonl"), "--run-manifest", str(tmp_path / "r.json")])
    assert not (tmp_path / "b.jsonl").exists()


def test_모듈은_네트워크_라이브러리를_부르지_않는다():
    src = Path(A.__file__).read_text(encoding="utf-8")
    for banned in ("requests", "urllib", "httpx", "anthropic", "openai", "socket", "http.client"):
        assert f"import {banned}" not in src


# ── 비용 상한 ($10, 코드 상수) ────────────────────────────────────────────────

def guard(cap=None, inp=3.0, out=15.0):
    # 단가는 검사용 임의 값이다 — 실제 단가가 아니다.
    return A.CostGuard(inp, out, "검사용 가짜 단가", cap_usd=cap)


def test_상한_기본값은_10달러이고_올릴_수_없다():
    assert A.COST_CAP_USD == 10.0
    assert A.resolve_cost_cap(None) == 10.0
    assert A.resolve_cost_cap(2.5) == 2.5
    for bad in (10.01, 100, 0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            A.resolve_cost_cap(bad)


def test_단가에는_기본값이_없고_출처가_필요하다():
    with pytest.raises(TypeError):
        A.CostGuard()  # 단가 없이 만들 수 없다
    with pytest.raises(ValueError):
        A.CostGuard(3.0, 15.0, "")
    with pytest.raises(ValueError):
        A.CostGuard(0, 0, "출처")
    with pytest.raises(ValueError):
        A.CostGuard(-1, 15.0, "출처")


def test_비용은_토큰_곱하기_백만_토큰당_단가다():
    g = guard(inp=3.0, out=15.0)
    assert g.cost(1_000_000, 0) == pytest.approx(3.0)
    assert g.cost(2000, 100) == pytest.approx((2000 * 3 + 100 * 15) / 1e6)


def test_예상_비용이_상한을_넘으면_시작하지_않는다():
    g = guard()
    with pytest.raises(A.CostCapError):
        g.preflight(1000, 1_000_000, 0)                 # $3000 > $10
    assert g.stopped_reason == "preflight" and g.calls == 0
    ok = guard()
    assert ok.preflight(1000, 2000, 100) == pytest.approx(1000 * (2000 * 3 + 100 * 15) / 1e6)


def test_상한을_낮추면_낮춘_값으로_막는다():
    g = guard(cap=1.0)
    with pytest.raises(A.CostCapError):
        g.preflight(1000, 2000, 100)                    # $7.5 > $1


def test_실행_중_누적이_상한에_닿기_전에_멈춘다():
    g = guard(cap=1.0, inp=10.0, out=0.0)               # 호출당 입력 30k 토큰 = $0.30
    made = 0
    with pytest.raises(A.CostCapError):
        for _ in range(10):
            g.before_call(30_000, 0)
            g.record(30_000, 0)
            made += 1
    assert made == 3                                    # 0.9 + 0.3 > 1.0 이라 넷째 전에 멈춤
    assert g.spent_usd <= g.cap_usd and g.stopped_reason == "before_call"


def test_실제_사용량이_추정보다_커서_넘으면_그_뒤로_멈춘다():
    g = guard(cap=1.0, inp=10.0, out=0.0)
    g.before_call(1000, 0)
    with pytest.raises(A.CostCapError):
        g.record(200_000, 0)                            # $2 — 추정보다 훨씬 컸다
    assert g.stopped_reason == "after_call"
    with pytest.raises(A.CostCapError):
        g.before_call(1, 0)


def cli_args(tmp_path, *extra):
    return ["--dry-run", "--queue", str(tmp_path / "queue.json"),
            "--manifest", str(tmp_path / "manifest.json"),
            "--prompt", str(tmp_path / "prompt.txt"), "--model", "claude-sonnet-5",
            "--out", str(tmp_path / "b.jsonl"), "--run-manifest", str(tmp_path / "r.json"), *extra]


def test_CLI는_상한을_넘는_예상이면_묶음을_만들지_않는다(tmp_path):
    write_inputs(tmp_path, 4)
    with pytest.raises(SystemExit):
        A.main(cli_args(tmp_path, "--price-input-per-mtok", "3", "--price-output-per-mtok", "15",
                        "--price-source", "검사용", "--est-input-tokens-per-call", "1000000",
                        "--max-output-tokens", "1000"))
    assert not (tmp_path / "b.jsonl").exists()


def test_CLI는_상한을_10달러보다_올리지_못한다(tmp_path):
    write_inputs(tmp_path)
    with pytest.raises(SystemExit):
        A.main(cli_args(tmp_path, "--cost-cap", "50", "--price-input-per-mtok", "3",
                        "--price-output-per-mtok", "15", "--price-source", "검사용",
                        "--est-input-tokens-per-call", "10", "--max-output-tokens", "10"))
    assert not (tmp_path / "b.jsonl").exists()


def test_CLI는_단가를_일부만_주면_거부한다(tmp_path):
    write_inputs(tmp_path)
    with pytest.raises(SystemExit):
        A.main(cli_args(tmp_path, "--price-input-per-mtok", "3"))


def test_CLI는_상한_안이면_예상_비용과_상한을_기록한다(tmp_path):
    write_inputs(tmp_path, 4)
    assert A.main(cli_args(tmp_path, "--price-input-per-mtok", "3", "--price-output-per-mtok", "15",
                           "--price-source", "검사용", "--est-input-tokens-per-call", "2000",
                           "--max-output-tokens", "100")) == 0
    run = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    cg = run["cost_guard"]
    assert cg["cap_usd"] == 10.0 and cg["hard_max_usd"] == 10.0 and cg["spent_usd"] == 0
    assert cg["projected_usd"] == pytest.approx(4 * (2000 * 3 + 100 * 15) / 1e6)
    assert run["calls_made"] == 0


# ── 실행 기록의 지문 ─────────────────────────────────────────────────────────

def test_실행_기록에_프롬프트_스키마_그림_지문이_있다(tmp_path):
    import hashlib
    write_inputs(tmp_path, 2)
    for i in range(2):
        (tmp_path / f"C{i}.png").write_bytes(b"crop%d" % i)
        (tmp_path / f"C{i}.full.png").write_bytes(b"full%d" % i)
    A.main(cli_args(tmp_path))
    run = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert run["response_schema"] == A.RESPONSE_SCHEMA
    assert run["response_schema_sha256"] == A.response_schema_sha256()
    assert run["image_sha256"]["C1"] == {"full_scene": hashlib.sha256(b"full1").hexdigest(),
                                         "crop": hashlib.sha256(b"crop1").hexdigest()}
    assert run["image_hashes_complete"] is True
    assert run["api_version"] == "[실행 전 기입]"       # 주지 않으면 지어내지 않는다
    assert run["cost_guard"] is None


def test_그림_파일이_없으면_지문을_지어내지_않는다(tmp_path):
    write_inputs(tmp_path, 2)
    A.main(cli_args(tmp_path))
    run = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert run["image_sha256"]["C0"] == {"full_scene": None, "crop": None}
    assert run["image_hashes_complete"] is False


def test_프롬프트_지문이_사전_등록과_다르면_멈춘다(tmp_path):
    write_inputs(tmp_path)
    with pytest.raises(SystemExit):
        A.main(cli_args(tmp_path, "--expected-prompt-sha256", "0" * 64))
    assert not (tmp_path / "b.jsonl").exists()


def test_CRLF와_LF_프롬프트는_같은_지문이다(tmp_path):
    import hashlib
    write_inputs(tmp_path)
    (tmp_path / "prompt.txt").write_bytes(PROMPT.replace("\n", "\r\n").encode("utf-8"))
    A.main(cli_args(tmp_path))
    run = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert run["prompt_sha256"] == hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()


def test_응답_스키마와_parse_response가_같은_규칙이다():
    assert A.RESPONSE_SCHEMA["properties"]["verdict"]["enum"] == list(A.VERDICTS)
    assert set(A.RESPONSE_SCHEMA["required"]) == {"verdict", "reason"}
    assert A.RESPONSE_SCHEMA["additionalProperties"] is False


# ── 사전 등록에 고정한 프롬프트·스키마 지문 ───────────────────────────────────

REPO = Path(__file__).resolve().parents[2]


def _draft_blocks():
    return A.prompt_blocks_from_draft(
        (REPO / "docs" / "ai-adjudicator-prompt-draft.md").read_text(encoding="utf-8"))


def test_프롬프트_문서에서_두_블록을_꺼낸다():
    blocks = _draft_blocks()
    assert blocks["system"].startswith("당신은 자율주행")
    assert blocks["system"].endswith('"reason": "<한 문장>"}')
    assert blocks["user_template"].startswith("[전체 장면과 대상 크롭 첨부]")
    assert "```" not in blocks["system"] + blocks["user_template"]


def test_사전_등록의_프롬프트와_스키마_지문이_문서와_코드에서_다시_계산한_값과_같다():
    """프롬프트 문서나 스키마를 사전 등록 뒤에 고치면 여기서 걸린다."""
    prereg = (REPO / "docs" / "qa-preregistration.md").read_text(encoding="utf-8")
    blocks = _draft_blocks()
    assert A.sha256_text(blocks["system"]) in prereg
    assert A.sha256_text(blocks["user_template"]) in prereg
    assert A.response_schema_sha256() in prereg


def test_코드가_만드는_사용자_메시지는_문서의_틀과_같은_모양이다():
    import re
    tmpl = _draft_blocks()["user_template"].split("\n")
    _, manifest = make_inputs(2)
    for meta in manifest:
        got = A._user_message(meta).split("\n")
        assert len(got) == len(tmpl)
        for t, g in zip(tmpl, got):
            if t.startswith("답:"):
                assert g == t                           # 답 형식 줄은 글자 그대로
            else:
                pattern = "^" + re.sub(r"\\\{[^}]*\\\}", ".+", re.escape(t)) + "$"
                assert re.match(pattern, g), (t, g)


def test_프롬프트_문서에서_꺼내면_사전_등록_지문과_맞는다(tmp_path):
    write_inputs(tmp_path)
    draft = REPO / "docs" / "ai-adjudicator-prompt-draft.md"
    expected = A.sha256_text(_draft_blocks()["system"])
    args = cli_args(tmp_path, "--prompt-from-draft", "--expected-prompt-sha256", expected)
    args[args.index("--prompt") + 1] = str(draft)
    assert A.main(args) == 0
    run = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert run["prompt_sha256"] == expected
