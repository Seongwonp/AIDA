"""`N_required` 사전 계획 — 검정력 시뮬레이션 (docs/n-required-plan.md).

**시간으로 표본 크기를 정하지 않는다.** `activity.capacity_from_blocks`가 내는
`N_capacity`는 "시간 안에 몇 개를 볼 수 있는가"이고, 여기서 묻는 것은 "목표 Δ를
정해진 검정력으로 탐지하려면 데이터셋당 몇 개를 봐야 하는가"다.

## 왜 이항 검정으로 계산하지 않는가

후보는 독립 베르누이가 **아니다.** 교과서 공식을 쓰면 필요량이 작게 나온다.

- 같은 이미지의 후보가 묶인다 (재표집 단위가 이미지다)
- 여러 후보가 **같은 `unique_error_id`** 를 가리킬 수 있다 — 중복 제거하면
  성과가 줄어든다
- AIDA와 기준선이 **같은 후보 판정을 공유**한다 (짝지음)
- 순위와 검수 예산 때문에 결과가 **비선형**이다 — 상위 N이 바뀌면 성과가
  계단처럼 움직인다
- 데이터셋은 **동등 가중**이다

## 그래서 집계 규칙을 그대로 호출한다

이 모듈은 **가상의 판정 기록을 만들기만 한다.** 순위·동점·중복 제거·예산·
재표집·동등 가중은 전부 `evaluation`의 실제 함수가 한다
(`paired_cluster_bootstrap`, `verdict_against_delta`). **집계 로직을 복제하지
않는다** — 복제하면 시뮬레이터가 통과시킨 설계를 실제 평가가 떨어뜨린다.

## 이것으로 무엇을 정하지 않는가

개발 데이터에서 짐작한 시나리오는 **최종 자연 오류 분포를 보장하지 않는다.**
여기서 나오는 것은 설계 민감도이고, `N_required`·`N_final`·Δ를 **확정하지
않는다.** 유리한 시나리오 하나를 골라 권고하지도 않는다.
"""
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from .bootstrap import paired_cluster_bootstrap, verdict_against_delta
from .summary import summarise
from .schema import Adjudication, Ranking, ValidationError

# 비교하는 두 이름. **같은 후보 집합에서의 조건부 재정렬 효과**를 잰다 —
# 후보 생성이 다르면 그것은 작업 전체 효과이고 다른 질문이다(paired.py).
METHOD = "aida"
BASELINE = "iou_mismatch"

# 규약이 95% 구간을 쓴다(bootstrap.py의 0.025/0.975). **여기서 바꿀 수 없다** —
# 시나리오의 `alpha`는 그 사실을 적어 두는 칸이지 조절 손잡이가 아니다.
PROTOCOL_ALPHA = 0.05

# 판정 규칙은 `verdict_against_delta`가 정한다: `ci_low > Δ`이면 "성공".
# 양측 95% 구간의 아래끝을 쓰므로 **한쪽 방향으로는 유의수준이 α/2 = 0.025**다.
# 귀무(두 방법이 같음)에서 검정력이 α가 아니라 α/2 근처로 나오는 이유다.
ONE_SIDED_ALPHA = PROTOCOL_ALPHA / 2

# 값의 근거가 어디까지인지. **근거 없는 값을 공식 결론에 쓰지 않으려는 것이다.**
SOURCES = (
    "measured_development",            # 개발 데이터에서 실측
    "timing_pilot",                    # timing1~5에서 관측
    "business_assumption",             # 사업적 판단 — 사용자가 정한다
    "unsupported_sensitivity_example",  # 근거 없음. 민감도 축으로만 쓴다
    # 아래 둘은 **가정이 아니다.** 넷 중 하나로 억지로 분류하면 규약이 고정한
    # 값이 "사업 가정"처럼 보이거나, 반복 수가 "근거 없는 값"처럼 보인다.
    "protocol_fixed",                  # 평가 규약이 고정한 값 (α, 판정 규칙)
    "simulation_setting",              # 반복 수·씨앗 — 정밀도만 바꾼다
)
UNSUPPORTED = "unsupported_sensitivity_example"

