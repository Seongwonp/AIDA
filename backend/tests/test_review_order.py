"""재검수 목록의 순서 규칙 (docs/21 AN·AO).

**어긋난 자에서는 목록의 맨 위가 아래보다 나빴다.** 심각도만으로 정렬하면
유형 신뢰도 두 벌(present/noise)이 겹쳐서, 진단이 "계통적이지 않다"고 판정한
유형이 맨 위에 앉는다 — `class_mismatch`의 noise 값 0.990이 `width`의 present
값 0.820보다 높다. 실측으로 상위 10위의 61%가 그런 유형이었고, 조건 29개 중
26개에서 1위가 그랬다.

고친 뒤 어긋난 자 5대에서 @5 정밀도가 평균 +0.42 올랐다(시드 3개, 관측 15개
전부 양수).

**여기서 고정하는 것은 규칙이지 수치가 아니다.** 수치는 GPU가 필요하고 CI에서
못 잰다. 규칙이 조용히 뒤집히면 그 수치도 같이 사라지므로, 규칙을 검사로 박아둔다.
"""
import sys
from pathlib import Path

import pytest

EXPERIMENT = Path(__file__).resolve().parents[2] / "experiment"
if str(EXPERIMENT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT))


@pytest.fixture(scope="module")
def L():
    return pytest.importorskip(
        "label_diagnosis", reason="experiment/ 코드를 못 읽는 환경")


def finding(L, suspicion: str, severity: float, index: int = 0):
    return L.BoxFinding(image="a.png", label_index=index, suspicion=suspicion,
                        severity=severity, detail="", box=[0, 0, 1, 1],
                        raw_signal=severity, confidence=0.9)


def summary_of(ratios: dict) -> dict:
    return {"by_type": [{"suspicion": k, "ratio": v} for k, v in ratios.items()]}


# --- present_types: 절대 문턱과 상대 문턱 (AO) --------------------------------

def test_absolute_threshold_wins_when_it_finds_something(L):
    """맞는 자에서는 절대 문턱이 이미 잘 잡는다. 건드리면 손해였다(−0.038~−0.092)."""
    s = summary_of({"width": 0.30, "missing": 0.05})
    assert L.present_types(s) == {"width"}


def test_relative_threshold_kicks_in_only_when_absolute_finds_nothing(L):
    """자가 크게 어긋나면 지목이 흩어져 어느 유형도 문턱을 못 넘는다.

    KITTI 자로 COCO를 진단하면 최대 유형 비율이 0.103~0.112로 문턱(0.12)을
    아슬아슬하게 못 넘어 조건 26개 중 26개에서 **하나도 안 잡혔다.** 그러면
    순서 처방이 통째로 no-op이 된다.
    """
    s = summary_of({"width": 0.103, "missing": 0.02, "scale": 0.01})
    assert L.present_types(s) == {"width"}


def test_flat_distribution_still_finds_nothing(L):
    """전부 고만고만하면 대표 유형이 없는 게 맞다. 아무거나 올리면 안 된다."""
    s = summary_of({"a": 0.04, "b": 0.035, "c": 0.03})
    assert L.present_types(s) == set()


def test_relative_threshold_has_a_floor(L):
    """중앙값의 2배여도 절대 문턱의 절반은 넘어야 한다 — 잡음까지 승격되면 안 된다."""
    s = summary_of({"width": 0.05, "missing": 0.01, "scale": 0.01})
    assert L.present_types(s) == set()


# --- review_order: 계통적 유형이 먼저 (AN) ------------------------------------

def test_systematic_type_outranks_higher_severity_noise(L):
    """이게 AN의 핵심이다.

    class_mismatch(비계통, 0.95)가 width(계통, 0.30)를 눌러 맨 위에 앉는 것이
    바로 고친 결함이다.
    """
    f = [finding(L, "class_mismatch", 0.95, 1), finding(L, "width", 0.30, 0)]
    order = L.review_order(f, summary_of({"width": 0.30, "class_mismatch": 0.01}))
    assert [x.suspicion for x in order] == ["width", "class_mismatch"]


