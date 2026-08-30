"""라벨 단위 진단 로직 — 박스 하나하나를 대조해 "왜 의심스러운지"를 만든다.

기존 diagnose_upload.py와의 차이가 이 모듈의 존재 이유다:
- diagnose_upload.py: 데이터셋 전체 성능 숫자(precision/recall) 하나를 성능
  패턴 DB와 비교 → "이 데이터셋에는 회전 오류가 있는 것 같다" 수준의 추정.
  precision/recall 2차원만으로 8개 오류 유형을 구분해야 해서 판별력이
  근본적으로 부족하다(docs/21 C 실행 결과의 missing_30 오진 사례 참고).
- 이 모듈: clean 모델의 예측 박스와 고객 라벨을 1:1로 대조 → "3번 이미지의
  2번 박스가 예측보다 28% 작다" 수준의 박스 단위 의심 목록. AIDA가 원래
  약속한 "재검수 우선순위 목록" 그 자체이고, 유형 판별도 성능 숫자가 아니라
  기하학적 증거로 하므로 훨씬 직접적이다.

GPU/모델 의존이 없는 순수 함수만 둔다 — 실제 추론은 diagnose_labels.py가
맡고, 여기 로직은 테스트로 검증한다(tests/test_label_diagnosis.py).
"""
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

# error_injector.py와 같은 좌표 규약 (픽셀 기준 left, top, right, bottom)
Box = tuple[float, float, float, float]

# ── 임계값 ──────────────────────────────────────────────────────────────────
# 주입 오류 강도가 15%/30%이고 모델 예측 자체도 몇 %는 흔들리므로, 그 사이인
# 12%를 크기 오류 기준으로 잡는다. 중심점 이동도 같은 이유로 10%(주입 강도
# 15%의 2/3). 이 값들은 evaluate_label_diagnosis.py로 27개 조건 전체에 대해
# 정확도를 재면서 조정한 결과다 — 바꾸려면 그 스크립트를 다시 돌려볼 것.
SIZE_DEVIATION_THRESHOLD = 0.12
CENTER_SHIFT_THRESHOLD = 0.10
# 예측과 라벨을 "같은 객체"로 볼 최소 IoU. 이보다 낮으면 아예 짝이 없는
# 것으로 보고 missing/spurious로 분류한다.
MATCH_IOU_THRESHOLD = 0.4
# 이미 짝지어진 예측과 이만큼 겹치는 여분 라벨은 중복 라벨로 본다.
DUPLICATE_IOU_THRESHOLD = 0.5
# 라벨이 없는 자리에서 모델이 이 정도 확신을 보이면 "누락된 라벨" 후보로 본다.
# 낮추면 모델의 오탐까지 누락으로 잡아 오진이 늘어난다.
#
# 처음엔 0.5로 잡았는데, 누락은 8개 유형 중 정밀도가 꼴찌였다(존재해도 71~83%).
# collect_missing_features.py로 570건의 누락 의심을 실측해 원인을 찾아보니,
# 확신도 하나가 다른 어떤 맥락 신호(박스 크기, 화면 위치, 주변 라벨 밀도)보다
# 압도적으로 잘 갈랐다 — 진짜 누락은 확신도 중앙값 0.84, 오탐은 0.59.
# 0.5~0.7 구간은 사실상 오탐 구간이었다: 그 구간 239건 중 진짜는 79건뿐.
MISSING_CONFIDENCE_THRESHOLD = 0.70
# 이 예측이 기존 라벨에 이만큼 삼켜져 있으면 누락으로 보지 않는다.
# IoU와 다르다 — 작은 예측이 큰 라벨 안에 통째로 들어가면 IoU는 낮지만 이 값은
# 1.0이다. 이런 건 "라벨 없는 객체"가 아니라 이미 라벨된 객체를 두 번 잡았거나,
# 라벨된 차 뒤에 가려진 차다(KITTI는 심하게 가려진 차를 Car로 라벨링하지 않아
# 정상 탐지가 누락으로 오인된다). 확신도만으로는 이게 안 걸러진다.
MISSING_MAX_COVERED_RATIO = 0.7
# 클래스 불일치를 말하려면 모델이 자기 클래스를 이만큼은 확신해야 한다.
#
# 진단은 "라벨의 클래스가 틀렸다"와 "모델의 클래스 예측이 틀렸다"를 구분할
# 수단이 없다 — 둘 다 겉보기엔 같은 불일치다. 실측해보니 확신도가 그 둘을
# 거의 완벽하게 갈랐다(다중 클래스 299건 표본): 진짜 클래스 오기입은 확신도
# 중앙값 0.835인데 오탐은 0.546이었고, **오탐 48건이 전부 0.60 아래였다.**
# 겹침(IoU)은 전혀 갈라내지 못했다(0.881 vs 0.805).
#
# 문턱 아래면 아무 판정도 내리지 않는다. 근거 없이 다른 유형(누락·중복)으로
# 부르면 틀린 말을 하는 것이고, 침묵하는 편이 낫다.
CLASS_MISMATCH_CONFIDENCE_THRESHOLD = 0.60
# 한 유형의 의심이 전체 라벨의 이 비율을 넘으면 "계통적 오류"로 판정한다.
# clean의 최대 유형 비율(7.4% 실측)과 실제 오류 조건의 최대 유형 비율
# (26%+) 사이에 두되, 약한 오류(10% 주입)까지 놓치지 않도록 낮게 잡았다.
SYSTEMATIC_ERROR_RATIO = 0.12

