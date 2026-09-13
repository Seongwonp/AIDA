"""`N_required` 사전 계획 시뮬레이터를 검증한다 (docs/n-required-plan.md).

**시뮬레이터가 틀리면 틀린 표본 크기가 그럴듯한 표로 나온다.** 그래서 결과를
보기 전에 시뮬레이터 자체를 손계산 fixture로 고정한다.

몬테카를로 결과의 단조성은 **엄격한 부등식으로 고정하지 않는다.** 잡음이 있어
반복 수가 모자라면 참인 경향도 한 번씩 뒤집힌다 — 차이가 크게 나는 조합과
허용 오차를 쓴다.
"""
import json
import math
import random
from dataclasses import fields, replace
from pathlib import Path

import pytest

import evaluation.planning as planning
from evaluation.bootstrap import equal_weight_difference
from evaluation.paired import paired_difference
from evaluation.planning import (BASELINE, METHOD, ONE_SIDED_ALPHA,
                                 PlanningScenario, auc_from_strength,
                                 build_world, delta_options,
                                 power_against_targets, scenario_from_dict,
                                 simulate_power, strength_from_auc,
                                 validate_scenario)
from evaluation.schema import ValidationError
from evaluation.summary import summarise

EXPERIMENT = Path(__file__).resolve().parents[1]
ALL_FIELDS = [f.name for f in fields(PlanningScenario)
              if f.name not in ("name", "sources", "note")]


def tags(value="unsupported_sensitivity_example"):
    return {name: value for name in ALL_FIELDS}


def mk(**kw) -> PlanningScenario:
    base = dict(name="t", dataset_count=1, candidates_per_dataset=40,
                images_per_dataset=20, candidates_per_image={"2": 1.0},
                duplicates_per_unique_error={"1": 1.0}, error_prevalence=0.3,
                image_error_concentration=0.0, aida_ranking_strength=0.5,
                baseline_ranking_strength=0.5, hold_rate=0.0, delta=None,
                alpha=0.05, target_power=None, iterations=20,
                bootstrap_iterations=40, random_seed=7, sources=tags())
    base.update(kw)
    return PlanningScenario(**base)


# ── 입력 거부 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("change", [
    {"error_prevalence": float("nan")},
    {"error_prevalence": 1.5},
    {"error_prevalence": -0.1},
    {"hold_rate": float("inf")},
    {"image_error_concentration": 2.0},
    {"aida_ranking_strength": -1.0},
    {"baseline_ranking_strength": float("nan")},
    {"dataset_count": 0},
    {"dataset_count": True},
    {"iterations": 0},
    {"bootstrap_iterations": -5},
    {"candidates_per_dataset": 10, "images_per_dataset": 20},
    {"candidates_per_image": {}},
    {"candidates_per_image": {"2": 0.0}},
    {"candidates_per_image": {"0": 1.0}},
    {"candidates_per_image": {"x": 1.0}},
    {"duplicates_per_unique_error": {"1": -1.0}},
    {"delta": float("nan")},
    {"target_power": 1.2},
    {"random_seed": 1.5},
    {"name": " "},
])
def test_잘못된_입력은_거부한다(change):
    with pytest.raises(ValidationError):
        validate_scenario(mk(**change))


def test_alpha는_규약이_고정한다():
    """시나리오에서 바꾸면 '그 값으로 계산했다'는 착각이 생긴다."""
    with pytest.raises(ValidationError, match="규약"):
        validate_scenario(mk(alpha=0.10))


def test_근거를_안_적은_값이_있으면_거부한다():
    partial = tags()
    partial.pop("error_prevalence")
    with pytest.raises(ValidationError, match="근거"):
        validate_scenario(mk(sources=partial))


def test_모르는_근거_표시는_거부한다():
    bad = dict(tags(), hold_rate="gut_feeling")
    with pytest.raises(ValidationError, match="모르는 근거"):
        validate_scenario(mk(sources=bad))


def test_파일의_모르는_항목은_거부한다():
    raw = {f.name: getattr(mk(), f.name) for f in fields(PlanningScenario)}
    raw["prevalance"] = 0.1          # 오타
    with pytest.raises(ValidationError, match="모르는 항목"):
        scenario_from_dict(raw)


def test_예산이_0이나_음수면_거부한다():
    for bad in (0, -3, 1.5, True):
        with pytest.raises(ValidationError):
            simulate_power(mk(delta=0.0), bad)