# 반복이 적으면 검정력 추정의 몬테카를로 오차가 커서 **판정을 말할 수 없다.**
# 0.80 근처에서 SE ≈ sqrt(0.8×0.2/R)이므로 R=200이면 ±0.028이다.
# **근거가 약한 운영 기준이다** — 넘었다고 정확한 것이 아니라, 못 넘으면
# 공식 판정을 막으려는 선이다.
MIN_OFFICIAL_ITERATIONS = 200
# 재표집이 적으면 구간 끝이 거칠어 `ci_low > Δ`가 흔들린다.
MIN_OFFICIAL_BOOTSTRAP = 400


@dataclass(frozen=True)
class PlanningScenario:
    """**계획 가정 한 벌.** 값마다 근거를 같이 적는다.

    근거를 안 적은 값은 거부한다. 하나라도 `unsupported_sensitivity_example`이면
    그 시나리오는 `official=False`가 되어 공식 결론에 못 쓴다.
    """
    name: str
    dataset_count: int
    candidates_per_dataset: int          # 후보 풀. 검수 예산 N보다 커야 한다
    images_per_dataset: int
    candidates_per_image: dict[str, float]        # 후보 수 → 비중
    duplicates_per_unique_error: dict[str, float]  # 한 오류를 가리키는 후보 수
    error_prevalence: float              # 후보 중 실제 오류 비율
    image_error_concentration: float     # 0이면 고르게, 클수록 몇 이미지에 몰림
    aida_ranking_strength: float         # 오류를 위로 올리는 힘 (0이면 무작위)
    baseline_ranking_strength: float
    hold_rate: float
    delta: float | None                  # **미정이면 None.** 판정하지 않는다
    alpha: float
    target_power: float | None           # **미정이면 None**
    iterations: int                      # 몬테카를로 복제 수
    bootstrap_iterations: int
    random_seed: int
    sources: dict[str, str] = field(default_factory=dict)
    note: str = ""

    @property
    def unsupported_fields(self) -> list[str]:
        return sorted(k for k, v in self.sources.items() if v == UNSUPPORTED)

    @property
    def official(self) -> bool:
        """근거 없는 값이 하나라도 있으면 공식 결론에 쓰지 않는다."""
        return not self.unsupported_fields

    @property
    def delta_status(self) -> str:
        return "undetermined" if self.delta is None else "chosen_by_user"

    @property
    def target_power_status(self) -> str:
        return "undetermined" if self.target_power is None else "chosen_by_user"

    def as_dict(self) -> dict:
        return {"name": self.name, "dataset_count": self.dataset_count,
                "candidates_per_dataset": self.candidates_per_dataset,
                "images_per_dataset": self.images_per_dataset,
                "error_prevalence": self.error_prevalence,
                "image_error_concentration": self.image_error_concentration,
                "aida_ranking_strength": self.aida_ranking_strength,
                "baseline_ranking_strength": self.baseline_ranking_strength,
                "hold_rate": self.hold_rate, "delta": self.delta,
                "delta_status": self.delta_status,
                "target_power": self.target_power,
                "target_power_status": self.target_power_status,
                "official": self.official,
                "unsupported_fields": self.unsupported_fields,
                "note": self.note}


# ── 검증 ─────────────────────────────────────────────────────────────────────

# **값마다 근거를 적는다.** 하나라도 빠지면 시나리오를 거부한다.
REQUIRED_SOURCE_FIELDS = (
    "dataset_count", "candidates_per_dataset", "images_per_dataset",
    "candidates_per_image", "duplicates_per_unique_error", "error_prevalence",
    "image_error_concentration", "aida_ranking_strength",
    "baseline_ranking_strength", "hold_rate", "delta", "alpha",
    "target_power", "iterations", "bootstrap_iterations", "random_seed",
)


def _rate(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name}는 수여야 한다: {value!r}")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValidationError(f"{name}는 0과 1 사이다: {value!r}")
    return float(value)