def test_severity_still_orders_within_a_type(L):
    """유형 안에서는 심각도가 그대로 순서를 정한다."""
    f = [finding(L, "width", 0.20, 0), finding(L, "width", 0.80, 1)]
    order = L.review_order(f, summary_of({"width": 0.30}))
    assert [x.severity for x in order] == [0.80, 0.20]


def test_severity_values_are_not_modified(L):
    """값은 화면과 CSV에 나가고 유형 안에서는 여전히 쓸모가 있다.

    한때 심각도에 1.0을 더해 앞으로 보내는 방식을 썼는데, 그러면 화면에 1.53
    같은 값이 나간다. 순서만 바꾸고 값은 두는 것이 지금 규칙이다.
    """
    f = [finding(L, "class_mismatch", 0.95, 1), finding(L, "width", 0.30, 0)]
    order = L.review_order(f, summary_of({"width": 0.30, "class_mismatch": 0.01}))
    assert sorted(x.severity for x in order) == [0.30, 0.95]
    assert all(0.0 <= x.severity <= 1.0 for x in order)


def test_nothing_systematic_means_plain_severity_order(L):
    """계통적 유형이 하나도 없으면 예전과 같이 심각도 순이다."""
    f = [finding(L, "a", 0.20, 0), finding(L, "b", 0.80, 1)]
    order = L.review_order(f, summary_of({"a": 0.04, "b": 0.035}))
    assert [x.severity for x in order] == [0.80, 0.20]


def test_diagnose_labels_uses_review_order(L):
    """제품 경로가 실제로 이 규칙을 쓰는지.

    규칙만 있고 안 쓰면 아무 소용이 없다. 실제로 build_result가 순수 심각도
    정렬을 쓰고 있었던 것이 AN의 결함이었다.
    """
    src = (EXPERIMENT / "diagnose_labels.py").read_text(encoding="utf-8")
    assert "review_order(findings, summary)" in src, \
        "build_result가 review_order를 안 쓴다 — AN 처방이 빠졌다"
    assert "sorted(findings, key=lambda f: -f.severity)" not in src, \
        "순수 심각도 정렬이 되살아났다"


# --- 순서를 무엇으로 정했는지 화면에 내보내는가 (docs/21 AO) -------------------
#
# 상대 문턱으로 물러난 경우는 **순서를 정한 규칙 자체가 다른데** 지금까지 그
# 사실이 어디에도 안 나왔다. 이 프로젝트는 "어느 자로 쟀는지 숨기지 않는다"를
# 지켜왔고 이것도 같은 종류다.

def test_order_basis_absolute_when_threshold_catches(L):
    assert L.order_basis(summary_of({"width": 0.30, "missing": 0.05})) == "absolute"


def test_order_basis_relative_when_absolute_is_empty(L):
    """자가 어긋나면 분포가 납작해져 절대 문턱이 통째로 빈다.

    실측에서 KITTI 자로 COCO를 진단하면 최대 유형 비율이 0.103~0.112로
    문턱(0.12)을 아슬아슬하게 못 넘었다.
    """
    basis = L.order_basis(summary_of({"width": 0.10, "missing": 0.02, "scale": 0.01}))
    assert basis == "relative"


def test_order_basis_none_when_flat(L):
    """상대 문턱도 못 잡을 만큼 고르면 순수 심각도 순이다."""
    assert L.order_basis(summary_of({"a": 0.05, "b": 0.05, "c": 0.05})) == "none"
    assert L.order_basis({"by_type": []}) == "none"


def test_order_basis_agrees_with_present_types(L):
    """두 함수가 어긋나면 화면이 순서와 다른 말을 하게 된다."""
    for ratios in ({"width": 0.30}, {"width": 0.10, "b": 0.02, "c": 0.01},
                   {"a": 0.05, "b": 0.05, "c": 0.05}):
        s = summary_of(ratios)
        assert (L.order_basis(s) == "none") == (not L.present_types(s))


def test_diagnose_labels_reports_order_basis(L):
    """제품 경로가 실제로 그 값을 결과에 담는지."""
    src = (EXPERIMENT / "diagnose_labels.py").read_text(encoding="utf-8")
    assert 'summary["order_basis"] = order_basis(summary)' in src, \
        "진단 결과가 순서 근거를 안 담는다 — 화면이 알 방법이 없다"