# ── 근거와 미정 상태 ─────────────────────────────────────────────────────────

def test_근거_없는_값이_하나라도_있으면_공식이_아니다():
    s = mk(sources=dict(tags("timing_pilot"),
                        aida_ranking_strength="unsupported_sensitivity_example"))
    assert s.official is False
    assert s.unsupported_fields == ["aida_ranking_strength"]
    assert mk(sources=tags("timing_pilot")).official is True


def test_Δ와_목표_검정력은_기본이_미정이다():
    s = mk()
    assert s.delta_status == "undetermined"
    assert s.target_power_status == "undetermined"
    assert all(o["delta_status"] == "undetermined" for o in delta_options(120))


def test_Δ가_없으면_검정력을_내지_않는다():
    got = simulate_power(mk(delta=None), 10)
    assert got["status"] == "delta_undetermined"
    assert got["power"] is None


def test_예산이_풀보다_크면_계산하지_않는다():
    got = simulate_power(mk(), 41, deltas=[0.0])
    assert got["status"] == "budget_exceeds_pool"
    assert got["power"] is None


def test_목표_검정력은_비교로만_본다():
    assert power_against_targets(0.85) == {"meets_0.80": True, "meets_0.90": False}
    assert power_against_targets(None) == {"meets_0.80": None, "meets_0.90": None}


# ── 순위 품질의 뜻 ───────────────────────────────────────────────────────────

def test_강도와_짝_비교_확률을_손계산과_맞춘다():
    """AUC = 1 − (1 − 강도)² / 2.

    강도 0   → 1 − 1/2    = 0.5   (무작위)
    강도 0.5 → 1 − 0.25/2 = 0.875
    강도 1   → 1.0               (완벽 — 모든 오류가 모든 정상 후보보다 위)
    AUC 0.7  → 강도 1 − √0.6 = 0.225403...
    """
    assert auc_from_strength(0.0) == 0.5
    assert auc_from_strength(0.5) == 0.875
    assert auc_from_strength(1.0) == 1.0
    assert auc_from_strength(3.0) == 1.0
    assert strength_from_auc(0.875) == pytest.approx(0.5)
    assert strength_from_auc(0.5) == 0.0
    assert strength_from_auc(0.7) == pytest.approx(0.2254033307585166)


def test_짝_비교_확률이_실제_점수에서도_맞는다():
    """공식이 아니라 **만들어진 점수**로 확인한다. 강도 0.5면 약 0.875."""
    s = mk(candidates_per_dataset=400, images_per_dataset=200,
           error_prevalence=0.5, aida_ranking_strength=0.5)
    adjudications, rankings = build_world(s, random.Random(12))
    is_error = {a.key: a.unique_error_id is not None for a in adjudications}
    mine = [r for r in rankings if r.method == METHOD]
    err = [r.severity for r in mine if is_error[r.candidate_key]]
    ok = [r.severity for r in mine if not is_error[r.candidate_key]]
    wins = sum(1 for e in err for o in ok if e > o)
    assert wins / (len(err) * len(ok)) == pytest.approx(0.875, abs=0.03)


@pytest.mark.parametrize("bad", [0.49, 1.01, float("nan"), float("inf"), True, "0.7", None])
def test_짝_비교_확률의_잘못된_값은_거부한다(bad):
    with pytest.raises(ValidationError):
        strength_from_auc(bad)


# ── 손계산 fixture ───────────────────────────────────────────────────────────

def test_모든_후보가_오류면_차이는_정확히_0이다():
    """풀 20건이 전부 서로 다른 오류라면 어느 순서로 10건을 봐도 10개를 찾는다.

    차이는 모든 복제·모든 재표집에서 0이다 → `ci_low = 0`.
    Δ=-1이면 `0 > -1`이라 항상 성공(1.0), Δ=0이면 `0 > 0`이 거짓이라 항상 0.0.
    """
    s = mk(candidates_per_dataset=20, images_per_dataset=10,
           error_prevalence=1.0, aida_ranking_strength=3.0,
           baseline_ranking_strength=0.0, iterations=5, bootstrap_iterations=20)
    got = simulate_power(s, 10, deltas=[-1.0, 0.0])
    assert [d["power"] for d in got["by_delta"]] == [1.0, 0.0]
    assert got["mean_method_unique_errors"] == 10.0
    assert got["mean_baseline_unique_errors"] == 10.0
    assert got["mean_observed_difference"] == 0.0