def _count(value, name: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{name}는 정수여야 한다: {value!r}")
    if value < minimum:
        raise ValidationError(f"{name}는 {minimum} 이상이다: {value}")
    return value


def _distribution(raw, name: str) -> dict[int, float]:
    """{"1": 0.6, "2": 0.4} → {1: 0.6, 2: 0.4}. **합이 0이면 거부한다.**"""
    if not isinstance(raw, dict) or not raw:
        raise ValidationError(f"{name}는 비어 있으면 안 된다: {raw!r}")
    out: dict[int, float] = {}
    for key, weight in raw.items():
        try:
            size = int(key)
        except (TypeError, ValueError):
            raise ValidationError(f"{name}의 열쇠는 정수여야 한다: {key!r}")
        if size < 1:
            raise ValidationError(f"{name}의 열쇠는 1 이상이다: {size}")
        if (isinstance(weight, bool) or not isinstance(weight, (int, float))
                or not math.isfinite(weight) or weight < 0):
            raise ValidationError(f"{name}의 비중이 이상하다: {weight!r}")
        out[size] = float(weight)
    if sum(out.values()) <= 0:
        raise ValidationError(f"{name}의 비중 합이 0이다")
    return out


def validate_scenario(s: PlanningScenario) -> None:
    """**틀린 가정을 그럴듯한 숫자로 만들지 않는다.**"""
    if not isinstance(s.name, str) or not s.name.strip():
        raise ValidationError("시나리오 이름이 비어 있다")
    _count(s.dataset_count, "dataset_count")
    _count(s.candidates_per_dataset, "candidates_per_dataset")
    _count(s.images_per_dataset, "images_per_dataset")
    _count(s.iterations, "iterations")
    _count(s.bootstrap_iterations, "bootstrap_iterations")
    if isinstance(s.random_seed, bool) or not isinstance(s.random_seed, int):
        raise ValidationError(f"random_seed는 정수여야 한다: {s.random_seed!r}")

    _distribution(s.candidates_per_image, "candidates_per_image")
    _distribution(s.duplicates_per_unique_error, "duplicates_per_unique_error")
    _rate(s.error_prevalence, "error_prevalence")
    _rate(s.image_error_concentration, "image_error_concentration")
    _rate(s.hold_rate, "hold_rate")

    for name in ("aida_ranking_strength", "baseline_ranking_strength"):
        value = getattr(s, name)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0):
            raise ValidationError(f"{name}는 0 이상의 유한한 수다: {value!r}")

    if s.delta is not None:
        if (isinstance(s.delta, bool) or not isinstance(s.delta, (int, float))
                or not math.isfinite(s.delta)):
            raise ValidationError(f"delta가 이상하다: {s.delta!r}")
    if s.target_power is not None:
        _rate(s.target_power, "target_power")

    # **alpha는 조절 손잡이가 아니다.** 규약이 95% 구간을 쓰고 있고, 그것을
    # 바꾸려면 bootstrap.py의 분위수를 바꿔야 한다. 시나리오에서 다른 값을
    # 적어 두면 "그 값으로 계산했다"는 착각이 생긴다.
    if abs(float(s.alpha) - PROTOCOL_ALPHA) > 1e-12:
        raise ValidationError(
            f"alpha는 규약이 고정한 {PROTOCOL_ALPHA}다 (bootstrap.py의 95% 구간). "
            f"{s.alpha!r}로 계산하려면 규약부터 바꿔야 한다.")

    # **말없이 깎지 않는다.** 오류를 (1 − 몰림) 비율의 이미지에만 두므로 그 안의
    # 비율은 `오류 비율 ÷ (1 − 몰림)`이다. 이것이 1을 넘으면 만들 수 없는데,
    # 처음에는 `min(1, …)`로 잘라서 오류 비율 0.6·몰림 0.5를 넣으면 실제로는
    # 약 0.5가 만들어졌다. 시나리오에 적힌 값과 계산된 값이 달라진다.
    if s.error_prevalence > (1.0 - s.image_error_concentration) + 1e-12:
        raise ValidationError(
            f"오류 비율 {s.error_prevalence}를 몰림 {s.image_error_concentration}로 "
            "만들 수 없다 — 오류를 둘 이미지 비율(1 − 몰림)보다 오류 비율이 크다.")

    if s.candidates_per_dataset < s.images_per_dataset:
        raise ValidationError(
            f"후보({s.candidates_per_dataset})가 이미지({s.images_per_dataset})보다 "
            "적다. 이미지마다 후보가 하나는 있어야 묶음이 뜻을 갖는다.")

    missing = [f for f in REQUIRED_SOURCE_FIELDS if f not in s.sources]
    if missing:
        raise ValidationError(f"근거를 안 적은 값이 있다: {missing}")
    bad = {k: v for k, v in s.sources.items() if v not in SOURCES}
    if bad:
        raise ValidationError(f"모르는 근거 표시다: {bad} (쓸 수 있는 것: {SOURCES})")