# ── 심각도 계산 ─────────────────────────────────────────────────────────────
# severity는 재검수 목록의 정렬 키이므로 "이게 진짜 오류일 가능성"을 뜻해야
# 하고, 유형이 달라도 서로 비교 가능해야 한다. 유형별 원시 신호(누락은 확신도,
# 중복은 겹침, 크기는 변형률)는 단위도 범위도 달라서 그냥 쓰면 안 된다 —
# 실제로 초기 버전이 원시값을 그대로 써서 상위 10% 정밀도가 28.5%로 전체
# 평균(58.9%)보다 낮았다. 확신도 0.9대인 누락 의심이 목록 상단을 점령했는데
# 정작 누락은 유형별 정밀도가 27%로 가장 낮았기 때문이다.
#
# 그래서 두 가지를 곱한다:
#   1) 유형 신뢰도 — 그 유형이 얼마나 미더운지 (아래 실측 상수)
#   2) 신호 세기 — 임계값을 얼마나 넘었는지 0~1로 정규화
# 유형끼리는 신뢰도가 순서를 정하고, 같은 유형 안에서는 세기가 정한다.
#
# 유형 신뢰도는 evaluate_box_accuracy.py로 KITTI Car 26개 조건에서 실측한
# 유형별 정밀도다. **도메인이 바뀌면 재보정해야 한다.**
#
# 신뢰도는 "그 유형이 이 데이터셋의 대표 오류 유형으로 판정됐는가"에 따라 크게
# 갈린다. 하나의 전역 상수로는 **"이 유형이 얼마나 미더운가"와 "이 유형이
# 애초에 있기는 한가"를 뒤섞게 된다.** 실측이 이를 뚜렷하게 보여준다 —
# 누락 의심은 대표 유형일 때 82.9%(n=181)인데 아닐 때는 4.3%(n=445)로,
# 예전 전역 상수 27%는 성격이 전혀 다른 두 모집단을 평균낸 값이었다.
# (KITTI가 원거리·가려진 차를 라벨링하지 않아 모델의 정상 탐지가 "누락"으로
# 오인되는데, 그 오탐이 누락 없는 23개 조건에서 대량으로 나왔다.)
#
# 그래서 2단으로 나눈다. 데이터셋이 계통적으로 그 유형을 갖고 있다면
# "있기는 한가"는 해소됐으므로 높은 쪽을 쓴다.
#
# 가르는 기준은 "그 유형이 1등인가"가 아니라 **"계통적 임계값을 넘는가"**다.
# 처음엔 대표(1등) 유형만 승격시켰는데, 혼합 오류 조건(calibrate_mixed.py)으로
# 재보정해보니 **2차 유형도 실제로 존재하기만 하면 대표 유형만큼 미더웠다**:
#
#   유형            대표일 때        2차로 존재할 때
#   duplicate       97.9%(n=146)    100.0%(n=39)
#   translation_y   97.8%(n=181)     97.4%(n=39)
#   scale           93.8%(n=357)     93.5%(n=46)
#   height          86.9%(n=588)     83.9%(n=56)
#   width           82.6%(n=413)     80.0%(n=60)
#   missing         82.9%(n=181)     71.2%(n=59)
#
# 즉 신뢰도를 가르는 건 순위가 아니라 존재 여부였다. 1등만 승격시키면 두 번째
# 오류 유형이 노이즈 취급을 받아(누락의 경우 71.2%인데 4%로) 목록 바닥에
# 깔린다. 아래 값은 두 측정을 건수로 가중평균한 것이다.
TYPE_RELIABILITY_PRESENT = {
    "duplicate": 0.98,
    "translation_y": 0.98,
    "translation_x": 0.95,
    "scale": 0.94,
    "height": 0.87,
    "width": 0.82,
    # 누락 필터(확신도 0.70 + 삼켜짐 0.7) 적용 후 재측정: 대표일 때 100%(n=120),
    # 2차로 존재할 때 94.9%(n=39) → 합쳐 98.7%. 필터 전에는 82.9%/71.2%였다.
    "missing": 0.99,
    # 클래스 오기입. 확신도 문턱(0.60)을 통과한 것만 세면 실측 100%(n=171)인데,
    # 표본 수백 건짜리 100%를 "절대 안 틀린다"로 굳히지 않으려고 0.99로 둔다.
    # 다중 클래스 조건에서 잰 값이다 — 단일 클래스에서는 이 유형이 안 나온다.
    "class_mismatch": 0.99,
}
# 계통적 수준으로 존재하지 않을 때 = 사실상 모델 예측 흔들림에서 나온 오탐.
# 단일 유형 조건 26개에서 "그 유형이 주입되지 않았을 때"로 실측한 값이다.
TYPE_RELIABILITY_NOISE = {
    "duplicate": 0.69,
    "scale": 0.60,
    "height": 0.31,
    "translation_y": 0.21,
    "translation_x": 0.21,
    "width": 0.20,
    # 필터 적용 후 88.2%(n=15/17). 예전 값 0.04는 n=445 표본에서 나왔는데,
    # 그 445건이 대부분 KITTI 관행에서 오는 오탐이었고 필터가 그걸 걷어냈다.
    # **n=17은 다른 유형(n=55~478)에 비해 훨씬 작다** — 이 값은 근거가 얇다.
    # 다만 방향은 분명하다: 누락 없는 조건 8개에서 살아남은 의심이 640장 중
    # 2건뿐이라, 이 상수가 잘못돼도 영향받는 건수 자체가 거의 없다. 오히려
    # 0.04를 그대로 두면 계통적 임계값(12%)에 못 미치는 성긴 누락을 가진
    # 데이터셋에서 진짜 누락이 목록 바닥에 깔린다.
    "missing": 0.88,
    # 부재 시도 실측 100%지만 n=30으로 얇다. 확신도 문턱이 이미 걸러낸 뒤라
    # 두 단계가 갈리지 않는 유형이다.
    "class_mismatch": 0.99,
}
# 기하 의심(크기·이동)의 심각도에 예측 확신도를 얼마나 반영할지.
# 심각도는 원래 확신도를 아예 안 봤다 — 유형 신뢰도와 변형률만 봤다. 그런데
# 기하 의심 2936건을 재보니 확신도가 유형을 가리지 않고 가장 잘 갈랐다:
#
#   유형            진짜(중앙값)   오탐(중앙값)
#   width              0.828        0.620
#   height             0.79         0.62
#   scale              0.83         0.62
#
# 이유는 단순하다. 진단은 예측 박스를 자로 삼아 라벨을 재는데, 모델이
# 확신하지 못한 예측은 자 자체가 흔들린다. 그 자로 잰 변형률은 라벨이 아니라
# 모델의 불확실성을 재고 있는 것이다.
#
# 확신도로 후보를 잘라내는 대신(재현율이 20% 넘게 깎인다) 순위에만 반영한다 —
# 버리는 건 없고 순서만 바뀌므로 재현율이 그대로다. 세기 항과 같은 형태로
# 0.5~1.0 구간에 눌러, 유형 신뢰도가 순서의 주도권을 유지하게 한다.
# 가중치는 0.2~1.0을 훑어 상위 10% 정밀도가 가장 높은 지점으로 잡았다
# (0.5에서 78.3%, 0.7 이상에서는 다시 떨어짐).
CONFIDENCE_FLOOR = 0.5
# 누락은 확신도가 곧 원시 신호이므로 제외한다(이중 계산). 중복은 실측을
# 안 해서 넣지 않았다 — 이미 정밀도 90%로 약한 고리가 아니다.
CONFIDENCE_WEIGHTED_TYPES = {"width", "height", "scale", "translation_x", "translation_y"}