# --- 측정 스크립트가 기준선을 제품 코드에서 물려받지 않는가 (docs/21 AT·AU) ----
#
# 이틀 새 두 번 같은 일이 났다. 처방을 제품에 넣으면, 그 제품 함수를 "처방 전"
# 으로 쓰던 측정 스크립트는 조용히 **같은 것을 두 번 재게 된다.** 둘 다 결과가
# 전부 +0.000으로 나와서 겨우 알아챘다 — 처방이 안 듣는 줄 알았다.
#
# 수치는 CI에서 못 재지만 "기준선을 못 박았는가"는 잴 수 있다.

def test_shipped_present_types_is_not_absolute_only(L):
    """제품 함수에 후퇴가 들어 있다 — 그래서 기준선으로 쓰면 안 된다."""
    flat = summary_of({"width": 0.10, "missing": 0.02, "scale": 0.01})
    assert not L._absolute_present_types(flat), "절대 문턱은 이걸 못 잡아야 한다"
    assert L.present_types(flat), "제품 함수는 후퇴로 잡아야 한다"


def test_relative_threshold_pins_its_own_baseline(L):
    """AO 측정이 '처방 전'을 절대 문턱으로 직접 계산하는가."""
    src = (EXPERIMENT / "relative_threshold.py").read_text(encoding="utf-8")
    assert "L.present_types = absolute_present_types" in src, \
        "기준선을 제품의 present_types에서 물려받으면 같은 것을 두 번 잰다"
    assert "empty_abs += (not L.present_types(summary))" not in src, \
        "'절대 문턱이 빈 조건' 세는 곳도 제품 함수를 쓰면 안 된다"


# --- 순서가 오탐을 좇고 있을 위험을 말하는가 (docs/21 BB) ---------------------
#
# 후퇴가 기하 유형만 올렸을 때가 위험한 모습이다. 실측(431칸): 구조적 유형이
# 올라간 150칸은 손해 0건, 기하만 올라간 281칸은 47%가 손해였다.
#
# **판정만 하고 순서는 안 바꾼다.** 여기 쓰인 자와 조건은 전부 오류를 넣어 만든
# 것이라 순서를 바꿀 근거로는 아직 부족하다.

def test_order_risk_only_when_fallback_promoted_geometry(L):
    """후퇴 + 기하 유형만 → 위험."""
    s = summary_of({"width": 0.10, "height": 0.02, "scale": 0.01})
    assert L.order_basis(s) == "relative"
    assert L.order_risk(s) is True


def test_order_risk_false_when_structural_promoted(L):
    """구조적 유형이 올라갔으면 위험이 아니다 — 실측 150칸에 예외가 없었다."""
    s = summary_of({"missing": 0.10, "width": 0.02, "scale": 0.01})
    assert L.order_basis(s) == "relative"
    assert L.order_risk(s) is False


def test_order_risk_false_without_fallback(L):
    """절대 문턱이 잡았으면 후퇴 자체가 없다."""
    s = summary_of({"width": 0.30, "missing": 0.05})
    assert L.order_basis(s) == "absolute"
    assert L.order_risk(s) is False


def test_order_risk_false_when_nothing_promoted(L):
    s = summary_of({"a": 0.05, "b": 0.05, "c": 0.05})
    assert L.order_basis(s) == "none"
    assert L.order_risk(s) is False


def test_structural_set_matches_product_types(L):
    """구조적 유형 목록이 진단이 실제로 내는 유형 이름과 맞는가."""
    assert L.STRUCTURAL_SUSPICIONS == {"missing", "duplicate", "class_mismatch"}
    assert L.STRUCTURAL_SUSPICIONS <= set(L.TYPE_RELIABILITY_PRESENT)


def test_diagnose_labels_reports_order_risk(L):
    src = (EXPERIMENT / "diagnose_labels.py").read_text(encoding="utf-8")
    assert 'summary["order_risk"] = order_risk(summary)' in src, \
        "진단 결과가 순서 위험을 안 담는다 — 화면이 알 방법이 없다"