def test_같은_오류를_가리키는_중복이_부풀려지지_않는다():
    """이미지 5장 × 후보 3건, 전부 오류, 오류 하나를 후보 3건이 함께 가리킨다.

    hit 후보는 15건이지만 고유 오류는 5개다. 15로 세면 중복이 성과가 된다.
    """
    s = mk(candidates_per_dataset=15, images_per_dataset=5,
           candidates_per_image={"3": 1.0}, duplicates_per_unique_error={"3": 1.0},
           error_prevalence=1.0)
    adjudications, rankings = build_world(s, random.Random(3))
    got = summarise(adjudications, rankings, METHOD, None)
    assert got.hit_candidates == 15
    assert got.unique_error_yield == 5


def test_중복_묶음은_이미지를_넘지_않는다():
    s = mk(candidates_per_dataset=120, images_per_dataset=40,
           candidates_per_image={"1": 1, "3": 1, "5": 1},
           duplicates_per_unique_error={"1": 0.4, "2": 0.4, "4": 0.2},
           error_prevalence=0.6, image_error_concentration=0.5)
    adjudications, _ = build_world(s, random.Random(9))
    images_of: dict[str, set] = {}
    for a in adjudications:
        if a.unique_error_id:
            images_of.setdefault(a.unique_error_id, set()).add(a.image_id)
    assert images_of, "오류가 하나도 안 만들어졌다"
    assert all(len(v) == 1 for v in images_of.values())


def test_이미지_묶음과_풀_크기가_보존된다():
    s = mk(dataset_count=2, candidates_per_dataset=30, images_per_dataset=10,
           candidates_per_image={"3": 1.0})
    adjudications, rankings = build_world(s, random.Random(5))
    for name in ("ds1", "ds2"):
        mine = [a for a in adjudications if a.dataset_id == name]
        assert len(mine) == 30
        assert len({a.cluster for a in mine}) == 10
        assert all(a.cluster == f"{name}/{a.image_id}" for a in mine)
    # 두 방법 모두 모든 후보에 점수를 매긴다 — 같은 후보 집합이다.
    assert len(rankings) == 2 * len(adjudications)
    assert ({r.candidate_key for r in rankings if r.method == METHOD}
            == {r.candidate_key for r in rankings if r.method == BASELINE})


def test_보류는_성과가_아니지만_예산을_쓴다():
    s = mk(candidates_per_dataset=20, images_per_dataset=10,
           error_prevalence=1.0, hold_rate=1.0)
    adjudications, rankings = build_world(s, random.Random(1))
    got = summarise(adjudications, rankings, METHOD, 10)
    assert got.in_budget == 10
    assert got.holds == 10
    assert got.unique_error_yield == 0


# ── 실제 집계 함수를 부르는가 ─────────────────────────────────────────────────

def test_실제_부트스트랩과_판정_규칙을_그대로_부른다(monkeypatch):
    """**집계 로직을 복제하지 않는다.** 가로채 보면 실제 함수가 불린다."""
    calls = []
    real = planning.paired_cluster_bootstrap

    def spy(adjudications, rankings, method, baseline, budget=None, iterations=0, seed=0):
        calls.append({"datasets": {a.dataset_id for a in adjudications},
                      "method": method, "baseline": baseline, "budget": budget,
                      "iterations": iterations})
        return real(adjudications, rankings, method, baseline, budget=budget,
                    iterations=iterations, seed=seed)

    monkeypatch.setattr(planning, "paired_cluster_bootstrap", spy)
    simulate_power(mk(dataset_count=3, iterations=4, bootstrap_iterations=11), 10,
                   deltas=[0.0])
    assert len(calls) == 4
    for c in calls:
        # 데이터셋을 **한꺼번에** 넘긴다 — 동등 가중은 부트스트랩 안에서 한다.
        assert c["datasets"] == {"ds1", "ds2", "ds3"}
        assert (c["method"], c["baseline"], c["budget"], c["iterations"]) == (
            METHOD, BASELINE, 10, 11)