def _load_reliability_profile() -> None:
    """도메인별로 재보정한 신뢰도를 기본 상수 위에 덮어쓴다.

    기본값은 KITTI Car 단일 클래스 실측치다. 다중 클래스로 검증해보니
    **"존재 시" 값은 잘 옮겨가지만 "부재 시" 값은 크게 달라졌다** —
    누락이 88% → 22%로 무너졌다(docs/21 L). 그래서 상수를 코드에 박아두는
    대신 프로파일로 갈아끼울 수 있게 한다.

    프로파일 형식: {"present": {유형: 0~1}, "noise": {유형: 0~1}}
    빠진 유형은 기본값을 그대로 쓴다.
    """
    path = os.environ.get("AIDA_RELIABILITY_PROFILE", "")
    if not path:
        return
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key, table in (("present", TYPE_RELIABILITY_PRESENT),
                       ("noise", TYPE_RELIABILITY_NOISE)):
        for suspicion, value in data.get(key, {}).items():
            table[suspicion] = float(value)


_load_reliability_profile()


# 유형별 (임계값, 이 값 이상이면 신호가 최대) — 신호 세기 정규화 구간.
_STRENGTH_RANGE = {
    "width": (SIZE_DEVIATION_THRESHOLD, 0.40),
    "height": (SIZE_DEVIATION_THRESHOLD, 0.40),
    "scale": (SIZE_DEVIATION_THRESHOLD, 0.40),
    "translation_x": (CENTER_SHIFT_THRESHOLD, 0.40),
    "translation_y": (CENTER_SHIFT_THRESHOLD, 0.40),
    "missing": (MISSING_CONFIDENCE_THRESHOLD, 1.0),
    "duplicate": (DUPLICATE_IOU_THRESHOLD, 1.0),
    "class_mismatch": (MATCH_IOU_THRESHOLD, 1.0),
}


