"""검정력 격자 산출물 묶기 검사 (experiment/package_power_grid.py)."""
import json
from pathlib import Path

import pytest

import package_power_grid as pkg

EXPERIMENT = Path(__file__).resolve().parents[1]


def test_Wilson_구간은_0회_성공에서도_폭이_있다():
    """복제 60에 성공 0회: 상한 = (z²/2n) / (1 + z²/n) × 2 = 0.0602.

    표의 `±표준오차`는 여기서 0.00이 된다 — 그 표시가 과신이라는 근거다.
    """
    low, high = pkg.wilson(0, 60)
    assert low == 0.0
    assert high == pytest.approx(0.0602, abs=1e-4)
    low, high = pkg.wilson(60, 60)
    assert low == pytest.approx(0.9398, abs=1e-4)
    assert high == 1.0


def test_칸_씨앗_규칙이_power_report의_시나리오_이름과_같다():
    import power_report
    raw = json.loads((EXPERIMENT / "planning_scenarios.json").read_text(encoding="utf-8"))
    cell = power_report.scenarios_from_grid(raw["grid"], datasets=[3], budgets=[240])[0]
    s = cell["scenario"]
    row = {"datasets": 3, "budget": 240, "prevalence": cell["prevalence"],
           "dependence": cell["dependence"], "ranking": cell["ranking"]}
    assert pkg.cell_seed(s.random_seed, row) == f"{s.random_seed}|{s.name}"


def _raw(power=0.5, iterations=60):
    row = {"prevalence": 0.065, "dependence": "independent", "ranking": "small_gap",
           "aida_auc": 0.75, "baseline_auc": 0.7, "datasets": 1, "budget": 120,
           "pool": 240, "images": 149, "status": "too_few_iterations",
           "official_scenario": False, "pool_unique_errors_per_dataset": 15.6,
           "mean_aida_unique_errors": 10.0, "mean_baseline_unique_errors": 9.0,
           "blocks_per_dataset": 1, "blocks_total": 1, "per_dataset_evidence": "observed",
           "evidence": "observed", "required_active_minutes": 10.0,
           "deltas": [{"name": n, "delta": d, "power": power, "monte_carlo_se": 0.06,
                       "exceeds_expected_errors": False} for n, d in (("A", 1), ("B", 6), ("C", 12))]}
    return {"iterations": iterations, "bootstrap_iterations": 150, "rows": [row]}


def test_모든_칸을_탐색으로_표시하고_성공_횟수를_복원한다():
    rows = pkg.package(_raw(power=0.5), random_seed=7, iterations=60, bootstrap=150)
    assert rows[0]["exploratory"] is True
    assert rows[0]["official_iteration_requirement_met"] is False
    assert [d["successes"] for d in rows[0]["deltas"]] == [30, 30, 30]


def test_검정력이_복제_수로_떨어지지_않으면_멈춘다():
    """0.5 × 7 = 3.5 — 원시 결과와 복제 수가 어긋났다는 뜻이다."""
    with pytest.raises(ValueError):
        pkg.package(_raw(power=0.5, iterations=7), random_seed=7, iterations=7, bootstrap=150)


def test_CSV는_칸마다_Δ_안_하나씩_한_줄이다():
    rows = pkg.package(_raw(), random_seed=7, iterations=60, bootstrap=150)
    text = pkg.to_csv(rows)
    lines = text.strip().split("\n")
    assert len(lines) == 1 + 3
    assert lines[0].split(",") == pkg.CSV_FIELDS


def test_이미_있는_산출물은_덮어쓰지_않는다(tmp_path, monkeypatch):
    raw_path = tmp_path / "raw.json"
    raw_path.write_text(json.dumps(_raw()), encoding="utf-8")
    monkeypatch.setattr(pkg, "OUT_DIR", tmp_path)
    (tmp_path / "grid.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["package_power_grid.py", "--raw", str(raw_path),
                                     "--name", "grid", "--code-commit", "x",
                                     "--scenario-commit", "159d04d8",
                                     "--runtime-minutes", "1", "--command", "c",
                                     "--hardware", "h"])
    with pytest.raises(SystemExit, match="덮어쓰지 않는다"):
        pkg.main()
    assert (tmp_path / "grid.json").read_text(encoding="utf-8") == "{}"


def test_묶은_격자_산출물이_명세와_맞는다():
    """저장소에 넣은 산출물의 해시와 표시를 확인한다."""
    import hashlib
    base = EXPERIMENT / "planning_evidence"
    manifest = json.loads((base / "power_grid_explore_2026-09-13.manifest.json").read_text(encoding="utf-8"))
    for key in ("packaged_json", "packaged_csv"):
        data = (base / manifest[key]).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == manifest[key + "_sha256"]
    packaged = json.loads((base / manifest["packaged_json"]).read_text(encoding="utf-8"))
    assert len(packaged["rows"]) == manifest["cells"] == 240
    assert all(r["exploratory"] and r["status"] == "too_few_iterations"
               and not r["official_iteration_requirement_met"] for r in packaged["rows"])
    assert packaged["n_required_status"] == "undetermined"
    assert manifest["iterations"] == 60 and manifest["bootstrap_iterations"] == 150