def test_데이터셋_동등_가중이_유지된다():
    """전체 차이는 데이터셋별 차이의 **단순 평균**이어야 한다."""
    s = mk(dataset_count=3, candidates_per_dataset=60, images_per_dataset=30,
           aida_ranking_strength=2.0, baseline_ranking_strength=0.0)
    adjudications, rankings = build_world(s, random.Random(21))
    per = []
    for name in ("ds1", "ds2", "ds3"):
        facts = [a for a in adjudications if a.dataset_id == name]
        keys = {a.key for a in facts}
        ranks = [r for r in rankings if r.candidate_key in keys]
        per.append(paired_difference(facts, ranks, METHOD, BASELINE, 20)["difference"])
    overall = equal_weight_difference(adjudications, rankings, METHOD, BASELINE, 20)
    assert overall == pytest.approx(sum(per) / 3)


# ── 재현성과 반복 수 ─────────────────────────────────────────────────────────

def test_같은_씨앗이면_같은_결과가_나온다():
    s = mk(iterations=6, bootstrap_iterations=15, aida_ranking_strength=1.0)
    a = simulate_power(s, 10, deltas=[0.0, 1.0])
    b = simulate_power(s, 10, deltas=[0.0, 1.0])
    assert a == b


def test_씨앗이_다르면_세상이_달라진다():
    s = mk()
    w1, _ = build_world(s, random.Random(1))
    w2, _ = build_world(s, random.Random(2))
    assert [a.verdict for a in w1] != [a.verdict for a in w2]


def test_반복이_모자라면_공식_판정을_막는다():
    got = simulate_power(mk(iterations=3, bootstrap_iterations=10), 10, deltas=[0.0])
    assert got["status"] == "too_few_iterations"
    assert got["official_iterations"] is False
    assert "공식 판정" in got["reason"]


def test_반복이_최소를_넘으면_막지_않는다(monkeypatch):
    monkeypatch.setattr(planning, "MIN_OFFICIAL_ITERATIONS", 3)
    monkeypatch.setattr(planning, "MIN_OFFICIAL_BOOTSTRAP", 10)
    got = simulate_power(mk(iterations=3, bootstrap_iterations=10), 10, deltas=[0.0])
    assert got["status"] == "ok"
    assert got["official_iterations"] is True


# ── 통계적 성질 ──────────────────────────────────────────────────────────────

def test_두_방법이_같으면_기각률이_유의수준_부근이다():
    """순위 품질이 같으면 Δ=0을 넘는 '성공'은 우연뿐이다.

    판정 규칙이 양측 95% 구간의 아래끝이라 기대값은 α/2 = 0.025 근처다.
    **개발 중 잰 값은 0.0025~0.0175**(복제 400)였다 — 이산성 때문에 보수적으로
    나온다. 부풀려지면(잘못 짝지은 재표집 등) 여기서 걸린다. 몬테카를로 오차를
    감안해 상한만 넉넉히 둔다.
    """
    s = mk(iterations=300, bootstrap_iterations=60, random_seed=2026)
    got = simulate_power(s, 20, deltas=[0.0])
    se = math.sqrt(ONE_SIDED_ALPHA * (1 - ONE_SIDED_ALPHA) / 300)
    assert got["power"] <= ONE_SIDED_ALPHA + 4 * se


def test_효과가_커지면_검정력이_대체로_는다():
    # 기준선을 **무작위 순서(강도 0)** 로 둔다. 기준선 강도 0.5도 오류를 꽤 잘
    # 올려서(짝 비교로 약 87%) '강한 효과'가 생각만큼 크지 않았다 — 처음엔 그걸
    # 놓쳐 이 검사가 0.68로 떨어졌다. 단언은 그대로 두고 대비를 분명히 했다.
    common = dict(candidates_per_dataset=60, images_per_dataset=30,
                  baseline_ranking_strength=0.0,
                  iterations=60, bootstrap_iterations=60, random_seed=31)
    # 약한 쪽은 기준선(0.0)과 거의 같게 둔다. 0.6이면 무작위 기준선 대비 이미
    # 차이가 평균 7건이라 검정력이 0.87까지 올라 '약한 효과'가 아니었다.
    weak = simulate_power(mk(aida_ranking_strength=0.1, **common), 20, deltas=[0.0])
    strong = simulate_power(mk(aida_ranking_strength=3.0, **common), 20, deltas=[0.0])
    assert strong["power"] >= 0.8
    assert strong["power"] >= weak["power"] + 0.3