def severity_for(suspicion: str, raw_signal: float, is_present: bool = False,
                 confidence: float | None = None) -> float:
    """유형 신뢰도 × 신호 세기 → 유형이 달라도 비교 가능한 재검수 우선순위 점수.

    is_present는 "이 유형이 데이터셋에 계통적 수준으로 존재하는가"다. 이미지
    한 장만 볼 때는 알 수 없으므로 기본값은 False이고, 데이터셋 전체를 본 뒤
    rescore()가 다시 매긴다.
    """
    floor, ceiling = _STRENGTH_RANGE.get(suspicion, (0.0, 1.0))
    span = ceiling - floor
    strength = (raw_signal - floor) / span if span > 0 else 1.0
    strength = min(max(strength, 0.0), 1.0)
    table = TYPE_RELIABILITY_PRESENT if is_present else TYPE_RELIABILITY_NOISE
    reliability = table.get(suspicion, 0.5)
    # 세기는 0.5~1.0 구간으로 눌러서, 유형 신뢰도가 순서의 주도권을 갖게 한다
    score = reliability * (0.5 + 0.5 * strength)
    if confidence is not None and suspicion in CONFIDENCE_WEIGHTED_TYPES:
        # 라벨을 잰 자(예측 박스)가 얼마나 미더운가. 세기와 같은 형태로 눌러
        # 최대 절반까지만 깎으므로, 심각도 <= 유형 신뢰도는 그대로 유지된다.
        c = (confidence - CONFIDENCE_FLOOR) / (1.0 - CONFIDENCE_FLOOR)
        score *= 0.5 + 0.5 * min(max(c, 0.0), 1.0)
    return round(score, 4)