def scenario_from_dict(raw: dict) -> PlanningScenario:
    known = set(PlanningScenario.__dataclass_fields__)
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ValidationError(f"모르는 항목이다: {unknown}")
    s = PlanningScenario(**raw)
    validate_scenario(s)
    return s


def load_scenarios(path: str | Path) -> list[PlanningScenario]:
    """버전 관리되는 시나리오 파일을 읽는다."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw["scenarios"] if isinstance(raw, dict) else raw
    return [scenario_from_dict(r) for r in rows]


# ── 순위 품질 — 강도와 짝 비교 확률 ──────────────────────────────────────────
#
# 점수는 `U(0,1) + 강도 × [오류]`로 만든다. 강도 숫자만 보면 무엇을 가정했는지
# 안 보인다 — **강도 1.0은 모든 오류를 모든 정상 후보보다 위에 두는 완벽한
# 순위**다. 처음 시나리오 파일에 AIDA 1.0 / 기준선 0.5를 넣었다가 그것을 뒤늦게
# 알아챘다. 그래서 가정은 **짝 비교 확률(AUC)** 로 적고 강도는 거기서 계산한다.
#
#     AUC = P(오류 후보 점수 > 정상 후보 점수)
#         = 1 − (1 − 강도)² / 2        (0 ≤ 강도 ≤ 1)
#
# AUC 0.5는 무작위, 1.0은 완벽이다.

def auc_from_strength(strength: float) -> float:
    """강도 → 짝 비교 확률. 강도가 1 이상이면 완벽(1.0)이다."""
    if (isinstance(strength, bool) or not isinstance(strength, (int, float))
            or not math.isfinite(strength) or strength < 0):
        raise ValidationError(f"강도는 0 이상의 유한한 수다: {strength!r}")
    if strength >= 1.0:
        return 1.0
    return 1.0 - (1.0 - strength) ** 2 / 2.0


def strength_from_auc(auc: float) -> float:
    """짝 비교 확률 → 강도. **0.5 미만은 거부한다** — 오류를 아래로 미는 순위다."""
    if (isinstance(auc, bool) or not isinstance(auc, (int, float))
            or not math.isfinite(auc) or not 0.5 <= auc <= 1.0):
        raise ValidationError(f"AUC는 0.5와 1 사이다: {auc!r}")
    return 1.0 - math.sqrt(2.0 * (1.0 - auc))


# ── 가상 판정 기록 만들기 ────────────────────────────────────────────────────
#
# **여기서 만드는 것은 입력뿐이다.** 순위·중복 제거·예산·재표집·동등 가중은
# 전부 evaluation의 실제 함수가 한다.

def _draw(dist: dict[int, float], rng: random.Random) -> int:
    sizes = sorted(dist)
    weights = [dist[s] for s in sizes]
    return rng.choices(sizes, weights=weights, k=1)[0]


def _image_sizes(dist: dict[int, float], images: int, target: int,
                 rng: random.Random) -> list[int]:
    """이미지마다 후보를 몇 개 둘 것인가. 합이 후보 풀 크기가 되게 맞춘다."""
    sizes = [max(1, _draw(dist, rng)) for _ in range(images)]
    # 분포로 뽑은 합이 목표와 어긋난다. **이미지 수를 고정하고 크기로 맞춘다** —
    # 이미지 수가 바뀌면 재표집 묶음 수가 바뀌어 구간이 달라진다.
    while sum(sizes) > target:
        big = max(range(len(sizes)), key=lambda i: sizes[i])
        if sizes[big] == 1:
            break                     # 더 줄일 수 없다
        sizes[big] -= 1
    while sum(sizes) < target:
        sizes[rng.randrange(len(sizes))] += 1
    return sizes


def build_world(scenario: PlanningScenario,
                rng: random.Random) -> tuple[list[Adjudication], list[Ranking]]:
    """가상의 판정 기록 한 벌.

    **판정은 방법과 무관한 사실이다**(schema.py). 그래서 후보를 만들 때 한 번
    정하고, 두 방법이 그 같은 사실을 공유한다 — 짝지음이 여기서 생긴다.

    중복은 **같은 이미지 안에서** 같은 `unique_error_id`를 나눠 갖게 만든다.
    실제로도 한 라벨을 여러 의심 유형이 동시에 집는 방식이라, 중복 제거가
    성과를 얼마나 깎는지가 이 값에 달려 있다.
    """
    adjudications: list[Adjudication] = []
    rankings: list[Ranking] = []
    # **분포는 한 번만 푼다.** 파일에서 읽으면 열쇠가 문자열이라 매번 바꾸면
    # 복제마다 같은 일을 수만 번 한다.
    image_dist = _distribution(scenario.candidates_per_image,
                               "candidates_per_image")
    dup_dist = _distribution(scenario.duplicates_per_unique_error,
                             "duplicates_per_unique_error")

    for d in range(scenario.dataset_count):
        dataset_id = f"ds{d + 1}"
        sizes = _image_sizes(image_dist, scenario.images_per_dataset,
                             scenario.candidates_per_dataset, rng)

        # 오류가 몇 이미지에 몰리는가. **가장자리 비율은 그대로 둔다** —
        # 몰릴수록 그 이미지 안의 비율이 올라가고 나머지는 0이 된다.
        concentration = scenario.image_error_concentration
        share = max(1e-9, 1.0 - concentration)
        bearing = [rng.random() < share for _ in sizes]
        if not any(bearing):
            bearing[rng.randrange(len(bearing))] = True
        rate = min(1.0, scenario.error_prevalence / share)

        error_seq = 0
        for i, size in enumerate(sizes):
            image_id = f"{dataset_id}_img{i:04d}"
            local_rate = rate if bearing[i] else 0.0
            is_error = [rng.random() < local_rate for _ in range(size)]

            # 오류 후보를 중복 묶음으로 나눈다 — 한 묶음이 한 고유 오류다.
            error_slots = [j for j, flag in enumerate(is_error) if flag]
            error_of: dict[int, str] = {}
            pos = 0
            while pos < len(error_slots):
                k = max(1, _draw(dup_dist, rng))
                error_seq += 1
                name = f"{dataset_id}_err{error_seq:05d}"
                for slot in error_slots[pos:pos + k]:
                    error_of[slot] = name
                pos += k

            for j in range(size):
                if scenario.hold_rate and rng.random() < scenario.hold_rate:
                    verdict = "hold"          # 보류는 예산을 쓰지만 성과가 아니다
                elif is_error[j]:
                    verdict = "hit"
                else:
                    verdict = "miss"
                row = Adjudication(
                    dataset_id=dataset_id, image_id=image_id,
                    candidate_id=f"c{j:03d}",
                    suspicion="simulated",
                    verdict=verdict,
                    unique_error_id=error_of.get(j))
                adjudications.append(row)

                # **점수는 방법마다 다르다.** 오류를 얼마나 위로 올리는가가
                # 그 방법의 순위 품질이다. 잡음은 서로 독립이다.
                for method, strength in (
                        (METHOD, scenario.aida_ranking_strength),
                        (BASELINE, scenario.baseline_ranking_strength)):
                    severity = rng.random() + (strength if is_error[j] else 0.0)
                    rankings.append(Ranking(method=method,
                                            candidate_key=row.key,
                                            severity=severity))
    return adjudications, rankings


# ── 검정력 ───────────────────────────────────────────────────────────────────

def _check_delta(value) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value)):
        raise ValidationError(f"delta가 이상하다: {value!r}")
    return float(value)


def simulate_power(scenario: PlanningScenario, budget: int,
                   iterations: int | None = None,
                   bootstrap_iterations: int | None = None,
                   seed: int | str | None = None,
                   deltas: list[float] | None = None) -> dict:
    """`budget`건을 검수할 때 Δ를 잡아낼 확률.

    한 복제마다 세상을 새로 만들고 **실제 집계 경로**를 그대로 돌린다
    (`paired_cluster_bootstrap` → `verdict_against_delta`). "성공"이 나온 비율이
    검정력이다.

    **Δ 여러 개를 같은 복제로 본다.** 복제마다 구간은 하나이고, 그 구간을 Δ마다
    `verdict_against_delta`에 넣기만 하면 된다. Δ마다 세상을 따로 만들면 비용이
    Δ 수만큼 늘고, 안끼리 비교할 때 몬테카를로 잡음이 섞인다.

    **Δ가 없으면 검정력을 내지 않는다.** 규약이 Δ 없이는 판정하지 않기 때문이고
    (`verdict_against_delta`), 여기서 Δ를 지어내면 그건 기준이 아니라 사후
    설명이 된다.

    돌려주는 값에 **몬테카를로 표준오차**를 같이 담는다. 0.80과 0.79의 차이가
    반복 수 때문일 수 있다.
    """
    validate_scenario(scenario)
    _count(budget, "budget", minimum=1)
    reps = scenario.iterations if iterations is None else iterations
    boots = (scenario.bootstrap_iterations if bootstrap_iterations is None
             else bootstrap_iterations)
    _count(reps, "iterations")
    _count(boots, "bootstrap_iterations")
    if deltas is None:
        deltas = [] if scenario.delta is None else [scenario.delta]
    deltas = [_check_delta(d) for d in deltas]
    use_seed = scenario.random_seed if seed is None else seed

    base = {
        "scenario": scenario.name, "budget": budget,
        "dataset_count": scenario.dataset_count,
        "candidates_per_dataset": scenario.candidates_per_dataset,
        "iterations": reps, "bootstrap_iterations": boots,
        "seed": use_seed, "deltas": deltas,
        "delta_status": "undetermined" if not deltas else "scenario_input",
        "official_scenario": scenario.official,
        "unsupported_fields": scenario.unsupported_fields,
        "one_sided_alpha": ONE_SIDED_ALPHA,
    }
    if not deltas:
        return {**base, "status": "delta_undetermined", "by_delta": [],
                "power": None, "monte_carlo_se": None,
                "reason": ("Δ가 없으면 성공·실패를 판정하지 않는다. "
                           "검정력은 '어떤 Δ를 잡아낼 확률'이라 Δ 없이는 "
                           "말이 되지 않는다.")}
    if budget > scenario.candidates_per_dataset:
        return {**base, "status": "budget_exceeds_pool", "by_delta": [],
                "power": None, "monte_carlo_se": None,
                "reason": (f"검수 예산 {budget}이 후보 풀 "
                           f"{scenario.candidates_per_dataset}보다 크다. "
                           "없는 후보를 검수할 수는 없다.")}

    root = random.Random(use_seed)
    successes = [0] * len(deltas)
    differences: list[float] = []
    method_yield: list[float] = []
    baseline_yield: list[float] = []
    pool_errors: list[float] = []
    for _ in range(reps):
        rng = random.Random(root.getrandbits(64))
        adjudications, rankings = build_world(scenario, rng)
        result = paired_cluster_bootstrap(
            adjudications, rankings, METHOD, BASELINE, budget=budget,
            iterations=boots, seed=root.getrandbits(32))
        differences.append(result["observed_difference"])
        for i, delta in enumerate(deltas):
            if verdict_against_delta(result, delta) == "성공":
                successes[i] += 1
        # 해석용: 데이터셋당 고유 오류를 방법마다 몇 개 찾는가. **실제 집계
        # 함수로 센다.**
        per_ds_m, per_ds_b = [], []
        for d in range(scenario.dataset_count):
            name = f"ds{d + 1}"
            facts = [a for a in adjudications if a.dataset_id == name]
            keys = {a.key for a in facts}
            ranks = [r for r in rankings if r.candidate_key in keys]
            per_ds_m.append(summarise(facts, ranks, METHOD, budget).unique_error_yield)
            per_ds_b.append(summarise(facts, ranks, BASELINE, budget).unique_error_yield)
        method_yield.append(sum(per_ds_m) / len(per_ds_m))
        baseline_yield.append(sum(per_ds_b) / len(per_ds_b))
        # 풀 전체에 **실제로 만들어진** 고유 오류 수(데이터셋 평균). 설정한 중복
        # 분포가 아니라 이것을 본다 — 이미지 대부분이 후보 1건이면 중복 묶음이
        # 만들어질 자리가 없어, 설정값으로 계산한 기대 오류 수가 틀린다.
        pool_errors.append(len({(a.dataset_id, a.unique_error_id)
                                for a in adjudications if a.unique_error_id})
                           / scenario.dataset_count)

    by_delta = []
    for delta, hit in zip(deltas, successes):
        power = hit / reps
        by_delta.append({"delta": delta, "successes": hit, "power": power,
                         "monte_carlo_se": math.sqrt(power * (1.0 - power) / reps)})

    enough = reps >= MIN_OFFICIAL_ITERATIONS and boots >= MIN_OFFICIAL_BOOTSTRAP
    return {
        **base,
        "status": "ok" if enough else "too_few_iterations",
        "by_delta": by_delta,
        "power": by_delta[0]["power"],
        "monte_carlo_se": by_delta[0]["monte_carlo_se"],
        "mean_observed_difference": sum(differences) / reps,
        "min_observed_difference": min(differences),
        "max_observed_difference": max(differences),
        "mean_method_unique_errors": sum(method_yield) / reps,
        "mean_baseline_unique_errors": sum(baseline_yield) / reps,
        # 보류 여부와 무관하게 오류로 만들어진 것의 수다. 보류된 오류는 성과로
        # 안 세므로 찾을 수 있는 최대치는 이보다 작을 수 있다.
        "mean_pool_unique_errors": sum(pool_errors) / reps,
        "official_iterations": enough,
        "iteration_floor": {"iterations": MIN_OFFICIAL_ITERATIONS,
                            "bootstrap_iterations": MIN_OFFICIAL_BOOTSTRAP},
        "reason": ("" if enough else
                   f"반복이 모자라 공식 판정을 막는다 (복제 {reps} / "
                   f"재표집 {boots}, 최소 {MIN_OFFICIAL_ITERATIONS} / "
                   f"{MIN_OFFICIAL_BOOTSTRAP}). 숫자는 참고로만 본다."),
        "note": ("**판정 규칙은 `ci_low > Δ`다**(verdict_against_delta). 양측 "
                 "95% 구간의 아래끝이므로 한쪽 방향 유의수준은 α/2 = "
                 f"{ONE_SIDED_ALPHA}다. 두 방법이 같으면 검정력이 그 근처로 "
                 "나오는 것이 정상이다."),
    }


# 목표 검정력은 **사용자가 정하지 않았다.** 확정값처럼 쓰지 않고 두 값을
# 나란히 보여 주기만 한다.
COMPARISON_POWERS = (0.80, 0.90)


def power_against_targets(power: float | None,
                          targets=COMPARISON_POWERS) -> dict[str, bool | None]:
    """0.80·0.90을 **비교 시나리오로만** 본다. 통과 도장이 아니다."""
    return {f"meets_{t:.2f}": (None if power is None else power >= t)
            for t in targets}


def delta_options(budget: int) -> list[dict]:
    """사전 결정용 Δ 안. **고르지 않는다 — 늘어놓기만 한다.**

    `activity.delta_scenarios`와 같은 안을 쓴다(한 곳에서 정의). ROI 안은 값이
    없어 검정력을 계산하지 않는다.
    """
    from .activity import delta_scenarios
    return [dict(row, delta_status="undetermined")
            for row in delta_scenarios(budget)]
