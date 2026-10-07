"""nuImages val 평가 표본 (docs/nuimages-data-plan.md).

지키는 것 셋.

1. **사전 등록이 커밋되어 있어야 val을 연다.** 커밋 안 됐거나 고친 채면 멈춘다.
2. **기록 하나가 표본을 채우지 않는다** — 기록마다 최대 `per_log`장.
3. **씨앗으로 다시 만들 수 있다.**

손계산 세계 — 기록 셋(L0 키프레임 5, L1 3, L2 1), sweep 하나는 세지 않는다.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nuimages_eval_sample as V  # noqa: E402


def tables():
    sample, sample_data = [], []
    for log, n in (("L0", 5), ("L1", 3), ("L2", 1)):
        for j in range(n):
            s = f"{log}s{j}"
            sample.append({"token": s, "log_token": log})
            sample_data.append({"token": f"{log}d{j}", "sample_token": s, "is_key_frame": True,
                                "calibrated_sensor_token": "cf", "filename": f"samples/{s}.jpg"})
    sample_data.append({"token": "sweep", "sample_token": "L0s0", "is_key_frame": False,
                        "calibrated_sensor_token": "cf", "filename": "sweeps/p.jpg"})
    return {"log": [{"token": t, "location": "boston-seaport"} for t in ("L0", "L1", "L2")],
            "sensor": [{"token": "sf", "channel": "CAM_FRONT"}],
            "calibrated_sensor": [{"token": "cf", "sensor_token": "sf"}],
            "sample": sample, "sample_data": sample_data}


def test_기록마다_최대_per_log장만_뽑는다():
    result = V.sample_by_log(tables(), images=100, per_log=2, seed=1)
    counts = result["summary"]
    assert counts["images"] == 5                        # 2 + 2 + 1
    assert counts["max_per_log"] == 2 and counts["logs"] == 3
    assert counts["shortfall"] == 95
    assert "sweep" not in {r["sample_data_token"] for r in result["rows"]}


def test_목표_수에_닿으면_멈춘다():
    result = V.sample_by_log(tables(), images=3, per_log=2, seed=1)
    assert result["summary"]["images"] == 3 and result["summary"]["shortfall"] == 0


def test_씨앗으로_다시_만들_수_있다():
    tokens = lambda seed: [r["sample_data_token"]
                           for r in V.sample_by_log(tables(), 4, 2, seed)["rows"]]
    assert tokens(7) == tokens(7)
    assert any(tokens(7) != tokens(s) for s in range(8, 30))


def test_목표나_기록당_수가_0이면_거부한다():
    with pytest.raises(ValueError):
        V.sample_by_log(tables(), images=0, per_log=2, seed=1)
    with pytest.raises(ValueError):
        V.sample_by_log(tables(), images=3, per_log=0, seed=1)


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    return tmp_path


def test_커밋되지_않은_사전_등록이면_val을_열지_않는다(repo):
    (repo / "prereg.md").write_text("N=60\n", encoding="utf-8")
    with pytest.raises(ValueError, match="커밋"):
        V.check_preregistration(repo, "prereg.md")


def test_커밋한_뒤_고친_사전_등록이면_val을_열지_않는다(repo):
    (repo / "prereg.md").write_text("N=60\n", encoding="utf-8")
    git(repo, "add", "prereg.md")
    git(repo, "commit", "-q", "-m", "prereg")
    (repo / "prereg.md").write_text("N=90\n", encoding="utf-8")
    with pytest.raises(ValueError, match="변경"):
        V.check_preregistration(repo, "prereg.md")


def test_커밋된_사전_등록이면_그_커밋을_돌려준다(repo):
    (repo / "prereg.md").write_text("N=60\n", encoding="utf-8")
    git(repo, "add", "prereg.md")
    git(repo, "commit", "-q", "-m", "prereg")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert V.check_preregistration(repo, "prereg.md") == head


@pytest.mark.parametrize("marker_line", [
    "| AI 판정자 | **[미기입 — 임의로 채우지 않는다]** |",
    "| API 버전 | [실행 전 기입] |",
    "결과: 【Q-A 결과】",
])
def test_커밋됐어도_빈칸_표시가_남은_사전_등록이면_val을_열지_않는다(repo, marker_line):
    """커밋·무변경만 보면 미완성 사전 등록으로도 val이 열린다 — 빈칸 표시도 막는다."""
    (repo / "prereg.md").write_text(f"# 사전 등록\nN=90\n{marker_line}\n", encoding="utf-8")
    git(repo, "add", "prereg.md")
    git(repo, "commit", "-q", "-m", "prereg")
    with pytest.raises(ValueError, match="채우지 않은 칸") as exc:
        V.check_preregistration(repo, "prereg.md")
    assert "3행" in str(exc.value)


def test_하위_폴더의_사전_등록도_빈칸을_검사한다(repo):
    (repo / "docs").mkdir()
    (repo / "docs" / "prereg.md").write_text("C = 1,000\n모델 [실행 전 기입]\n", encoding="utf-8")
    git(repo, "add", "docs/prereg.md")
    git(repo, "commit", "-q", "-m", "prereg")
    with pytest.raises(ValueError, match="채우지 않은 칸"):
        V.check_preregistration(repo, "docs/prereg.md")


def test_빈칸을_채워_커밋하면_다시_열린다(repo):
    (repo / "prereg.md").write_text("모델 [실행 전 기입]\n", encoding="utf-8")
    git(repo, "add", "prereg.md")
    git(repo, "commit", "-q", "-m", "draft")
    with pytest.raises(ValueError):
        V.check_preregistration(repo, "prereg.md")
    (repo / "prereg.md").write_text("모델 claude-sonnet-5\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "filled")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert V.check_preregistration(repo, "prereg.md") == head


def test_빈칸_표시_목록과_위치():
    found = V.unfilled_markers("a\nb [미기입]\nc 【x】 [실행 전 기입]\n")
    assert [(m["line"], m["marker"]) for m in found] == [
        (2, "[미기입"), (3, "[실행 전 기입]"), (3, "【")]
    assert V.unfilled_markers("완성본\n") == []


def test_표본_요약은_소비한_기록과_남은_기록_수를_적는다():
    """개발/최종 경계 (사전 등록 D1). 다음 평가가 같은 기록을 다시 쓰지 않게."""
    t = tables()
    all_logs = {r["log_token"] for r in V._keyframes(t, None)}
    summ = V.sample_by_log(t, images=3, per_log=2, seed=1)["summary"]
    consumed = summ["consumed_log_tokens"]
    assert consumed == sorted(consumed) and len(consumed) == summ["logs"]
    assert set(consumed) <= all_logs
    assert summ["unconsumed_logs"] == len(all_logs) - len(consumed)