@dataclass(frozen=True)
class BoxFinding:
    """의심 박스 하나. image/label_index로 고객이 바로 그 박스를 찾아갈 수 있다."""
    image: str
    label_index: int | None  # 누락 의심이면 대응하는 라벨이 없으므로 None
    suspicion: str  # missing | duplicate | class_mismatch | scale | width | height
                    # | translation_x | translation_y
    severity: float  # 0~1, 클수록 확실. 재검수 우선순위 정렬 키
    detail: str  # 사람이 읽을 근거 ("예측 대비 28% 작음" 등)
    # 문제의 박스 위치. 라벨이 있는 의심은 그 라벨 박스, 누락 의심은 "라벨이
    # 있어야 할 자리"인 예측 박스다. 좌표계는 입력과 같다(보통 픽셀).
    # 누락 의심은 가리킬 인덱스가 없어서, 이 좌표가 그 박스를 지목하는
    # 유일한 수단이다 — 박스 단위 정확도 측정도 이 좌표로 대조한다.
    box: Box = (0.0, 0.0, 0.0, 0.0)
    # severity를 만들기 전의 원시 신호(누락=확신도, 중복=겹침, 기하=변형률).
    # 데이터셋 전체를 본 뒤 severity를 다시 매기려면(rescore) 원시 신호가
    # 남아 있어야 한다 — severity만 있으면 신뢰도를 되돌릴 수 없다.
    raw_signal: float = 0.0
    # 이 의심을 만든 예측 박스의 확신도. rescore가 심각도를 다시 매길 때
    # 원시 신호와 함께 필요하다. 기본 1.0은 "확신도 정보 없음 = 감점 없음"이다.
    confidence: float = 1.0


def present_types(summary: dict) -> set[str]:
    """데이터셋에 계통적 수준으로 존재한다고 볼 오류 유형들.

    1등만 뽑지 않는다 — 혼합 오류 실측에서 2차 유형도 존재하기만 하면 대표
    유형만큼 미더웠기 때문이다(TYPE_RELIABILITY_PRESENT 주석 참고).
    dominant_ratio가 임계값을 넘는다는 건 곧 이 집합이 비지 않는다는 뜻이라,
    기존의 systematic 판정과도 어긋나지 않는다.
    """
    return {
        t["suspicion"] for t in summary.get("by_type", [])
        if t["ratio"] >= SYSTEMATIC_ERROR_RATIO
    }


def rescore(findings: list[BoxFinding], summary: dict) -> list[BoxFinding]:
    """데이터셋 전체를 본 뒤 severity를 다시 매긴다.

    diagnose_image는 이미지 한 장씩 처리하므로 "이 데이터셋에 어떤 오류가
    계통적으로 있는지"를 알 수 없다. 그래서 일단 보수적인(노이즈) 신뢰도로
    점수를 매겨두고, summarize()가 유형별 비율을 낸 뒤 여기서 갱신한다.

    계통적 수준의 유형이 하나도 없으면 아무것도 바꾸지 않는다 — 근거가 약한
    상태에서 특정 유형을 밀어올리면 오류가 증폭되기 때문이다.
    """
    present = present_types(summary)
    if not present:
        return findings
    return [
        replace(f, severity=severity_for(f.suspicion, f.raw_signal, is_present=True,
                                         confidence=f.confidence))
        if f.suspicion in present else f
        for f in findings
    ]


