"""설정이 다르면 출력 자리도 달라야 한다 (docs/25 2단계).

> "설정이 다른 실행은 별도 출력 위치를 사용하고 기존 결과를 조용히 덮어쓰지
> 않는다."

**서브프로세스로 잰다.** `config`는 불러올 때 환경을 읽어 상수를 굳히므로
`importlib.reload`로는 바뀐 환경이 안 잡힌다 — 그걸로 재면 검사가 통과해도
아무것도 확인한 게 없다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

EXPERIMENT = Path(__file__).resolve().parents[1]

# 오류 비율이 바뀌면 내용이 달라지는 산출물 전부.
# **OBB도 포함한다** — build_obb_condition도 ERROR_RATIO를 쓴다.
ERROR_DEPENDENT = ("conditions", "data_yaml", "runs", "metrics",
                   "multi_seed", "agg",
                   "obb_conditions", "obb_data_yaml", "obb_runs",
                   "obb_metrics", "obb_multi_seed", "obb_agg")

_PROBE = (
    "import json, config as c; "
    "print(json.dumps({"
    "'conditions': c.CONDITIONS_DIR.name, 'data_yaml': c.DATA_YAML_DIR.name, "
    "'runs': c.RUNS_DIR.name, 'metrics': c.METRICS_CSV.name, "
    "'multi_seed': c.MULTI_SEED_CSV.name, 'agg': c.AGG_CSV.name, "
    "'obb_conditions': c.OBB_CONDITIONS_DIR.name, "
    "'obb_data_yaml': c.OBB_DATA_YAML_DIR.name, 'obb_runs': c.OBB_RUNS_DIR.name, "
    "'obb_metrics': c.OBB_METRICS_CSV.name, "
    "'obb_multi_seed': c.OBB_MULTI_SEED_CSV.name, 'obb_agg': c.OBB_AGG_CSV.name, "
    "'labels': c.LABELS_GT_TRAIN_DIR.parent.name, 'ratio': str(c.ERROR_RATIO)}))")


def _run(code: str, env: dict) -> subprocess.CompletedProcess:
    """자식과 부모가 **같은 인코딩을 쓰게** 못 박고 돌린다.

    `text=True`만 주면 부모는 OS 로캘(윈도우에서 cp949)로 푼다. 자식이 UTF-8로
    쓰면(`PYTHONIOENCODING`이 켜져 있는 셸이 그렇다) 읽는 스레드가
    `UnicodeDecodeError`로 죽고 `stderr`가 **None**이 된다. 그러면 검사는
    "거부 메시지가 없다"가 아니라 **`TypeError`로** 떨어져 무엇이 틀렸는지
    알아보기 어렵다. 실제로 그렇게 한 번 헤맸다.
    """
    return subprocess.run(
        [sys.executable, "-c", code], cwd=str(EXPERIMENT), capture_output=True,
        encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", **env})


def probe(**env) -> dict:
    out = _run(_PROBE, env)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def rejected(**env) -> str:
    """설정이 거부되는가. 거부되면 stderr를 돌려준다."""
    out = _run("import config", env)
    assert out.returncode != 0, "거부돼야 하는 설정이 통과했다"
    assert out.stderr is not None, "stderr를 못 읽었다 — 인코딩이 어긋났다"
    return out.stderr


# --- 기본값은 그대로 -----------------------------------------------------------

def test_default_keeps_every_existing_path():
    """기본값에는 접미사가 없어야 한다 — 기존 산출물이 전부 그 경로다."""
    p = probe(AIDA_ERROR_RATIO="0.3")
    assert p["conditions"] == "conditions"
    assert p["metrics"] == "metrics.csv"
    assert p["multi_seed"] == "metrics_multi_seed.csv"
    assert p["agg"] == "metrics_agg.csv"
    assert p["obb_metrics"] == "metrics_obb.csv"


# --- 오류 비율이 다르면 전부 갈린다 ---------------------------------------------

@pytest.mark.parametrize("key", ERROR_DEPENDENT)
def test_error_ratio_separates_every_dependent_output(key):
    """하나라도 안 갈리면 그 파일에서 다른 실험의 수치를 읽는다."""
    default = probe(AIDA_ERROR_RATIO="0.3")
    changed = probe(AIDA_ERROR_RATIO="0.1")
    assert changed[key] != default[key], f"{key}가 오류 비율로 안 갈린다"


def test_two_non_default_ratios_differ():
    a = probe(AIDA_ERROR_RATIO="0.1")
    b = probe(AIDA_ERROR_RATIO="0.2")
    for key in ERROR_DEPENDENT:
        assert a[key] != b[key], f"{key}: 0.1과 0.2가 같은 자리를 쓴다"


def test_clean_labels_do_not_fork():
    """깨끗한 라벨은 오류 비율과 무관하다 — 쓸데없이 갈리면 용량만 먹는다."""
    assert probe(AIDA_ERROR_RATIO="0.1")["labels"] == probe(AIDA_ERROR_RATIO="0.3")["labels"]


# --- 반올림 충돌 ---------------------------------------------------------------

def test_close_ratios_never_share_a_path():
    """0.101과 0.104는 다른 설정이다.

    `round(r * 100)`으로 이름을 만들면 둘 다 `_r10`이 되어 **다른 실험이 서로를
    덮어쓴다.** 거부하든 갈라 쓰든, 같은 자리를 쓰면 안 된다.
    """
    try:
        a = probe(AIDA_ERROR_RATIO="0.101")
        b = probe(AIDA_ERROR_RATIO="0.104")
    except AssertionError:
        rejected(AIDA_ERROR_RATIO="0.101")      # 거부도 답이다
        return
    for key in ERROR_DEPENDENT:
        assert a[key] != b[key], f"{key}: 0.101과 0.104가 같은 자리를 쓴다"


def test_ratio_keeps_its_written_form():
    """0.10과 0.1은 같은 값이므로 같은 자리여야 한다."""
    assert probe(AIDA_ERROR_RATIO="0.10") == probe(AIDA_ERROR_RATIO="0.1")


# --- 말이 안 되는 값은 거부한다 --------------------------------------------------

@pytest.mark.parametrize("bad", ["-0.1", "1.5", "nan", "inf", "", "abc"])
def test_impossible_ratios_are_refused(bad):
    """조용히 통과하면 그 값으로 만든 조건이 무엇인지 아무도 모른다."""
    err = rejected(AIDA_ERROR_RATIO=bad)
    assert "AIDA_ERROR_RATIO" in err


# --- 이미 갈리던 것들이 그대로인가 ----------------------------------------------

def test_other_settings_still_separate():
    base = probe()
    assert probe(AIDA_DATASET="coco")["conditions"] != base["conditions"]
    assert probe(AIDA_N_TRAIN="800")["conditions"] != base["conditions"]
    assert probe(AIDA_CLASSES="Car,Van")["conditions"] != base["conditions"]