def test_N이_커지면_검정력이_대체로_는다():
    s = mk(candidates_per_dataset=160, images_per_dataset=80,
           aida_ranking_strength=1.0, iterations=60, bootstrap_iterations=60,
           random_seed=41)
    small = simulate_power(s, 10, deltas=[0.0])
    large = simulate_power(s, 60, deltas=[0.0])
    tolerance = 2 * math.sqrt(0.25 / 60)          # 복제 60에서 최대 SE의 2배
    assert large["power"] + tolerance >= small["power"]
    assert large["mean_observed_difference"] > small["mean_observed_difference"]


# ── 시나리오 파일과 표 ───────────────────────────────────────────────────────

def test_시나리오_파일이_읽히고_전부_민감도_전용이다():
    import power_report
    raw = json.loads((EXPERIMENT / "planning_scenarios.json").read_text(encoding="utf-8"))
    cells = power_report.scenarios_from_grid(raw["grid"])
    grid = raw["grid"]
    assert len(cells) == (len(grid["datasets"]["values"]) * len(grid["budgets"]["values"])
                          * len(grid["error_prevalence"]) * len(grid["dependence"])
                          * len(grid["ranking"]))
    # 완벽한 순위(AUC 1.0)를 몰래 가정하지 않는다.
    assert all(row["aida_auc"] < 1.0 and row["baseline_auc"] < 1.0
               for row in grid["ranking"])
    for cell in cells:
        s = cell["scenario"]
        assert s.official is False                      # 순위 품질이 근거 없음
        assert "aida_ranking_strength" in s.unsupported_fields
        assert s.delta_status == "undetermined"
        assert s.target_power_status == "undetermined"
        assert s.candidates_per_dataset >= cell["budget"]
        assert set(planning.REQUIRED_SOURCE_FIELDS) <= set(s.sources)


def test_용량_열을_손계산과_맞춘다():
    import power_report
    got = power_report.capacity_columns(3, 120, 120, 5.02, [60, 30])
    assert got["blocks_per_dataset"] == 1 and got["blocks_total"] == 3
    assert got["per_dataset_evidence"] == "observed"
    assert got["evidence"] == "extrapolated"
    assert got["required_active_minutes"] == 30.1
    assert got["capacity"]["60"] == {"n_capacity": 120, "meets": True}
    assert got["capacity"]["30"] == {"n_capacity": 0, "meets": False}

    big = power_report.capacity_columns(3, 600, 120, 5.02, [180])
    assert big["blocks_total"] == 15
    assert big["per_dataset_evidence"] == "extrapolated"
    assert big["evidence"] == "strongly_extrapolated"
    assert big["capacity"]["180"]["meets"] is True


def test_설정값_기대_오류_수는_손계산과_맞는다():
    import power_report
    # 풀 480 × 0.065 / 평균 중복 (1×0.6 + 2×0.3 + 3×0.1 = 1.5) = 20.8
    got = power_report.nominal_unique_errors(480, 0.065, {"1": 0.6, "2": 0.3, "3": 0.1})
    assert got == pytest.approx(20.8)
    c = [o for o in delta_options(240) if o["name"] == "C"][0]
    assert c["delta"] == 24


def test_이미지당_후보가_1건이면_설정한_중복이_만들어지지_않는다():
    """**설정값으로 기대 오류 수를 내면 틀린다**는 것을 고정한다.

    이미지 10장 × 후보 1건, 전부 오류, 중복을 '한 오류에 후보 3건'으로 설정해도
    같은 이미지에 후보가 1건뿐이라 묶을 수 없다. 실제 고유 오류는 10개다
    (설정값 계산은 10 ÷ 3 ≈ 3.3).
    """
    s = mk(candidates_per_dataset=10, images_per_dataset=10,
           candidates_per_image={"1": 1.0}, duplicates_per_unique_error={"3": 1.0},
           error_prevalence=1.0, iterations=2, bootstrap_iterations=5)
    got = simulate_power(s, 5, deltas=[0.0])
    assert got["mean_pool_unique_errors"] == 10.0


@pytest.mark.parametrize("flag", ["--iterations", "--bootstrap"])
def test_반복_수_0을_조용히_기본값으로_바꾸지_않는다(flag):
    """`args.iterations or 60`으로 짜여 있어 0을 주면 60으로 돌았다. 거부해야 한다."""
    import os
    import subprocess
    import sys
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(EXPERIMENT)}
    got = subprocess.run([sys.executable, "power_report.py", "--estimate-only", flag, "0"],
                         cwd=EXPERIMENT, env=env, capture_output=True,
                         encoding="utf-8", errors="replace")
    assert got.returncode != 0
    assert "1 이상" in got.stderr