def center_size(box: Box) -> tuple[float, float, float, float]:
    left, top, right, bottom = box
    return (left + right) / 2, (top + bottom) / 2, right - left, bottom - top


def iou(a: Box, b: Box) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def covered_ratio(box: Box, others: list[Box]) -> float:
    """box가 others에 얼마나 삼켜져 있는가 — (교집합 / box 면적)의 최대값.

    iou()와 달리 비대칭이다. 큰 라벨 안에 작은 예측이 통째로 들어간 경우
    iou는 작지만 이 값은 1.0이 되어, "이미 라벨된 영역"임을 잡아낸다.
    """
    l, t, r, b = box
    area = max(r - l, 0.0) * max(b - t, 0.0)
    if area <= 0:
        return 0.0
    best = 0.0
    for ol, ot, orr, ob in others:
        iw = max(min(r, orr) - max(l, ol), 0.0)
        ih = max(min(b, ob) - max(t, ot), 0.0)
        best = max(best, iw * ih / area)
    return best


def match_boxes(
    predictions: list[Box],
    labels: list[Box],
    iou_threshold: float = MATCH_IOU_THRESHOLD,
    pred_classes: list[int] | None = None,
    label_classes: list[int] | None = None,
) -> tuple[dict[int, int], list[int], list[int]]:
    """IoU가 큰 쌍부터 욕심껏 1:1로 짝짓는다.

    클래스 정보가 주어지면 **같은 클래스끼리만** 짝짓는다. 단일 클래스에서는
    아무 차이가 없지만, 다중 클래스에서 클래스를 무시하면 사람 라벨에 자동차
    예측이 붙는 식의 짝이 생긴다. 그 쌍의 기하 편차는 라벨 오류가 아니라
    서로 다른 물체를 비교한 결과라, 없는 오류를 만들어낸다.

    반환: (label_index -> pred_index 매칭, 짝 없는 예측 인덱스, 짝 없는 라벨 인덱스)
    """
    def compatible(pi: int, li: int) -> bool:
        if pred_classes is None or label_classes is None:
            return True
        if pi >= len(pred_classes) or li >= len(label_classes):
            return True
        return pred_classes[pi] == label_classes[li]

    pairs = [
        (iou(p, l), pi, li)
        for pi, p in enumerate(predictions)
        for li, l in enumerate(labels)
        if iou(p, l) >= iou_threshold and compatible(pi, li)
    ]
    pairs.sort(reverse=True)

    matched: dict[int, int] = {}
    used_preds: set[int] = set()
    for _, pi, li in pairs:
        if pi in used_preds or li in matched:
            continue
        matched[li] = pi
        used_preds.add(pi)

    unmatched_preds = [i for i in range(len(predictions)) if i not in used_preds]
    unmatched_labels = [i for i in range(len(labels)) if i not in matched]
    return matched, unmatched_preds, unmatched_labels


