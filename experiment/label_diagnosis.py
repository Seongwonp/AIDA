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
from dataclasses import dataclass

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
MISSING_CONFIDENCE_THRESHOLD = 0.5
# 한 유형의 의심이 전체 라벨의 이 비율을 넘으면 "계통적 오류"로 판정한다.
# clean의 최대 유형 비율(7.4% 실측)과 실제 오류 조건의 최대 유형 비율
# (26%+) 사이에 두되, 약한 오류(10% 주입)까지 놓치지 않도록 낮게 잡았다.
SYSTEMATIC_ERROR_RATIO = 0.12


@dataclass(frozen=True)
class BoxFinding:
    """의심 박스 하나. image/label_index로 고객이 바로 그 박스를 찾아갈 수 있다."""
    image: str
    label_index: int | None  # 누락 의심이면 대응하는 라벨이 없으므로 None
    suspicion: str  # missing | duplicate | scale | width | height | translation_x | translation_y
    severity: float  # 0~1, 클수록 확실. 재검수 우선순위 정렬 키
    detail: str  # 사람이 읽을 근거 ("예측 대비 28% 작음" 등)


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


def match_boxes(
    predictions: list[Box],
    labels: list[Box],
    iou_threshold: float = MATCH_IOU_THRESHOLD,
) -> tuple[dict[int, int], list[int], list[int]]:
    """IoU가 큰 쌍부터 욕심껏 1:1로 짝짓는다.

    반환: (label_index -> pred_index 매칭, 짝 없는 예측 인덱스, 짝 없는 라벨 인덱스)
    """
    pairs = [
        (iou(p, l), pi, li)
        for pi, p in enumerate(predictions)
        for li, l in enumerate(labels)
        if iou(p, l) >= iou_threshold
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
) -> list[BoxFinding]:
    """이미지 한 장의 예측/라벨을 대조해 의심 박스 목록을 만든다."""
    matched, unmatched_preds, unmatched_labels = match_boxes(predictions, labels)
    findings: list[BoxFinding] = []

    # 1) 짝지어진 라벨: 기하학적으로 어긋났는지 본다
    for li, pi in matched.items():
        verdict = classify_geometry(predictions[pi], labels[li])
        if verdict is not None:
            suspicion, severity, detail = verdict
            findings.append(BoxFinding(image, li, suspicion, round(severity, 3), detail))

    # 2) 짝 없는 라벨: 이미 짝지어진 예측과 크게 겹치면 중복 라벨
    for li in unmatched_labels:
        best_iou = 0.0
        for pi in matched.values():
            best_iou = max(best_iou, iou(predictions[pi], labels[li]))
        if best_iou >= DUPLICATE_IOU_THRESHOLD:
            findings.append(BoxFinding(
                image, li, "duplicate", round(best_iou, 3),
                f"다른 라벨과 같은 객체를 가리킴 (겹침 {best_iou:.2f})",
            ))

    # 3) 짝 없는 예측: 모델이 확신하는데 라벨이 없으면 누락 의심
    for pi in unmatched_preds:
        conf = confidences[pi] if pi < len(confidences) else 0.0
        if conf >= MISSING_CONFIDENCE_THRESHOLD:
            findings.append(BoxFinding(
                image, None, "missing", round(conf, 3),
                f"모델이 확신({conf:.2f})하는 위치에 라벨 없음",
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
