"""설정이 다르면 출력 자리도 달라야 한다 (docs/25 2단계).

> "설정이 다른 실행은 별도 출력 위치를 사용하고 기존 결과를 조용히 덮어쓰지
> 않는다."

`AIDA_ERROR_RATIO`는 **주입되는 오류의 양**을 바꾸는데 경로에 안 들어갔다.
0.1로 만들면 0.3으로 만든 조건 폴더를 그대로 덮어쓴다 — 이름이 같으니 아무
경고도 없고, 그 폴더를 쓰는 앞 절들의 수치가 조용히 다른 것이 된다.
docs/21 AX에 위험으로 적어두기만 했던 것이다.

**서브프로세스로 잰다.** `config`는 불러올 때 환경을 읽어 상수를 굳히므로
`importlib.reload`로는 바뀐 환경이 안 잡힌다 — 그걸로 재면 검사가 통과해도
아무것도 확인한 게 없다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parents[1]


def paths_with(**env) -> dict:
    code = ("import json, config; "
            "print(json.dumps({'conditions': config.CONDITIONS_DIR.name, "
            "'runs': config.RUNS_DIR.name, 'metrics': config.METRICS_CSV.name, "
            "'labels': config.LABELS_GT_TRAIN_DIR.parent.name, "
            "'ratio': config.ERROR_RATIO}))")
    out = subprocess.run([sys.executable, "-c", code], cwd=str(EXPERIMENT),
                         capture_output=True, text=True,
                         env={**os.environ, **env})
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_error_ratio_changes_the_conditions_dir():
    default = paths_with(AIDA_ERROR_RATIO="0.3")
    changed = paths_with(AIDA_ERROR_RATIO="0.1")
    assert changed["ratio"] == 0.1
    assert changed["conditions"] != default["conditions"], \
        "오류 비율이 다른데 같은 폴더에 쓰면 기존 조건을 덮어쓴다"
    assert changed["runs"] != default["runs"]


def test_error_ratio_also_separates_metrics():
    default = paths_with(AIDA_ERROR_RATIO="0.3")
    changed = paths_with(AIDA_ERROR_RATIO="0.1")
    assert changed["metrics"] != default["metrics"], \
        "지표 파일도 갈려야 한다 — 안 그러면 다른 실험의 수치를 읽는다"


def test_clean_labels_do_not_fork():
    """깨끗한 라벨은 오류 비율과 무관하다 — 쓸데없이 갈리면 용량만 먹는다."""
    default = paths_with(AIDA_ERROR_RATIO="0.3")
    changed = paths_with(AIDA_ERROR_RATIO="0.1")
    assert changed["labels"] == default["labels"]


def test_default_error_ratio_keeps_the_old_path():
    """기본값에는 접미사가 없어야 한다 — 기존 산출물이 전부 그 경로다."""
    p = paths_with(AIDA_ERROR_RATIO="0.3")
    assert p["conditions"] == "conditions"
    assert p["metrics"] == "metrics.csv"


def test_other_settings_still_separate():
    """이미 갈리던 것들이 그대로인지 — 접미사를 건드렸으므로 확인한다."""
    base = paths_with()
    assert paths_with(AIDA_DATASET="coco")["conditions"] != base["conditions"]
    assert paths_with(AIDA_N_TRAIN="800")["conditions"] != base["conditions"]
    assert paths_with(AIDA_CLASSES="Car,Van")["conditions"] != base["conditions"]