def classify_geometry(pred: Box, label: Box) -> tuple[str, float, str] | None:
    """짝지어진 예측/라벨 쌍의 기하학적 어긋남을 분류한다.

    가장 강한 신호 하나만 고른다 — 예를 들어 스케일 오류는 가로·세로가 함께
    변하므로 width/height 둘 다 걸리는데, 그럴 땐 scale로 부르는 게 맞다.
    반환값 None은 "이 박스는 정상"이라는 뜻.
    """
    p_cx, p_cy, p_w, p_h = center_size(pred)
    l_cx, l_cy, l_w, l_h = center_size(label)
    if p_w <= 0 or p_h <= 0:
        return None

    dx = (l_cx - p_cx) / p_w
    dy = (l_cy - p_cy) / p_h
    w_dev = l_w / p_w - 1
    h_dev = l_h / p_h - 1

    shift = max(abs(dx), abs(dy))
    size_dev = max(abs(w_dev), abs(h_dev))

    # 이동이 크기 변형보다 두드러지면 이동으로 본다
    if shift >= CENTER_SHIFT_THRESHOLD and shift > size_dev:
        if abs(dx) >= abs(dy):
            return "translation_x", min(abs(dx), 1.0), f"예측 대비 가로로 {dx * 100:+.0f}% 이동"
        return "translation_y", min(abs(dy), 1.0), f"예측 대비 세로로 {dy * 100:+.0f}% 이동"

    if size_dev < SIZE_DEVIATION_THRESHOLD:
        return None

    # 가로·세로가 같은 방향으로 함께 변했으면 스케일
    both_deviate = abs(w_dev) >= SIZE_DEVIATION_THRESHOLD and abs(h_dev) >= SIZE_DEVIATION_THRESHOLD
    if both_deviate and (w_dev > 0) == (h_dev > 0):
        avg = (w_dev + h_dev) / 2
        return "scale", min(abs(avg), 1.0), f"예측 대비 전체 크기 {avg * 100:+.0f}%"

    if abs(w_dev) >= abs(h_dev):
        return "width", min(abs(w_dev), 1.0), f"예측 대비 가로 {w_dev * 100:+.0f}%"
    return "height", min(abs(h_dev), 1.0), f"예측 대비 세로 {h_dev * 100:+.0f}%"


def diagnose_image(
    image: str,
    predictions: list[Box],
    confidences: list[float],
    labels: list[Box],
    pred_classes: list[int] | None = None,
    label_classes: list[int] | None = None,
    class_names: list[str] | None = None,
) -> list[BoxFinding]:
    """이미지 한 장의 예측/라벨을 대조해 의심 박스 목록을 만든다.

    클래스 정보는 선택이다 — 안 주면 예전처럼 클래스를 무시하고 위치만 본다.
    """
    matched, unmatched_preds, unmatched_labels = match_boxes(
        predictions, labels, pred_classes=pred_classes, label_classes=label_classes)
    findings: list[BoxFinding] = []

    def cname(i: int) -> str:
        if class_names and 0 <= i < len(class_names):
            return class_names[i]
        return f"클래스 {i}"

    # 1) 짝지어진 라벨: 기하학적으로 어긋났는지 본다
    for li, pi in matched.items():
        verdict = classify_geometry(predictions[pi], labels[li])
        if verdict is not None:
            suspicion, raw, detail = verdict
            conf = confidences[pi] if pi < len(confidences) else 1.0
            findings.append(BoxFinding(
                image, li, suspicion,
                severity_for(suspicion, raw, confidence=conf), detail,
                labels[li], raw, conf,
            ))

    # 2) 짝 없는 라벨: 먼저 "클래스만 다른 예측"이 같은 자리에 있는지 본다.
    #    클래스 인식 매칭을 켜면 클래스가 틀린 라벨은 짝을 못 찾는데, 그걸
    #    그냥 두면 예측 쪽이 "누락"으로, 라벨 쪽이 "중복"으로 잘못 불린다.
    #    실제 라벨링 현장에서 가장 흔한 오류가 클래스 오기입이라, 이걸
    #    별도 유형으로 부르는 게 맞다.
    class_mismatched: set[int] = set()
    if pred_classes is not None and label_classes is not None:
        matched_preds = set(matched.values())
        for li in unmatched_labels:
            best, best_pi = MATCH_IOU_THRESHOLD, None
            for pi, pbox in enumerate(predictions):
                if pi in matched_preds or li >= len(label_classes):
                    continue
                if pi < len(pred_classes) and pred_classes[pi] == label_classes[li]:
                    continue  # 같은 클래스인데 안 붙었으면 클래스 문제가 아니다
                v = iou(pbox, labels[li])
                if v >= best:
                    best, best_pi = v, pi
            if best_pi is None:
                continue
            # 확신도가 낮으면 이 라벨도 예측도 더는 건드리지 않는다. 판정은
            # 못 하지만, 그렇다고 예측을 "누락"으로 라벨을 "중복"으로 부르면
            # 없는 오류를 만들어낸다.
            conf = confidences[best_pi] if best_pi < len(confidences) else 1.0
            class_mismatched.add(li)
            matched_preds.add(best_pi)
            if conf < CLASS_MISMATCH_CONFIDENCE_THRESHOLD:
                continue
            findings.append(BoxFinding(
                image, li, "class_mismatch",
                severity_for("class_mismatch", best),
                f"모델은 {cname(pred_classes[best_pi])}로 보는데 "
                f"라벨은 {cname(label_classes[li])} (겹침 {best:.2f})",
                labels[li], best, conf,
            ))
        # 클래스 불일치로 쓰인 예측은 "라벨 없는 자리"가 아니므로 누락에서 뺀다
        unmatched_preds = [pi for pi in unmatched_preds if pi not in matched_preds]

    # 3) 짝 없는 라벨: 이미 짝지어진 예측과 크게 겹치면 중복 라벨
    for li in unmatched_labels:
        if li in class_mismatched:
            continue
        best_iou = 0.0
        for pi in matched.values():
            best_iou = max(best_iou, iou(predictions[pi], labels[li]))
        if best_iou >= DUPLICATE_IOU_THRESHOLD:
            findings.append(BoxFinding(
                image, li, "duplicate", severity_for("duplicate", best_iou),
                f"다른 라벨과 같은 객체를 가리킴 (겹침 {best_iou:.2f})",
                labels[li], best_iou,
            ))

    # 4) 짝 없는 예측: 모델이 확신하는데 라벨이 없으면 누락 의심.
    #    단, 기존 라벨에 대부분 삼켜진 예측은 제외한다 — 라벨된 객체의
    #    중복 탐지이거나 그 뒤에 가려진 객체라서, 누락 라벨이 아니다.
    for pi in unmatched_preds:
        conf = confidences[pi] if pi < len(confidences) else 0.0
        if conf < MISSING_CONFIDENCE_THRESHOLD:
            continue
        if covered_ratio(predictions[pi], labels) >= MISSING_MAX_COVERED_RATIO:
            continue
        findings.append(BoxFinding(
            image, None, "missing", severity_for("missing", conf),
            f"모델이 확신({conf:.2f})하는 위치에 라벨 없음",
            predictions[pi], conf,
        ))

    return findings


