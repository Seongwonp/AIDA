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
