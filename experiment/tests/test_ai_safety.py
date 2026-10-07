"""AI 판정·val 안전 관문 (사용자 결정 2026-10-07).

(a) val 잠금 — 커밋된 사전 등록에 빈칸 표시가 남아 있으면 val 표집을 거부한다.
(b) 외부 전송 입력 — nuImages 경로·파일 이름·업로드 데이터셋 그림 SHA·합성 표시 없음을 거부한다.
(c) 응답 모델 식별자가 다르면 즉시 멈춘다.
(d) 비용 상한에 닿으면 남은 후보는 ai_unjudged이고 실행이 멈춘다.
(e) 부분 실행으로 AI 일치도를 내지 않는다.
(f) 합성 드라이런 산출물(synthetic_dryrun)은 분석 경로가 거부한다.
(g) practice1(출처 손상 연습 자료)은 공식 평가 입력으로 고를 수 없다.

네트워크를 쓰지 않는다. 가짜 응답만 쓴다 — 실제 모델 응답이 아니다.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai_adjudicator as A  # noqa: E402
import ai_provider as P  # noqa: E402
import analyze_qa  # noqa: E402
import make_synthetic_ai_dryrun as G  # noqa: E402
import nuimages_eval_sample as V  # noqa: E402
from evaluation import provenance as PV  # noqa: E402
from evaluation.schema import ValidationError  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PREREG = "docs/qa-preregistration.md"
PRACTICE_IMAGES = REPO / "backend" / "app" / "data" / "uploads" / "006e49d2cbc9" / "images"
FAKE_PRICE = dict(input_usd_per_mtok=2.0, output_usd_per_mtok=10.0, price_source="검사용 가짜 단가")


# ── 공용: 합성 입력 (모듈 단위로 한 번 만든다) ───────────────────────────────

@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    root = tmp_path_factory.mktemp("synth") / "s"
    G.generate(root, scenes=3, seed=7, candidates=6)
    queue = json.loads((root / "queue.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "rendered" / "manifest.json").read_text(encoding="utf-8"))
    prompt = "검사용 프롬프트. JSON 한 줄."
    requests = A.build_requests(queue, manifest, prompt)
    return {"root": root, "images": root / "rendered", "queue": queue, "requests": requests}


def ok_response(verdict="miss", model=P.MODEL_ID, inp=3000, out=20):
    return {"model": model, "stop_reason": "end_turn",
            "content": [{"type": "text", "text": json.dumps({"verdict": verdict, "reason": "검사"})}],
            "usage": {"input_tokens": inp, "output_tokens": out}}


def run(synth, send, cap=1.0, max_attempts=2):
    guard = A.CostGuard(cap_usd=cap, **FAKE_PRICE)
    return P.run_candidates(synth["requests"], send, guard=guard, images_root=synth["images"],
                            model=P.MODEL_ID, max_tokens=256, thinking="disabled",
                            max_attempts=max_attempts, sleep=lambda s: None)


# ── (a) val 잠금 ─────────────────────────────────────────────────────────────

def test_a_지금_커밋된_사전_등록으로는_val을_열지_않는다():
    """확정 커밋 전까지 이 검사는 거부를 기대한다. 확정 커밋에서 빈칸이 0이 되면 이 검사를 함께 고친다."""
    with pytest.raises(ValueError):
        V.check_preregistration(REPO, PREREG)
    committed = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{PREREG}"],
                               capture_output=True).stdout.decode("utf-8")
    left = V.unfilled_markers(committed)
    assert left, "커밋된 사전 등록에 빈칸 표시가 없다 — 확정 커밋이면 이 검사를 갱신한다"


def test_a_작업_폴더의_사전_등록에도_빈칸이_남아_있다():
    text = (REPO / PREREG).read_text(encoding="utf-8")
    assert V.unfilled_markers(text)


# ── (b) 외부 전송 입력 관문 ──────────────────────────────────────────────────

def test_b_합성_입력은_관문을_통과하고_다시_만들어도_바이트가_같다(synth):
    checked = P.check_inputs(synth["requests"], synth["images"], synth["queue"],
                             deny={"sha256": set(), "sources": []})
    assert checked["provenance"] == PV.SYNTHETIC_DRYRUN and checked["reproducible_verified"]


@pytest.mark.parametrize("path", [
    "D:/AIDA-eval/nuimages/all/samples/x.png", "C:/data/nuImages/v1.0-val/a.png",
    "backend/app/data/uploads/006e49d2cbc9/images/a.png", "x/v1.0-train/a.png",
    "renders/n005-2018-07-10-16-39-03+0800__CAM_BACK__1531211947687642.png",
])
def test_b_nuImages_위치나_이름이면_걸린다(path):
    assert PV.nuimages_path_hits(path)


def test_b_합성_표시가_없으면_거부한다(synth, tmp_path):
    dst = tmp_path / "copy"
    shutil.copytree(synth["images"], dst)
    (dst / PV.PROVENANCE_FILE).unlink()
    with pytest.raises(PV.ProvenanceError, match="합성 표시"):
        P.check_inputs(synth["requests"], dst, synth["queue"], deny={"sha256": set(), "sources": []},
                       verify_reproducible=False)


def test_b_nuImages_경로_아래의_입력은_거부한다(synth, tmp_path):
    dst = tmp_path / "nuimages_render"
    shutil.copytree(synth["images"], dst)
    with pytest.raises(PV.ProvenanceError, match="nuImages"):
        P.check_inputs(synth["requests"], dst, synth["queue"], deny={"sha256": set(), "sources": []},
                       verify_reproducible=False)


def test_b_그림을_바꿔_끼우면_SHA가_달라_거부한다(synth, tmp_path):
    dst = tmp_path / "swap"
    shutil.copytree(synth["images"], dst)
    name = synth["requests"][0]["images"]["crop"]
    (dst / name).write_bytes(b"not the synthetic image")
    with pytest.raises(PV.ProvenanceError, match="SHA-256"):
        P.check_inputs(synth["requests"], dst, synth["queue"], deny={"sha256": set(), "sources": []},
                       verify_reproducible=False)


def test_b_거부_목록의_SHA와_같으면_거부한다(synth):
    name = synth["requests"][0]["images"]["full_scene"]
    sha = PV.sha256_file(synth["images"] / name)
    with pytest.raises(PV.ProvenanceError, match="거부 목록"):
        P.check_inputs(synth["requests"], synth["images"], synth["queue"],
                       deny={"sha256": {sha}, "sources": []}, verify_reproducible=False)


def test_b_합성_표시만_붙인_다른_그림은_재생성_대조로_거부한다(synth, tmp_path):
    """provenance.json의 SHA까지 맞춰 고쳐도, 같은 씨앗으로 다시 만든 바이트와 다르면 막는다."""
    dst = tmp_path / "forged"
    shutil.copytree(synth["images"], dst)
    name = synth["requests"][0]["images"]["crop"]
    (dst / name).write_bytes(b"forged")
    meta = json.loads((dst / PV.PROVENANCE_FILE).read_text(encoding="utf-8"))
    meta["files"][name] = PV.sha256_file(dst / name)
    (dst / PV.PROVENANCE_FILE).write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(PV.ProvenanceError, match="다시 만들"):
        P.check_inputs(synth["requests"], dst, synth["queue"], deny={"sha256": set(), "sources": []})


def test_b_가림_목록의_출처가_합성이_아니면_거부한다(synth):
    queue = {**synth["queue"], "provenance": None}
    with pytest.raises(PV.ProvenanceError):
        P.check_inputs(synth["requests"], synth["images"], queue, deny={"sha256": set(), "sources": []})


def test_b_후보가_20건을_넘으면_거부한다(synth):
    many = (synth["requests"] * 4)[:21]
    with pytest.raises(P.ExternalCallRefused):
        P.check_inputs(many, synth["images"], synth["queue"], deny={"sha256": set(), "sources": []})


@pytest.mark.skipif(not PRACTICE_IMAGES.is_dir(), reason="연습 데이터셋이 이 기계에 없다(데스크탑 전용)")
def test_b_업로드된_연습_데이터셋_원본은_거부_목록에_들어간다():
    deny = PV.build_image_deny_list()
    first = sorted(p for p in PRACTICE_IMAGES.iterdir() if p.suffix.lower() in PV.IMAGE_SUFFIXES)[0]
    assert PV.sha256_file(first) in deny["sha256"]
    assert deny["sources"][0]["present"] and deny["sources"][0]["images"] > 0


def test_b_합성_생성기는_nuImages_위치에_쓰지_않는다(tmp_path):
    with pytest.raises(ValueError, match="nuImages"):
        G.generate(tmp_path / "nuimages" / "x", scenes=1, candidates=1)


def test_b_합성_생성기는_20장_20건을_넘지_않는다(tmp_path):
    with pytest.raises(ValueError):
        G.generate(tmp_path / "a", scenes=21)
    with pytest.raises(ValueError):
        G.generate(tmp_path / "b", scenes=1, candidates=21)


def test_b_합성_그림은_1600x900_전체와_크롭_한_쌍이다(synth):
    from PIL import Image
    r = synth["requests"][0]
    with Image.open(synth["images"] / r["images"]["full_scene"]) as im:
        assert im.size == (1600, 900) and im.format == "PNG"
    with Image.open(synth["images"] / r["images"]["crop"]) as im:
        assert im.format == "PNG" and im.size[0] < 1600


def test_b_SDK나_키가_없으면_부르지_않는다(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(P.ExternalCallRefused, match="ANTHROPIC_API_KEY"):
        P.make_anthropic_sender(60)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-not-a-key")
    real = P.importlib.import_module

    def no_sdk(name, *a, **k):
        if name == "anthropic":
            raise ImportError("no sdk")
        return real(name, *a, **k)
    monkeypatch.setattr(P.importlib, "import_module", no_sdk)
    with pytest.raises(P.ExternalCallRefused, match="SDK"):
        P.make_anthropic_sender(60)


def test_b_CLI는_승인_플래그나_드라이런_없이는_돌지_않는다(synth, tmp_path):
    args = ["--queue", str(synth["root"] / "queue.json"),
            "--manifest", str(synth["images"] / "manifest.json"),
            "--prompt-draft", str(REPO / "docs" / "ai-adjudicator-prompt-draft.md"),
            "--expected-prompt-sha256", "0" * 64, "--model", P.MODEL_ID, "--max-output-tokens", "256",
            "--thinking", "disabled", "--timeout-seconds", "60", "--max-attempts", "3",
            "--price-input-per-mtok", "2", "--price-output-per-mtok", "10", "--price-source", "검사용",
            "--out-dir", str(tmp_path / "o")]
    with pytest.raises(SystemExit):
        P.main(args)                                       # 모드 없음
    with pytest.raises(SystemExit):
        P.main(args + ["--dry-run", "--cost-cap", "2"])    # $1 초과 상한
    bad_model = list(args)
    bad_model[bad_model.index("--model") + 1] = "claude-sonnet-5-latest"
    with pytest.raises(SystemExit):
        P.main(bad_model + ["--dry-run"])


def test_b_최대_예상_비용이_1달러를_넘을_수_있으면_시작하지_않는다(synth, tmp_path):
    draft = REPO / "docs" / "ai-adjudicator-prompt-draft.md"
    sha = A.sha256_text(A.prompt_blocks_from_draft(draft.read_text(encoding="utf-8"))["system"])
    args = ["--dry-run", "--queue", str(synth["root"] / "queue.json"),
            "--manifest", str(synth["images"] / "manifest.json"), "--prompt-draft", str(draft),
            "--expected-prompt-sha256", sha, "--model", P.MODEL_ID, "--max-output-tokens", "100000",
            "--thinking", "disabled", "--timeout-seconds", "60", "--max-attempts", "3",
            "--price-input-per-mtok", "2", "--price-output-per-mtok", "10", "--price-source", "검사용",
            "--out-dir", str(tmp_path / "o")]
    with pytest.raises(SystemExit, match="최대 예상 비용"):
        P.main(args)
    args[args.index("--max-output-tokens") + 1] = "256"
    assert P.main(args) == 0
    run_rec = json.loads((tmp_path / "o" / "run.json").read_text(encoding="utf-8"))
    assert run_rec["calls_made"] == 0 and run_rec["provenance"] == PV.SYNTHETIC_DRYRUN
    assert run_rec["temperature"] == 0 and "보장" in run_rec["temperature_note"]
    assert run_rec["projection"]["projected_max_usd"] <= 1.0


# ── (c) 모델 불일치 ──────────────────────────────────────────────────────────

def test_c_응답_모델이_다르면_즉시_멈추고_남은_후보는_ai_unjudged(synth):
    calls = []

    def send(payload):
        calls.append(payload["model"])
        return ok_response(model="claude-sonnet-5-5" if len(calls) == 2 else P.MODEL_ID)
    res = run(synth, send)
    assert len(calls) == 2 and res["stop_reason"] == "model_mismatch" and res["complete"] is False
    statuses = [r["status"] for r in res["candidates"]]
    assert statuses[0] == A.AI_JUDGED and all(s == A.AI_UNJUDGED for s in statuses[1:])
    assert len(statuses) == len(synth["requests"])


def test_c_요청은_정확한_모델과_온도_0을_쓰고_후보마다_새_요청이다(synth):
    payloads = []
    res = run(synth, lambda p: payloads.append(p) or ok_response())
    assert res["complete"] and len(payloads) == len(synth["requests"])
    for p in payloads:
        assert p["model"] == "claude-sonnet-5" and p["temperature"] == 0
        assert len(p["messages"]) == 1                     # 이전 대화를 붙이지 않는다
        kinds = [b["type"] for b in p["messages"][0]["content"]]
        assert kinds == ["image", "image", "text"]


def test_c_다른_모델_식별자로는_실행을_시작하지_않는다(synth):
    guard = A.CostGuard(cap_usd=1.0, **FAKE_PRICE)
    with pytest.raises(P.ExternalCallRefused):
        P.run_candidates(synth["requests"], lambda p: ok_response(), guard=guard, images_root=synth["images"],
                         model="claude-sonnet-5-5", max_tokens=10, thinking="disabled", max_attempts=1)


# ── (d) 비용 상한 ────────────────────────────────────────────────────────────

def test_d_상한에_닿으면_남은_후보는_ai_unjudged이고_실행이_멈춘다(synth):
    calls = []
    # 한 호출 최대 ≈ $0.011(상한 추정), 첫 호출 실제 $0.006 → 상한 $0.015면 둘째 호출 전에 멈춘다
    res = run(synth, lambda p: calls.append(1) or ok_response(inp=3000), cap=0.015)
    assert res["stop_reason"] == "cost_cap" and res["complete"] is False
    assert len(calls) == 1
    statuses = [r["status"] for r in res["candidates"]]
    assert statuses[0] == A.AI_JUDGED
    assert statuses[1:] and all(s == A.AI_UNJUDGED for s in statuses[1:])
    assert all("hold" != r.get("verdict") for r in res["candidates"][1:])
    assert all(r.get("verdict") is None for r in res["candidates"][1:])


def test_d_실제_사용량이_상한을_넘기면_그_후보까지만_기록하고_멈춘다(synth):
    res = run(synth, lambda p: ok_response(inp=10_000_000), cap=1.0)
    assert res["stop_reason"] == "cost_cap"
    assert res["candidates"][0]["status"] == A.AI_JUDGED
    assert all(r["status"] == A.AI_UNJUDGED for r in res["candidates"][1:])


def test_d_형식_오류는_hold가_아니라_ai_format_error이고_다시_묻지_않는다(synth):
    calls = []

    def send(p):
        calls.append(1)
        return {**ok_response(), "content": [{"type": "text", "text": "판단할 수 없습니다"}]}
    res = run(synth, send)
    assert len(calls) == len(synth["requests"])           # 후보당 한 번 — 재질문 없음
    assert {r["status"] for r in res["candidates"]} == {A.AI_FORMAT_ERROR}
    assert all("verdict" not in r and r["raw_text"] == "판단할 수 없습니다" for r in res["candidates"])
    assert res["complete"] is True


def test_d_네트워크_서버_오류만_재시도하고_다_쓰면_ai_unjudged(synth):
    attempts = []

    def send(p):
        attempts.append(1)
        raise P.TransientProviderError("529 overloaded")
    res = run(synth, send, max_attempts=3)
    assert len(attempts) == 3 * len(synth["requests"])
    assert all(r["status"] == A.AI_UNJUDGED and r["attempts"] == 3 for r in res["candidates"])
    assert res["complete"] is False


def test_d_재시도하지_않는_오류는_실행을_멈춘다(synth):
    calls = []

    def send(p):
        calls.append(1)
        raise P.FatalProviderError("400 invalid_request_error: temperature")
    res = run(synth, send, max_attempts=3)
    assert len(calls) == 1 and res["stop_reason"] == "fatal_error"
    assert all(r["status"] == A.AI_UNJUDGED for r in res["candidates"])


# ── (e) 부분 실행 일치도 거부 ────────────────────────────────────────────────

def _official_run(records, complete=True, stop_reason=None):
    return {"provenance": "official_ai_run", "dataset_id": "val_ds", "evaluation_id": "qa1",
            "candidates": records, "complete": complete, "stop_reason": stop_reason}


def test_e_ai_unjudged가_있으면_일치도를_내지_않는다():
    recs = [{"canonical_candidate_id": "a", "status": A.AI_JUDGED, "verdict": "hit"},
            {"canonical_candidate_id": "b", "status": A.AI_UNJUDGED}]
    with pytest.raises(A.PartialRunError):
        A.ai_agreement_report(_official_run(recs, complete=False, stop_reason="cost_cap"),
                              ["a", "b"], {"a": "hit", "b": "miss"}, registry={"entries": []})
    with pytest.raises(A.PartialRunError):                # complete 표시를 속여도 상태로 막는다
        A.ai_agreement_report(_official_run(recs), ["a", "b"], {"a": "hit", "b": "miss"},
                              registry={"entries": []})


def test_e_표본_후보가_기록에_없으면_일치도를_내지_않는다():
    recs = [{"canonical_candidate_id": "a", "status": A.AI_JUDGED, "verdict": "hit"}]
    with pytest.raises(A.PartialRunError):
        A.ai_agreement_report(_official_run(recs), ["a", "b"], {"a": "hit", "b": "miss"},
                              registry={"entries": []})


def test_e_완결된_실행이면_형식_오류를_따로_세고_일치도를_낸다():
    recs = [{"canonical_candidate_id": "a", "status": A.AI_JUDGED, "verdict": "hit"},
            {"canonical_candidate_id": "b", "status": A.AI_JUDGED, "verdict": "miss"},
            {"canonical_candidate_id": "c", "status": A.AI_FORMAT_ERROR}]
    rep = A.ai_agreement_report(_official_run(recs), ["a", "b", "c"], {"a": "hit", "b": "hit", "c": "miss"},
                                registry={"entries": []})
    assert rep["ai_format_error"] == 1 and rep["both_judged"] == 2 and rep["secondary_holds"] == 0
    assert rep["agreement_3way"]["agree"] == 1


# ── (f) 합성 드라이런 산출물은 분석이 거부 ───────────────────────────────────

def test_f_드라이런_실행_기록은_synthetic_dryrun을_달고_일치도가_거부한다(synth):
    res = run(synth, lambda p: ok_response())
    rec = {"provenance": PV.SYNTHETIC_DRYRUN, "dataset_id": "synthetic_dryrun",
           "evaluation_id": "synthetic_dryrun", **res}
    ids = [r["canonical_candidate_id"] for r in res["candidates"]]
    with pytest.raises(PV.ProvenanceError, match="synthetic_dryrun"):
        A.ai_agreement_report(rec, ids, {i: "hit" for i in ids})


def test_f_합성_목록은_synthetic_dryrun을_단다(synth):
    assert synth["queue"]["provenance"] == PV.SYNTHETIC_DRYRUN
    meta = json.loads((synth["images"] / PV.PROVENANCE_FILE).read_text(encoding="utf-8"))
    assert meta["provenance"] == PV.SYNTHETIC_DRYRUN and meta["contains_real_dataset_images"] is False


def test_f_analyze_qa는_synthetic_dryrun_내보내기를_거부한다():
    export = {"provenance": PV.SYNTHETIC_DRYRUN, "dataset_id": "synthetic_dryrun",
              "evaluation_id": "synthetic_dryrun", "adjudicator": "primary",
              "requested_scope": "labelled_candidates", "comparison_mode": "candidate_generation_included"}
    with pytest.raises(ValidationError, match="synthetic_dryrun"):
        analyze_qa.analyse(export, 2, 10, 1, ["aida", "all_label_iou"])


# ── (g) practice1은 공식 입력이 아니다 ───────────────────────────────────────

def test_g_등록부에_practice1이_연습_출처손상으로_적혀_있다():
    reg = PV.load_registry()
    entry = [e for e in reg["entries"] if e.get("evaluation_id") == "practice1"][0]
    assert entry["dataset_id"] == "006e49d2cbc9"
    assert entry["role"] == "practice" and entry["provenance"] == "damaged"
    assert set(entry["allowed_uses"]) == {"ui_reference", "timing_reference"}


@pytest.mark.parametrize("ids", [{"dataset_id": "006e49d2cbc9", "evaluation_id": "practice1"},
                                 {"dataset_id": "006e49d2cbc9", "evaluation_id": "other_eval"}])
def test_g_analyze_qa는_practice1과_연습_데이터셋을_거부한다(ids):
    export = {**ids, "adjudicator": "primary", "requested_scope": "labelled_candidates",
              "comparison_mode": "candidate_generation_included"}
    with pytest.raises(ValidationError, match="출처 등록부"):
        analyze_qa.analyse(export, 2, 10, 1, ["aida", "all_label_iou"])


def test_g_AI_일치도도_practice1을_거부한다():
    rec = {"dataset_id": "006e49d2cbc9", "evaluation_id": "practice1", "complete": True, "stop_reason": None,
           "candidates": [{"canonical_candidate_id": "a", "status": A.AI_JUDGED, "verdict": "hit"}]}
    with pytest.raises(PV.ProvenanceError):
        A.ai_agreement_report(rec, ["a"], {"a": "hit"})


def test_g_등록부가_없으면_분석하지_않는다(tmp_path):
    with pytest.raises(PV.ProvenanceError):
        PV.load_registry(tmp_path / "missing.json")