def summarize(findings: list[BoxFinding], total_labels: int) -> dict:
    """박스 단위 의심을 데이터셋 단위 요약으로 접는다.

    "계통적 오류가 있는가"의 판단 기준은 총 의심 비율이 아니라 **한 유형에
    몰렸는가(dominant_ratio)**다. 깨끗한 데이터셋에서도 모델 예측이 흔들려
    라벨의 10% 남짓은 의심으로 걸리는데, 그 오탐은 유형별로 얇게 흩어진다
    (실측: clean 조건에서 총 16.8% 의심이지만 최대 유형은 7.4%). 반면 실제로
    오류가 주입된 데이터셋은 한 유형이 26~60%로 몰린다. 총합만 보면 둘이
    구분되지 않지만 최대 유형 비율로는 깨끗하게 갈린다.
    """
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.suspicion] = counts.get(f.suspicion, 0) + 1

    by_type = [
        {
            "suspicion": name,
            "count": count,
            # 라벨 수 대비 비율 — 데이터셋 크기가 달라도 비교 가능하게
            "ratio": round(count / total_labels, 4) if total_labels else 0.0,
        }
        for name, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
    dominant = by_type[0] if by_type else None
    dominant_ratio = dominant["ratio"] if dominant else 0.0
    return {
        "total_labels": total_labels,
        "total_findings": len(findings),
        "suspicion_ratio": round(len(findings) / total_labels, 4) if total_labels else 0.0,
        "by_type": by_type,
        "dominant_type": dominant["suspicion"] if dominant else None,
        "dominant_ratio": dominant_ratio,
        "systematic": dominant_ratio >= SYSTEMATIC_ERROR_RATIO,
    }
